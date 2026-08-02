"""Règle protected_branches — main/develop/release/* avec niveaux d'accès attendus.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

import gitlab

MAINTAINER = 40
DEVELOPER = 30

EXPECTED_RULES = [
    {"pattern": "main", "push": {MAINTAINER}, "merge": {MAINTAINER}},
    {"pattern": "develop", "push": {MAINTAINER}, "merge": {DEVELOPER}},
    {"pattern": "release/*", "push": {MAINTAINER}, "merge": {DEVELOPER}},
]


def check_protected_branches(project: Any) -> list[dict]:
    try:
        protected_branches = project.protectedbranches.list(get_all=True)
    except Exception as exc:
        return [
            _result(project, rule["pattern"], False, f"Erreur API : {exc}")
            for rule in EXPECTED_RULES
        ]

    protected_by_name = {pb.name: pb for pb in protected_branches}
    results = []

    for rule in EXPECTED_RULES:
        branch_name = rule["pattern"]
        pb = protected_by_name.get(branch_name)

        if pb is None:
            results.append(_result(project, branch_name, False, "Règle absente : la branche n'est pas protégée"))
            continue

        actual_push = {lvl["access_level"] for lvl in pb.push_access_levels}
        actual_merge = {lvl["access_level"] for lvl in pb.merge_access_levels}

        push_ok = actual_push == rule["push"]
        merge_ok = actual_merge == rule["merge"]

        if push_ok and merge_ok:
            results.append(_result(project, branch_name, True, "OK"))
        else:
            problems = []
            if not push_ok:
                problems.append(f"push attendu={rule['push']} trouvé={actual_push}")
            if not merge_ok:
                problems.append(f"merge attendu={rule['merge']} trouvé={actual_merge}")
            results.append(_result(project, branch_name, False, "; ".join(problems)))

    return results


def fix_protected_branches(project: Any, result: dict, dry_run: bool = False, tier: str = "free") -> dict:
    """Dispatcher free/premium. `result` est l'entrée retournée par check_protected_branches
    pour la branche non conforme (doit contenir la clé "branch")."""
    if tier == "premium":
        return _fix_protected_branches_premium(project, result, dry_run)
    return _fix_protected_branches_free(project, result, dry_run)


def _fix_protected_branches_free(project: Any, result: dict, dry_run: bool) -> dict:
    branch_name = result.get("branch")
    rule = next((r for r in EXPECTED_RULES if r["pattern"] == branch_name), None)

    if rule is None:
        return _fix_result(project, branch_name, "aucune action", dry_run, False,
                            f"Aucune règle définie pour la branche '{branch_name}'")

    push_level = next(iter(rule["push"]))
    merge_level = next(iter(rule["merge"]))

    if dry_run:
        return _fix_result(project, branch_name,
                            f"protection à recréer (push={push_level}, merge={merge_level})",
                            True, True, "Dry-run : aucune écriture effectuée")

    try:
        existing = next((pb for pb in project.protectedbranches.list(get_all=True) if pb.name == branch_name), None)
        if existing is not None:
            existing.delete()

        project.protectedbranches.create({
            "name": branch_name,
            "push_access_level": push_level,
            "merge_access_level": merge_level,
        })

        return _fix_result(project, branch_name,
                            f"protection recréée (push={push_level}, merge={merge_level})",
                            False, True, "OK")
    except Exception as e:
        return _fix_result(project, branch_name, "correction échouée", False, False, str(e))


def _fix_protected_branches_premium(project: Any, result: dict, dry_run: bool) -> dict:
    branch_name = result.get("branch")
    rule = next((r for r in EXPECTED_RULES if r["pattern"] == branch_name), None)

    if rule is None:
        return _fix_result(project, branch_name, "aucune action", dry_run, False,
                            f"Aucune règle définie pour la branche '{branch_name}'")

    gl = project.manager.gitlab
    encoded_name = quote(branch_name, safe="")
    api_path = f"/projects/{project.id}/protected_branches/{encoded_name}"

    try:
        pb = project.protectedbranches.get(branch_name)
    except gitlab.exceptions.GitlabGetError:
        pb = None

    if pb is None:
        if dry_run:
            return _fix_result(project, branch_name, "création de la protection (simulation)", True, True,
                                "Dry-run : aucune écriture effectuée")
        try:
            project.protectedbranches.create({
                "name": branch_name,
                "allowed_to_push": [{"access_level": lvl} for lvl in rule["push"]],
                "allowed_to_merge": [{"access_level": lvl} for lvl in rule["merge"]],
            })
            return _fix_result(project, branch_name, "protection créée", False, True, "OK")
        except Exception as e:
            return _fix_result(project, branch_name, "création échouée", False, False, str(e))

    payload: dict = {}
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
        return _fix_result(project, branch_name, "aucune action (déjà conforme)", dry_run, True, "OK")

    if dry_run:
        return _fix_result(project, branch_name, f"modification prévue : {payload}", True, True,
                            "Dry-run : aucune écriture effectuée")

    try:
        gl.http_patch(api_path, post_data=payload)
        return _fix_result(project, branch_name, f"protection mise à jour : {payload}", False, True, "OK")
    except Exception as e:
        return _fix_result(project, branch_name, "mise à jour échouée", False, False, str(e))


def _result(project: Any, branch: str, compliant: bool, details: str) -> dict:
    return {
        "rule": "protected_branches",
        "project": project.path_with_namespace,
        "branch": branch,
        "compliant": compliant,
        "details": details,
    }


def _fix_result(project: Any, branch: str, action: str, dry_run: bool, success: bool, details: str) -> dict:
    return {
        "rule": "protected_branches",
        "project": project.path_with_namespace,
        "branch": branch,
        "action": action,
        "dry_run": dry_run,
        "success": success,
        "details": details,
    }