"""Stage 1 — Résolution de template et création de projet(s) par git clone/push mirror.

Cross-instance :
- Les templates vivent sur gitlab.com, sous TEMPLATE_GROUP_PATH.
- Les nouveaux projets sont créés sur l'instance GitLab locale (celle qui
  exécute ce pipeline, via CI_SERVER_URL), sous GROUP_PATH.
Deux clients GitLabAPIClient distincts sont donc nécessaires, chacun avec son
propre serveur et son propre token :
- template_client -> gitlab.com, lecture seule (TEMPLATE_GITLAB_TOKEN)
- local_client     -> instance locale, écriture (GITLAB_API_TOKEN, existant)

Multi-projets : PROJECT_NAME accepte plusieurs noms (séparés par des virgules,
points-virgules ou retours à la ligne). Tous sont créés depuis le même template,
dans le même groupe, en une seule exécution du pipeline. Le template n'est cloné
qu'une fois puis poussé vers chaque destination, et les projets sont provisionnés
en parallèle (MAX_PARALLEL_PROJECTS).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

from audit_tool.manifest import (
    ManifestError,
    expected_manifest,
    locate_manifest,
    read_identifier,
    rewrite_identifier,
    slugify as slugify_identifier,
)
from ci.lib.gitlab_api import GitLabAPIClient, GitLabAPIError

DEFAULT_MAX_PARALLEL = 4


class TemplateResolutionError(Exception):
    """Levée quand la résolution du template échoue (zéro ou multi-match non résolu)."""


class ProjectNamesError(Exception):
    """Levée quand la liste PROJECT_NAME est vide ou contient des doublons."""


def select_template(candidates: list[dict], project_type: str, variant: str | None) -> dict:
    """
    Sélectionne le template parmi les candidats trouvés par topic.

    - Zéro candidat -> échec dur.
    - Un seul candidat -> sélectionné directement.
    - Plusieurs candidats -> nécessite TEMPLATE_VARIANT, en égalité STRICTE
      (name ou path exact, pas de sous-chaîne ).
    """
    if not candidates:
        raise TemplateResolutionError(
            f"aucun template trouvé pour PROJECT_TYPE='{project_type}'."
        )

    if len(candidates) == 1:
        return candidates[0]

    if not variant:
        names = ", ".join(c["path_with_namespace"] for c in candidates)
        raise TemplateResolutionError(
            f"plusieurs templates correspondent à PROJECT_TYPE='{project_type}' ({names}). "
            "Fournis TEMPLATE_VARIANT pour désambiguïser."
        )

    variant_lower = variant.lower()
    filtered = [
        c for c in candidates
        if c.get("name", "").lower() == variant_lower
        or c.get("path", "").lower() == variant_lower
    ]

    if len(filtered) != 1:
        names = ", ".join(c["path_with_namespace"] for c in candidates)
        raise TemplateResolutionError(
            f"TEMPLATE_VARIANT='{variant}' ne correspond pas exactement (name ou path) "
            f"à un unique candidat parmi : {names}."
        )

    return filtered[0]


def slugify(text: str) -> str:
    """Transforme un nom de projet en slug valide pour le chemin GitLab."""
    s = text.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s)
    return s.strip("-")


def parse_project_names(raw: str) -> list[str]:
    """Découpe PROJECT_NAME en liste de noms (virgule, point-virgule ou saut de ligne)."""
    return [part.strip() for part in re.split(r"[,;\n]", raw) if part.strip()]


def resolve_targets(names: list[str]) -> list[tuple[str, str]]:
    """Associe chaque nom à son slug et refuse les collisions.

    Deux noms distincts peuvent produire le même slug (ex. « Mon Projet » et
    « mon-projet ») : la seconde création échouerait côté GitLab avec un
    conflit de path, autant le détecter avant toute écriture.
    """
    if not names:
        raise ProjectNamesError("PROJECT_NAME ne contient aucun nom de projet exploitable.")

    targets: list[tuple[str, str]] = []
    seen: dict[str, str] = {}

    for name in names:
        slug = slugify(name)
        if not slug:
            raise ProjectNamesError(f"le nom '{name}' ne produit aucun slug valide.")
        if slug in seen:
            raise ProjectNamesError(
                f"les noms '{seen[slug]}' et '{name}' produisent le même slug '{slug}'."
            )
        seen[slug] = name
        targets.append((name, slug))

    return targets


def scrub(text: str, *secrets: str) -> str:
    """Masque les tokens susceptibles d'apparaître dans la sortie de git."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


def clone_template_mirror(auth_clone_url: str, mirror_dir: str, secret: str) -> None:
    """Clone le template une seule fois ; le miroir est ensuite poussé N fois."""
    res = subprocess.run(
        ["git", "clone", "--mirror", auth_clone_url, mirror_dir],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"clone --mirror du template (gitlab.com) échoué : {scrub(res.stderr, secret)}"
        )


