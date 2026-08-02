import argparse
import gitlab
from dotenv import load_dotenv

from audit_tool.gitlab_client import get_gitlab_connection, get_filtered_projects, resolve_user_ids
from audit_tool.rules.protected_branches import check_protected_branches
from audit_tool.rules.protected_tags import check_protected_tags
from audit_tool.rules.pipeline_success import check_pipeline_success
from audit_tool.rules.specific_user_access import check_specific_user_access, VALID_ACCESS_TYPES
from audit_tool.fixes import fix_protected_branches, fix_protected_tags, fix_pipeline_success
from audit_tool.report import generate_report

load_dotenv()


def parse_user_branches(raw):
    """
    'main:both,develop:merge' -> {'main': 'both', 'develop': 'merge'}

    Lève ValueError sur toute entrée malformée : mieux vaut échouer bruyamment
    au démarrage que d'ignorer silencieusement une branche que l'utilisateur
    croyait avoir ciblée.
    """
    if not raw:
        return None

    branches = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue

        if ":" not in entry:
            raise ValueError(f"entrée '{entry}' : format attendu 'branche:access_type'")

        name, access_type = entry.split(":", 1)
        name = name.strip()
        access_type = access_type.strip()

        if not name:
            raise ValueError(f"entrée '{entry}' : nom de branche vide")
        if access_type not in VALID_ACCESS_TYPES:
            raise ValueError(
                f"entrée '{entry}' : access_type '{access_type}' invalide "
                f"(attendu : {', '.join(sorted(VALID_ACCESS_TYPES))})"
            )

        branches[name] = access_type

    return branches


def parse_args():
    parser = argparse.ArgumentParser(
        description="Audit de conformité GitLab CE (branches, tags, pipeline, accès utilisateur)"
    )
    parser.add_argument("--url", required=True, help="URL de l'instance GitLab ")
    parser.add_argument("--token", required=True, help="Token GitLab avec scope 'api'")
    parser.add_argument(
        "--user-id",
        type=str,
        default=None,
        help="ID(s) numérique(s) ou username(s) GitLab, séparés par des virgules (ex: alice,bob). Optionnel.",
    )
    parser.add_argument("--fix", action="store_true", help="Active la remédiation automatique des non-conformités")
    parser.add_argument("--dry-run", action="store_true", help="Simule les corrections sans écrire dans GitLab (nécessite --fix)")
    parser.add_argument(
        "--tier",
        choices=["free", "premium"],
        default="free",
        help="Édition GitLab cible pour les fixs (free=CE, premium=Premium/Ultimate). Défaut : free",
    )
    parser.add_argument(
        "--user-branches",
        type=str,
        default=None,
        help="Branches et types d'accès, ex: 'main:both,develop:merge,release/*:push' (tier=premium)",
    )
    return parser.parse_args()


def _gitlab_error_result(rule, project, error):
    return {
        "rule": rule,
        "project": project.path_with_namespace,
        "compliant": False,
        "details": f"Erreur API GitLab ({error.response_code}) : {error.error_message}",
    }


def run_audit(gitlab_url, gitlab_token, user_identifiers=None, fix=False, dry_run=False, tier="free", branches=None):
    gl = get_gitlab_connection(gitlab_url, gitlab_token)
    projects = get_filtered_projects(gl)

    resolved_user_ids = resolve_user_ids(gl, user_identifiers)

    # Règle facultative : en premium sans branches ciblées, il n'y a rien à
    # vérifier — on la saute pour ce run, comme quand aucun --user-id n'est fourni.
    if resolved_user_ids and tier == "premium" and not branches:
        print("⚠️ --tier premium sans --user-branches : règle specific_user_access ignorée")
        resolved_user_ids = []

    all_results = []

    for project in projects:
        print(f"--- Audit de : {project.path_with_namespace} ---")

        # protected_branches : une liste de résultats, un par branche
        try:
            branch_results = check_protected_branches(project)
        except gitlab.exceptions.GitlabError as e:
            branch_results = [_gitlab_error_result("protected_branches", project, e)]

        for branch_result in branch_results:
            all_results.append(branch_result)
            if fix and not branch_result["compliant"]:
                fix_result = fix_protected_branches(project, branch_result, dry_run=dry_run, tier=tier)
                all_results.append(fix_result)

        # protected_tags : un seul dict
        try:
            tags_result = check_protected_tags(project)
        except gitlab.exceptions.GitlabError as e:
            tags_result = _gitlab_error_result("protected_tags", project, e)
        all_results.append(tags_result)
        if fix and not tags_result["compliant"]:
            fix_result = fix_protected_tags(project, tags_result, dry_run=dry_run, tier=tier)
            all_results.append(fix_result)

        # pipeline_must_succeed : un seul dict
        try:
            pipeline_result = check_pipeline_success(project)
        except gitlab.exceptions.GitlabError as e:
            pipeline_result = _gitlab_error_result("pipeline_must_succeed", project, e)
        all_results.append(pipeline_result)
        if fix and not pipeline_result["compliant"]:
            fix_result = fix_pipeline_success(project, pipeline_result, dry_run=dry_run, tier=tier)
            all_results.append(fix_result)

        # specific_user_access : renvoie toujours une liste (1 dict/user en free,
        # 1 dict/(user, branche) en premium) — écrit déjà directement, pas de fix_* séparé
        if resolved_user_ids:
            try:
                results = check_specific_user_access(project, resolved_user_ids, tier=tier, branches=branches)
                all_results.extend(results)
            except gitlab.exceptions.GitlabError as e:
                all_results.append(_gitlab_error_result("specific_user_access", project, e))

    return all_results


if __name__ == "__main__":
    args = parse_args()

    try:
        branches = parse_user_branches(args.user_branches)
    except ValueError as e:
        raise SystemExit(f"❌ --user-branches invalide : {e}")

    results = run_audit(
        args.url,
        args.token,
        args.user_id,
        fix=args.fix,
        dry_run=args.dry_run,
        tier=args.tier,
        branches=branches,
    )
    generate_report(results)

    print(f"\n=== {len(results)} résultats collectés ===")
    for r in results:
        rule_label = r["rule"]
        if r.get("branch"):
            rule_label += f":{r['branch']}"

        if "compliant" in r:
            status = "✅" if r["compliant"] else "❌"
            print(f"{status} [{rule_label}] {r['project']} — {r['details']}")
        else:
            # résultats de fix_* : pas de clé "compliant", format différent
            status = "🔧" if r["success"] else "⚠️"
            print(f"{status} [{rule_label}] {r['project']} — {r['action']} — {r['details']}")