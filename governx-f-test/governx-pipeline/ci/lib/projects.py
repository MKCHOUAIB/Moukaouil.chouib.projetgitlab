"""Lecture de la liste des projets produits par le stage create_project."""
from __future__ import annotations

import os

DEFAULT_MAX_PARALLEL = 4


def read_project_paths() -> list[str]:
    """Retourne les projets à traiter, depuis l'artifact dotenv de create_project.

    NEW_PROJECT_PATHS (liste séparée par des virgules) est la source de vérité ;
    NEW_PROJECT_PATH reste accepté pour les exécutions mono-projet.
    """
    raw = os.getenv("NEW_PROJECT_PATHS", "").strip() or os.getenv("NEW_PROJECT_PATH", "").strip()
    return [part.strip() for part in raw.split(",") if part.strip()]


def max_parallel() -> int:
    """Nombre de projets traités simultanément (MAX_PARALLEL_PROJECTS)."""
    try:
        return max(1, int(os.getenv("MAX_PARALLEL_PROJECTS", str(DEFAULT_MAX_PARALLEL))))
    except ValueError:
        return DEFAULT_MAX_PARALLEL