def rename_manifest_identifier(
    local_client: GitLabAPIClient,
    project_path: str,
    project_type: str,
    project_name: str,
) -> dict:
    """Aligne le champ identifiant du manifeste sur un slug de PROJECT_NAME.

    `<artifactId>` racine pour Maven, `"name"` racine pour npm. Le commit passe
    par l'API GitLab (pas de clone local), sur la branche par défaut réelle du
    projet. C'est cette valeur que `audit_tool.rules.protected_tags` relira
    ensuite pour construire le pattern de protected tag.

    Fail-closed : toute anomalie (manifeste absent/multiple, champ absent ou
    illisible, branche par défaut indéterminée) lève ManifestError.
    """
    identifier = slugify_identifier(project_name)
    manifest_name = expected_manifest(project_type)

    project = local_client.get_project(project_path)
    default_branch = (project.get("default_branch") or "").strip()
    if not default_branch:
        raise ManifestError(
            f"branche par défaut indéterminée sur '{project_path}' : "
            "impossible de lire ou de commiter le manifeste."
        )

    tree = local_client.list_repository_tree(project_path, ref=default_branch)
    paths = [e["path"] for e in tree if e.get("type") == "blob"]
    manifest_path = locate_manifest(paths, manifest_name)

    content = local_client.get_raw_file(project_path, manifest_path, ref=default_branch)
    current = read_identifier(manifest_name, content)

    if current == identifier:
        return {
            "manifest": manifest_path,
            "identifier": identifier,
            "previous": current,
            "committed": False,
            "branch": default_branch,
        }

    updated = rewrite_identifier(manifest_name, content, identifier)
    local_client.create_commit(
        project_path,
        branch=default_branch,
        commit_message=f"chore(governx): aligne l'identifiant du manifeste sur '{identifier}'",
        actions=[{"action": "update", "file_path": manifest_path, "content": updated}],
    )

    return {
        "manifest": manifest_path,
        "identifier": identifier,
        "previous": current,
        "committed": True,
        "branch": default_branch,
    }


def provision_project(
    local_client: GitLabAPIClient,
    name: str,
    slug: str,
    target_group_id: int,
    project_type: str,
    template_path: str,
    mirror_dir: str,
) -> dict:
    """Crée le projet vide puis y pousse le miroir du template. Retourne sa fiche."""
    new_project = local_client.create_project(
        name=name,
        path=slug,
        namespace_id=target_group_id,
        description=(
            f"Projet {name} (type: {project_type}) initialisé depuis le template "
            f"{template_path} (gitlab.com)"
        ),
    )

    new_project_path = new_project["path_with_namespace"]
    new_project_http_url = new_project["http_url_to_repo"]
    auth_push_url = local_client.get_authenticated_git_url(new_project_http_url)

    # `git push` avec une URL explicite ne modifie pas le dépôt local : plusieurs
    # pushes concurrents depuis le même miroir sont sûrs.
    res = subprocess.run(
        ["git", "push", "--mirror", auth_push_url],
        cwd=mirror_dir,
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"push --mirror vers '{new_project_path}' échoué : "
            f"{scrub(res.stderr, local_client.token)}"
        )

    rename = rename_manifest_identifier(local_client, new_project_path, project_type, name)

    return {
        "name": name,
        "slug": slug,
        "path_with_namespace": new_project_path,
        "http_url_to_repo": new_project_http_url,
        "manifest": rename,
    }


