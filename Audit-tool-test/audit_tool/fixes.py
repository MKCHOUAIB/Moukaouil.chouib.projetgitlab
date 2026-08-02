import gitlab
from urllib.parse import quote

from audit_tool.rules.protected_branches import EXPECTED_RULES
from audit_tool.rules.protected_tags import MAINTAINER


def fix_protected_branches(project, result, dry_run=False, tier="free"):
    if tier == "premium":
        return _fix_protected_branches_premium(project, result, dry_run)
    return _fix_protected_branches_free(project, result, dry_run)


def _fix_protected_branches_free(project, result, dry_run):
    branch_name = result.get("branch")
    rule = next((r for r in EXPECTED_RULES if r["pattern"] == branch_name), None)

    if rule is None:
        return {
            "rule": "protected_branches", "project": project.path_with_namespace,
            "branch": branch_name, "action": "aucune action", "dry_run": dry_run,
            "success": False, "details": f"Aucune règle définie pour la branche '{branch_name}'",
        }

    push_level = next(iter(rule["push"]))
    merge_level = next(iter(rule["merge"]))

    if dry_run:
        return {
            "rule": "protected_branches", "project": project.path_with_namespace,
            "branch": branch_name,
            "action": f"protection à recréer (push={push_level}, merge={merge_level})",
            "dry_run": True, "success": True, "details": "Dry-run : aucune écriture effectuée",
        }

    try:
        existing = next(
            (pb for pb in project.protectedbranches.list(get_all=True) if pb.name == branch_name),
            None,
        )
        if existing is not None:
            existing.delete()

        project.protectedbranches.create({
            "name": branch_name,
            "push_access_level": push_level,
            "merge_access_level": merge_level,
        })

        return {
            "rule": "protected_branches", "project": project.path_with_namespace,
            "branch": branch_name,
            "action": f"protection recréée (push={push_level}, merge={merge_level})",
            "dry_run": False, "success": True, "details": "OK",
        }
    except Exception as e:
        return {
            "rule": "protected_branches", "project": project.path_with_namespace,
            "branch": branch_name, "action": "correction échouée",
            "dry_run": False, "success": False, "details": str(e),
        }


def _fix_protected_branches_premium(project, result, dry_run):
    branch_name = result.get("branch")
    rule = next((r for r in EXPECTED_RULES if r["pattern"] == branch_name), None)

    if rule is None:
        return {
            "rule": "protected_branches", "project": project.path_with_namespace,
            "branch": branch_name, "action": "aucune action", "dry_run": dry_run,
            "success": False, "details": f"Aucune règle définie pour la branche '{branch_name}'",
        }

    gl = project.manager.gitlab
    encoded_name = quote(branch_name, safe="")
    api_path = f"/projects/{project.id}/protected_branches/{encoded_name}"

    try:
        pb = project.protectedbranches.get(branch_name)
    except gitlab.exceptions.GitlabGetError:
        pb = None

    if pb is None:
        if dry_run:
            return {
                "rule": "protected_branches", "project": project.path_with_namespace,
                "branch": branch_name, "action": "création de la protection (simulation)",
                "dry_run": True, "success": True, "details": "Dry-run : aucune écriture effectuée",
            }
        try:
            project.protectedbranches.create({
                "name": branch_name,
                "allowed_to_push": [{"access_level": lvl} for lvl in rule["push"]],
                "allowed_to_merge": [{"access_level": lvl} for lvl in rule["merge"]],
            })
            return {
                "rule": "protected_branches", "project": project.path_with_namespace,
                "branch": branch_name, "action": "protection créée",
                "dry_run": False, "success": True, "details": "OK",
            }
        except Exception as e:
            return {
                "rule": "protected_branches", "project": project.path_with_namespace,
                "branch": branch_name, "action": "création échouée",
                "dry_run": False, "success": False, "details": str(e),
            }

    payload = {}
    for field, existing_entries, target_levels in [
        ("allowed_to_push", pb.push_access_levels, rule["push"]),
        ("allowed_to_merge", pb.merge_access_levels, rule["merge"]),
    ]:
        existing_by_level = {entry["access_level"]: entry["id"] for entry in existing_entries}
        entries = []
        for level, entry_id in existing_by_level.items():
            if level not in target_levels:
                entries.append({"id": entry_id, "_destroy": True})
        for level in target_levels:
            if level not in existing_by_level:
                entries.append({"access_level": level})
        if entries:
            payload[field] = entries

    if not payload:
        return {
            "rule": "protected_branches", "project": project.path_with_namespace,
            "branch": branch_name, "action": "aucune action (déjà conforme)",
            "dry_run": dry_run, "success": True, "details": "OK",
        }

    if dry_run:
        return {
            "rule": "protected_branches", "project": project.path_with_namespace,
            "branch": branch_name, "action": f"modification prévue : {payload}",
            "dry_run": True, "success": True, "details": "Dry-run : aucune écriture effectuée",
        }

    try:
        gl.http_patch(api_path, post_data=payload)
        return {
            "rule": "protected_branches", "project": project.path_with_namespace,
            "branch": branch_name, "action": f"protection mise à jour : {payload}",
            "dry_run": False, "success": True, "details": "OK",
        }
    except Exception as e:
        return {
            "rule": "protected_branches", "project": project.path_with_namespace,
            "branch": branch_name, "action": "mise à jour échouée",
            "dry_run": False, "success": False, "details": str(e),
        }


