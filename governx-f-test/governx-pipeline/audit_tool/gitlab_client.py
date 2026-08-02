"""audit_tool.gitlab_client — connexion GitLab et récupération de projet(s).
"""
from __future__ import annotations

import os

import gitlab


EXCLUDED_GROUP_PATH = os.getenv("EXCLUDED_GROUP_PATH", "")


def get_gitlab_connection(url: str, token: str) -> gitlab.Gitlab:
    """Ouvre et authentifie une connexion python-gitlab."""
    gl = gitlab.Gitlab(url, private_token=token)
    gl.auth()
    return gl


def get_project(gl: gitlab.Gitlab, project_path: str):
    """Récupère l'objet Project (python-gitlab) pour le projet audité (usage GovernX actuel : 1 seul projet)."""
    return gl.projects.get(project_path)


def resolve_user_id(gl: gitlab.Gitlab, user_identifier):
    """Résout un identifiant utilisateur (ID numérique ou username) en ID GitLab. """
    if user_identifier is None:
        return None

    if str(user_identifier).isdigit():
        return int(user_identifier)

    users = gl.users.list(username=user_identifier)
    if not users:
        print(f"⚠️ Utilisateur introuvable pour le username '{user_identifier}'")
        return None

    return users[0].id


def get_filtered_projects(gl: gitlab.Gitlab):
    """Liste tous les projets de l'instance, hors ceux du groupe EXCLUDED_GROUP_PATH."""
    filtered = []
    for project in gl.projects.list(iterator=True):
        if project.path_with_namespace.startswith(EXCLUDED_GROUP_PATH + "/"):
            continue
        filtered.append(project)
    return filtered