def provision_all(
    local_client: GitLabAPIClient,
    targets: list[tuple[str, str]],
    target_group_id: int,
    project_type: str,
    template_path: str,
    mirror_dir: str,
    max_parallel: int,
) -> tuple[list[dict], list[dict]]:
    """Provisionne tous les projets en parallèle. Retourne (succès, échecs).

    Un échec n'interrompt pas les autres projets : le pipeline doit dire ce qui
    a été créé et ce qui ne l'a pas été, pas s'arrêter au premier problème.
    """
    def worker(target: tuple[str, str]) -> dict:
        name, slug = target
        try:
            created = provision_project(
                local_client, name, slug, target_group_id, project_type, template_path, mirror_dir
            )
            manifest = created["manifest"]
            suffix = "" if manifest["committed"] else " (déjà aligné)"
            print(
                f"  [OK]  {name} -> {created['path_with_namespace']} "
                f"[{manifest['manifest']} : {manifest['identifier']}{suffix}]"
            )
            return {"status": "ok", "project": created}
        except (GitLabAPIError, ManifestError, RuntimeError) as exc:
            message = scrub(str(exc), local_client.token)
            print(f"  [KO]  {name} : {message}")
            return {"status": "failed", "error": {"name": name, "slug": slug, "error": message}}

    workers = max(1, min(max_parallel, len(targets)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        outcomes = list(pool.map(worker, targets))  # map préserve l'ordre d'entrée

    created = [o["project"] for o in outcomes if o["status"] == "ok"]
    failed = [o["error"] for o in outcomes if o["status"] == "failed"]
    return created, failed


def write_outputs(created: list[dict], failed: list[dict], reports_dir: str) -> None:
    """Écrit l'artifact dotenv (consommé par les stages suivants) et le récapitulatif JSON."""
    paths = [p["path_with_namespace"] for p in created]

    with open("create_project.env", "w", encoding="utf-8") as f:
        f.write(f"NEW_PROJECT_PATHS={','.join(paths)}\n")
        f.write(f"NEW_PROJECT_COUNT={len(paths)}\n")
        # Compatibilité mono-projet : première entrée de la liste.
        f.write(f"NEW_PROJECT_PATH={paths[0] if paths else ''}\n")
        f.write(f"NEW_PROJECT_HTTP_URL={created[0]['http_url_to_repo'] if created else ''}\n")

    os.makedirs(reports_dir, exist_ok=True)
    summary_path = os.path.join(reports_dir, "created_projects.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({"created": created, "failed": failed}, f, indent=2, ensure_ascii=False)

    print(
        f"Artifacts générés : 'create_project.env' (NEW_PROJECT_PATHS={','.join(paths)}) "
        f"et '{summary_path}'."
    )


def main() -> None:
    project_name = os.getenv("PROJECT_NAME", "").strip()
    project_type = os.getenv("PROJECT_TYPE", "").strip()
    group_path = os.getenv("GROUP_PATH", "").strip()
    template_group_path = os.getenv("TEMPLATE_GROUP_PATH", "").strip()
    template_variant = os.getenv("TEMPLATE_VARIANT", "").strip()
    template_gitlab_url = os.getenv("TEMPLATE_GITLAB_URL", "https://gitlab.com").strip()
    template_gitlab_token = os.getenv("TEMPLATE_GITLAB_TOKEN", "").strip()

    try:
        max_parallel = int(os.getenv("MAX_PARALLEL_PROJECTS", str(DEFAULT_MAX_PARALLEL)))
    except ValueError:
        max_parallel = DEFAULT_MAX_PARALLEL

    missing_vars = []
    if not project_name:
        missing_vars.append("PROJECT_NAME")
    if not project_type:
        missing_vars.append("PROJECT_TYPE")
    if not group_path:
        missing_vars.append("GROUP_PATH")
    if not template_group_path:
        missing_vars.append("TEMPLATE_GROUP_PATH")
    if not template_gitlab_token:
        missing_vars.append("TEMPLATE_GITLAB_TOKEN")

    if missing_vars:
        sys.stderr.write(
            f"Erreur critique : Les variables obligatoires suivantes sont manquantes : {', '.join(missing_vars)}.\n"
        )
        sys.exit(1)

    try:
        targets = resolve_targets(parse_project_names(project_name))
    except ProjectNamesError as exc:
        sys.stderr.write(f"Erreur critique : {exc}\n")
        sys.exit(1)

    print(f"{len(targets)} projet(s) à créer : {', '.join(name for name, _ in targets)}")

    # Client "source" : gitlab.com, lecture seule des templates.
    template_client = GitLabAPIClient(server_url=template_gitlab_url, token=template_gitlab_token)
    # Client "destination" : instance locale (CI_SERVER_URL / GITLAB_API_TOKEN), écriture.
    local_client = GitLabAPIClient()

    try:
        print(f"Recherche des templates pour le topic '{project_type}' dans '{template_group_path}' sur {template_gitlab_url}...")
        candidates = template_client.search_templates_by_topic(template_group_path, project_type)

        try:
            selected_template = select_template(candidates, project_type, template_variant or None)
        except TemplateResolutionError as exc:
            sys.stderr.write(f"Erreur critique : {exc}\n")
            sys.exit(1)

        template_path = selected_template["path_with_namespace"]
        print(f"Template sélectionné : {template_path} (gitlab.com)")

        print(f"Récupération de l'ID du groupe cible '{group_path}' sur l'instance locale...")
        target_group_id = local_client.get_group_id(group_path)
    except GitLabAPIError as exc:
        sys.stderr.write(f"Erreur critique : {exc}\n")
        sys.exit(1)

    auth_clone_url = template_client.get_authenticated_git_url(selected_template["http_url_to_repo"])

    reports_dir = os.path.abspath("reports")

    with tempfile.TemporaryDirectory() as tmpdir:
        mirror_dir = os.path.join(tmpdir, "template.git")

        print("Clone --mirror du template (une seule fois pour tous les projets)...")
        try:
            clone_template_mirror(auth_clone_url, mirror_dir, template_client.token)
        except RuntimeError as exc:
            sys.stderr.write(f"Erreur critique : {exc}\n")
            sys.exit(1)

        workers = max(1, min(max_parallel, len(targets)))
        print(f"Provisionnement de {len(targets)} projet(s) ({workers} en parallèle)...")
        created, failed = provision_all(
            local_client, targets, target_group_id, project_type,
            template_path, mirror_dir, max_parallel,
        )

    write_outputs(created, failed, reports_dir)

    if failed:
        sys.stderr.write(
            f"Erreur critique : {len(failed)} projet(s) sur {len(targets)} n'ont pas pu être créés : "
            + "; ".join(f"{f['name']} ({f['error']})" for f in failed)
            + "\n"
        )
        sys.exit(1)

    print(f"{len(created)} projet(s) créé(s) et initialisé(s) avec succès.")


if __name__ == "__main__":
    main()
