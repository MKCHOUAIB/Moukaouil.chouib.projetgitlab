"""Règle pipeline_success — vérifie que 'Pipelines must succeed' est activé
pour les merge requests (only_allow_merge_if_pipeline_succeeds).

"""
from __future__ import annotations

from typing import Any


def check_pipeline_success(project: Any) -> dict:
    enabled = bool(getattr(project, "only_allow_merge_if_pipeline_succeeds", False))
    return {
        "rule": "pipeline_success",
        "project": project.path_with_namespace,
        "compliant": enabled,
        "details": "OK" if enabled else "Option 'Pipelines must succeed' désactivée",
    }


def fix_pipeline_success(project: Any, dry_run: bool = False) -> dict:
    action = "Activer only_allow_merge_if_pipeline_succeeds"

    if dry_run:
        return {
            "rule": "pipeline_success", "project": project.path_with_namespace,
            "action": action, "dry_run": True, "success": True, "details": "dry-run",
        }

    try:
        project.only_allow_merge_if_pipeline_succeeds = True
        project.save()
    except Exception as exc:
        return {
            "rule": "pipeline_success", "project": project.path_with_namespace,
            "action": action, "dry_run": False, "success": False, "details": f"Erreur API : {exc}",
        }

    return {
        "rule": "pipeline_success", "project": project.path_with_namespace,
        "action": action, "dry_run": False, "success": True, "details": "OK",
    }