def fix_protected_tags(project, result, dry_run=False, tier="free"):
    # Pas de PATCH pour les protected tags, peu importe la license -> même logique pour les deux tiers
    pattern = result.get("pattern")
    project_type = result.get("project_type")

    if pattern is None:
        return {
            "rule": "protected_tags", "project": project.path_with_namespace,
            "pattern": None, "project_type": None, "action": "aucune action",
            "dry_run": dry_run, "success": False,
            "details": "Impossible de corriger : aucun pattern de version détecté",
        }

    if dry_run:
        return {
            "rule": "protected_tags", "project": project.path_with_namespace,
            "pattern": pattern, "project_type": project_type,
            "action": f"protection du pattern '{pattern}' à recréer (Maintainer uniquement)",
            "dry_run": True, "success": True, "details": "Dry-run : aucune écriture effectuée",
        }

    try:
        existing = next(
            (pt for pt in project.protectedtags.list(get_all=True) if pt.name == pattern),
            None,
        )
        if existing is not None:
            existing.delete()

        project.protectedtags.create({"name": pattern, "create_access_level": MAINTAINER})

        return {
            "rule": "protected_tags", "project": project.path_with_namespace,
            "pattern": pattern, "project_type": project_type,
            "action": f"protection recréée sur '{pattern}' (Maintainer uniquement)",
            "dry_run": False, "success": True, "details": "OK",
        }
    except Exception as e:
        return {
            "rule": "protected_tags", "project": project.path_with_namespace,
            "pattern": pattern, "project_type": project_type,
            "action": "correction échouée", "dry_run": False, "success": False, "details": str(e),
        }


def fix_pipeline_success(project, result, dry_run=False, tier="free"):
    # Attribut simple, pas concerné par le tier -> même logique pour les deux
    if dry_run:
        return {
            "rule": "pipeline_must_succeed", "project": project.path_with_namespace,
            "action": "activation prévue de 'Pipeline must succeed'",
            "dry_run": True, "success": True, "details": "Dry-run : aucune écriture effectuée",
        }

    try:
        project.only_allow_merge_if_pipeline_succeeds = True
        project.save()
        return {
            "rule": "pipeline_must_succeed", "project": project.path_with_namespace,
            "action": "option 'Pipeline must succeed' activée",
            "dry_run": False, "success": True, "details": "OK",
        }
    except Exception as e:
        return {
            "rule": "pipeline_must_succeed", "project": project.path_with_namespace,
            "action": "activation échouée", "dry_run": False, "success": False, "details": str(e),
        }