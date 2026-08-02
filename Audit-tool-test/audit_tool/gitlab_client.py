import os
from dotenv import load_dotenv
import gitlab

load_dotenv()


EXCLUDED_GROUP_PATH = os.getenv("EXCLUDED_GROUP_PATH", "")


def get_gitlab_connection(gitlab_url, gitlab_token):
    try:
        gl = gitlab.Gitlab(gitlab_url, private_token=gitlab_token)
        gl.auth()
        return gl
    except gitlab.exceptions.GitlabAuthenticationError as e:
        print(f"Erreur d'authentification : {e}")
        raise
    except Exception as e:
        print(f"Erreur de connexion à GitLab : {e}")
        raise


def resolve_user_id(gl, user_identifier):

    if user_identifier is None:
        return None

    if str(user_identifier).isdigit():
        return int(user_identifier)

    users = gl.users.list(username=user_identifier)
    if not users:
        print(f"⚠️ Utilisateur introuvable pour le username '{user_identifier}'")
        return None

    return users[0].id


def resolve_user_ids(gl, user_identifiers):
    """
    user_identifiers: chaîne séparée par des virgules, ex. "alice,123,bob", ou None.
    Retourne une liste d'IDs numériques résolus (éventuellement vide). Les entrées
    non résolues sont ignorées avec un avertissement (déjà émis par resolve_user_id),
    sans faire échouer la résolution des autres.
    """
    if not user_identifiers:
        return []

    resolved = []
    for identifier in user_identifiers.split(","):
        identifier = identifier.strip()
        if not identifier:
            continue
        user_id = resolve_user_id(gl, identifier)
        if user_id is not None:
            resolved.append(user_id)

    return resolved


def get_filtered_projects(gl):
    filtered = []
    for project in gl.projects.list(iterator=True):
        if project.path_with_namespace.startswith(EXCLUDED_GROUP_PATH + "/"):
            continue
        filtered.append(project)
    return filtered


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test rapide de gitlab_client.py en standalone")
    parser.add_argument("--url", required=True)
    parser.add_argument("--token", required=True)
    args = parser.parse_args()

    gl = get_gitlab_connection(args.url, args.token)
    projects = get_filtered_projects(gl)
    print(f"{len(projects)} projets trouvés (hors groupe exclu)")
    for p in projects:
        print(f"- {p.path_with_namespace}")