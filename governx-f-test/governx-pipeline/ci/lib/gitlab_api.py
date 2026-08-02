"""Wrapper API REST GitLab pour les opérations du pipeline GovernX."""
from __future__ import annotations

import os
import sys
from typing import Any
from urllib.parse import quote, urlparse

import requests
from requests.adapters import HTTPAdapter

# Taille du pool de connexions : le stage create_project provisionne plusieurs
# projets en parallèle et partage le même client.
_POOL_SIZE = 20
_DEFAULT_TIMEOUT = 30.0


class GitLabAPIError(RuntimeError):
    """Réponse HTTP >= 400 renvoyée par l'API GitLab.

    Levée au lieu d'un `sys.exit()` afin que les appelants qui traitent
    plusieurs projets puissent isoler l'échec d'un projet sans interrompre
    les autres. Les `main()` la rattrapent et sortent en code 1.
    """

    def __init__(self, action: str, status_code: int, body: str) -> None:
        super().__init__(f"Échec de l'action '{action}' (Code HTTP {status_code}) : {body}")
        self.action = action
        self.status_code = status_code
        self.body = body


class GitLabAPIClient:
    """Client REST pour interagir avec l'API v4 de GitLab.

    Une instance est réutilisable depuis plusieurs threads : la session n'est
    jamais mutée après construction et le pool de connexions sous-jacent
    (urllib3) est thread-safe.
    """

    def __init__(self, server_url: str | None = None, token: str | None = None) -> None:
        raw_url = server_url or os.getenv("CI_SERVER_URL", "https://gitlab.com")
        self.server_url = raw_url.rstrip("/")
        self.token = token or os.getenv("GITLAB_API_TOKEN", "")

        if not self.token:
            sys.stderr.write(
                "Erreur critique : La variable d'environnement GITLAB_API_TOKEN est manquante.\n"
            )
            sys.exit(1)

        try:
            self.timeout = float(os.getenv("GITLAB_API_TIMEOUT", str(_DEFAULT_TIMEOUT)))
        except ValueError:
            self.timeout = _DEFAULT_TIMEOUT

        self.session = requests.Session()
        self.session.headers.update(
            {
                "PRIVATE-TOKEN": self.token,
                "Content-Type": "application/json",
            }
        )
        adapter = HTTPAdapter(pool_connections=_POOL_SIZE, pool_maxsize=_POOL_SIZE)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _handle_response(self, response: requests.Response, action_description: str) -> Any:
        """Vérifie le statut HTTP et retourne le JSON, ou lève GitLabAPIError."""
        if response.status_code >= 400:
            raise GitLabAPIError(action_description, response.status_code, response.text)
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    @staticmethod
    def _encode_id(project_path_or_id: str | int) -> str:
        if isinstance(project_path_or_id, str):
            return quote(project_path_or_id.strip("/"), safe="")
        return str(project_path_or_id)

    def get_group_id(self, group_path: str) -> int:
        """Récupère l'identifiant numérique (ID) d'un groupe GitLab via son chemin."""
        encoded_path = quote(group_path.strip("/"), safe="")
        url = f"{self.server_url}/api/v4/groups/{encoded_path}"
        response = self.session.get(url, timeout=self.timeout)
        data = self._handle_response(response, f"Récupération du groupe '{group_path}'")
        return int(data["id"])

    def get_project(self, project_path_or_id: str | int) -> dict[str, Any]:
        """Récupère les détails d'un projet GitLab via son chemin ou son ID."""
        url = f"{self.server_url}/api/v4/projects/{self._encode_id(project_path_or_id)}"
        response = self.session.get(url, timeout=self.timeout)
        return self._handle_response(response, f"Récupération du projet '{project_path_or_id}'")

    def search_templates_by_topic(self, template_group_path: str, topic: str) -> list[dict[str, Any]]:
        """Recherche tous les projets sous template_group_path associés au topic donné."""
        group_id = self.get_group_id(template_group_path)
        url = f"{self.server_url}/api/v4/groups/{group_id}/projects"
        params = {
            "include_subgroups": "true",
            "per_page": "100",
        }

        response = self.session.get(url, params=params, timeout=self.timeout)
        data = self._handle_response(
            response,
            f"Recherche des templates pour le topic '{topic}' dans le groupe '{template_group_path}'",
        )

        matches: list[dict[str, Any]] = []
        target_topic = topic.strip().lower()

        for project in data:
            topics = [t.lower() for t in project.get("topics", [])]
            tag_list = [t.lower() for t in project.get("tag_list", [])]
            if target_topic in topics or target_topic in tag_list:
                matches.append(project)

        if not matches and data:
            found_summary = ", ".join(
                f"{p['path_with_namespace']} (topics: {p.get('topics', [])})"
                for p in data
            )
            print(f"[search_templates_by_topic] Aucun match pour topic='{topic}'. Projets trouvés sous '{template_group_path}' : {found_summary}")

        return matches

    def create_project(self, name: str, path: str, namespace_id: int, description: str = "") -> dict[str, Any]:
        """Crée un nouveau projet GitLab vide dans le namespace spécifié."""
        url = f"{self.server_url}/api/v4/projects"
        payload = {
            "name": name,
            "path": path,
            "namespace_id": namespace_id,
            "initialize_with_readme": False,
            "description": description or f"Projet {name} généré automatiquement par GovernX",
        }
        response = self.session.post(url, json=payload, timeout=self.timeout)
        return self._handle_response(response, f"Création du projet '{name}' dans le groupe (ID: {namespace_id})")

    def update_project_topics(self, project_path_or_id: str | int, topics: list[str]) -> dict[str, Any]:
        """Met à jour la liste des topics (tags) d'un projet GitLab."""
        url = f"{self.server_url}/api/v4/projects/{self._encode_id(project_path_or_id)}"
        payload = {"topics": topics}
        response = self.session.put(url, json=payload, timeout=self.timeout)
        return self._handle_response(response, f"Mise à jour des tags pour le projet {project_path_or_id}")

    def list_repository_tree(
        self, project_path_or_id: str | int, ref: str, recursive: bool = True
    ) -> list[dict[str, Any]]:
        """Liste l'arborescence complète du dépôt (paginée) sur la ref donnée."""
        url = f"{self.server_url}/api/v4/projects/{self._encode_id(project_path_or_id)}/repository/tree"
        entries: list[dict[str, Any]] = []
        page = 1

        while True:
            response = self.session.get(
                url,
                params={
                    "ref": ref,
                    "recursive": "true" if recursive else "false",
                    "per_page": "100",
                    "page": str(page),
                },
                timeout=self.timeout,
            )
            batch = self._handle_response(
                response, f"Lecture de l'arborescence de {project_path_or_id} sur '{ref}'"
            )
            if not batch:
                break
            entries.extend(batch)

            next_page = response.headers.get("X-Next-Page", "").strip()
            if not next_page:
                break
            page = int(next_page)

        return entries

    def get_raw_file(self, project_path_or_id: str | int, file_path: str, ref: str) -> str:
        """Retourne le contenu brut d'un fichier du dépôt, décodé en UTF-8."""
        encoded_file = quote(file_path.lstrip("/"), safe="")
        url = (
            f"{self.server_url}/api/v4/projects/{self._encode_id(project_path_or_id)}"
            f"/repository/files/{encoded_file}/raw"
        )
        response = self.session.get(url, params={"ref": ref}, timeout=self.timeout)
        if response.status_code >= 400:
            raise GitLabAPIError(
                f"Lecture de '{file_path}' sur '{ref}' dans {project_path_or_id}",
                response.status_code,
                response.text,
            )
        return response.content.decode("utf-8")

    def create_commit(
        self,
        project_path_or_id: str | int,
        branch: str,
        commit_message: str,
        actions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Crée un commit via l'API (aucun clone local requis).

        `actions` suit le format GitLab : [{"action": "update", "file_path": ...,
        "content": ...}].
        """
        url = f"{self.server_url}/api/v4/projects/{self._encode_id(project_path_or_id)}/repository/commits"
        payload = {"branch": branch, "commit_message": commit_message, "actions": actions}
        response = self.session.post(url, json=payload, timeout=self.timeout)
        return self._handle_response(
            response, f"Commit sur '{branch}' dans {project_path_or_id}"
        )

    def create_protected_tag(
        self, project_path_or_id: str | int, pattern: str, create_access_level: int
    ) -> dict[str, Any]:
        """
        Crée une règle de protected tag GitLab : un pattern de nom de tag git
        (ex. 'my-artifact-*') associé à un niveau d'accès requis pour créer
        un tag git correspondant à ce pattern.

        create_access_level (valeurs API GitLab) : 0=No access, 30=Developer,
        40=Maintainer, 60=Admin.
        """
        url = f"{self.server_url}/api/v4/projects/{self._encode_id(project_path_or_id)}/protected_tags"
        payload = {"name": pattern, "create_access_level": create_access_level}
        response = self.session.post(url, json=payload, timeout=self.timeout)
        return self._handle_response(
            response, f"Création du protected tag '{pattern}' sur le projet {project_path_or_id}"
        )

    def get_authenticated_git_url(self, git_http_url: str) -> str:
        """Injecte le token d'API masqué/protégé dans l'URL HTTP du dépôt Git."""
        parsed = urlparse(git_http_url)
        scheme = parsed.scheme or "https"
        netloc = parsed.netloc

        if "@" in netloc:
            netloc = netloc.split("@", 1)[1]

        auth_netloc = f"oauth2:{self.token}@{netloc}"
        return f"{scheme}://{auth_netloc}{parsed.path}"
