# GovernX — Arborescence complète du projet

> Fichier généré automatiquement le 27 juillet 2026.
> Contient l'intégralité de l'arborescence et du code source du projet.

---

## Structure globale

```
governX/
├── GovernX.md                          # Doc vivante — état d'avancement (3 axes)
├── arborescence_complete.md            # Ce fichier
└── governx-pipeline/
    ├── .gitlab-ci.yml                  # Pipeline GitLab CI (3 stages, déclenchement web)
    ├── README.md                       # Documentation du pipeline
    ├── ci/
    │   ├── __init__.py
    │   ├── requirements.txt            # Dépendances Python : requests, python-gitlab
    │   ├── create_project.py           # Stage 1 : résolution template + git mirror clone/push (cross-instance)
    │   ├── configure_tags.py           # Stage 2 : topics déterministes (backend/batch/dependencie -> maven, frontend -> npm)
    │   ├── audit_check.py              # Stage 3 : audit conformité via audit_tool rules + auto-fix + rapport
    │   └── lib/
    │       ├── __init__.py
    │       └── gitlab_api.py           # Wrapper REST GitLab v4
    └── audit_tool/
        ├── .gitkeep
        ├── __init__.py                 # Module audit_tool — extract_project_name, run_audit (placeholder), scan_manifests
        ├── gitlab_client.py            # Helpers connexion/projet python-gitlab
        └── rules/
            ├── pipeline_success.py     # Règle/fix Pipelines must succeed
            ├── protected_branches.py   # Règle/fix protected branches (main, develop, release/*)
            └── protected_tags.py       # Règle/fix protected tags (* / v*, Owner)
```

---

## `governx-pipeline/.gitlab-ci.yml`

```yaml
# GovernX — Pipeline de création de projet (Axe 1)
# Déclenchement : manuel uniquement, via le formulaire "Run pipeline" de GitLab
stages:
  - create_project
  - configure_tags
  - audit_check

variables:
  PROJECT_NAME:
    description: "Nom du nouveau projet GitLab à créer"
  PROJECT_TYPE:
    description: "Type de projet"
    value: "backend"
    options:
      - "backend"
      - "frontend"
      - "batch"
      - "dependencie"
  GROUP_PATH:
    description: "Chemin du groupe GitLab cible (ex: nom-groupe/sous-groupe)"
  TEMPLATE_VARIANT:
    description: "Variante du template en cas de multi-match (optionnel, doit correspondre exactement au nom ou path du template)"
  AUDIT_AUTO_FIX:
    description: "Activer le mode correctif automatique de l'audit (yes/no)"
    value: "no"
    options:
      - "no"
      - "yes"
  AUDIT_ACCEPT_NONCOMPLIANT:
    description: "Accepter un projet non conforme sans bloquer le pipeline (yes/no)"
    value: "no"
    options:
      - "no"
      - "yes"

workflow:
  rules:
    - if: '$CI_PIPELINE_SOURCE == "web"'

default:
  image: python:3.11-slim
  tags:
    - docker
  before_script:
    - apt-get update -qq && apt-get install -y -qq git
    - pip install --quiet -r ci/requirements.txt

create_project:
  stage: create_project
  script:
    - python3 -m ci.create_project
  artifacts:
    reports:
      dotenv: create_project.env

configure_tags:
  stage: configure_tags
  needs:
    - job: create_project
      artifacts: true
  script:
    - python3 -m ci.configure_tags

audit_check:
  stage: audit_check
  needs:
    - job: create_project
      artifacts: true
    - job: configure_tags
  script:
    - python3 -m ci.audit_check
  artifacts:
    when: always
    paths:
      - reports/audit_report.*
```

---

## `governx-pipeline/README.md`

```markdown
# GovernX — Pipeline GitLab CI (Axe 1)

Ce dépôt contient le socle métier du pipeline GitLab CI pour l'automatisation de la création, du tagging et de l'audit des projets GitLab.

## Structure du projet

```
governx-pipeline/
├── .gitlab-ci.yml              # Pipeline GitLab CI (3 stages, déclenchement manuel web)
├── README.md                   # Documentation du projet
├── ci/
│   ├── __init__.py
│   ├── requirements.txt        # Dépendance Python (requests)
│   ├── create_project.py       # Stage 1 : Résolution template + git mirror clone/push
│   ├── configure_tags.py       # Stage 2 : Détection manifestes (pom.xml / package.json) + tagging API
│   ├── audit_check.py          # Stage 3 : Exécution audit + rapport + contrôle conformité
│   └── lib/
│       ├── __init__.py
│       └── gitlab_api.py       # Wrapper API REST GitLab v4
└── audit_tool/                 # Interface minimale stubbée d'audit
    └── __init__.py             # Expose scan_manifests() et run_audit()
```

## Variables CI/CD

### Variables de déclenchement (Formulaire "Run pipeline")
- `PROJECT_NAME` *(obligatoire)* : Nom du nouveau projet GitLab à créer.
- `PROJECT_TYPE` *(obligatoire)* : Type de projet (`backend` | `frontend` | `batch` | `dependencie`). Sert de topic pour la résolution du template.
- `GROUP_PATH` *(obligatoire)* : Chemin du groupe cible GitLab dans lequel créer le projet.
- `TEMPLATE_VARIANT` *(optionnel)* : Nom ou identifiant de la variante pour désambiguïser en cas de multi-match.
- `AUDIT_AUTO_FIX` *(optionnel, défaut: `no`)* : Active la correction automatique lors de l'audit (`yes`/`no`).
- `AUDIT_ACCEPT_NONCOMPLIANT` *(optionnel, défaut: `no`)* : Accepte un projet non-conforme sans bloquer le pipeline (`yes`/`no`).

### Variables de groupe GitLab (Infra / Secrètes)
- `TEMPLATE_GROUP_PATH` *(obligatoire)* : Chemin du groupe racine contenant tous les projets templates.
- `GITLAB_API_TOKEN` *(obligatoire)* : Token d'API GitLab (droits API et push Git).
```

---

## `governx-pipeline/ci/__init__.py`

```python
"""Module CI pour le pipeline GovernX."""
from __future__ import annotations
```

---

## `governx-pipeline/ci/requirements.txt`

```
requests>=2.31.0
python-gitlab>=4.0
```

---

## `governx-pipeline/ci/create_project.py`

```python
"""Stage 1 — Résolution de template et création de projet par git clone/push mirror.

Cross-instance (décision confirmée par l'encadrante, 24/07) :
- Les templates vivent sur gitlab.com, sous TEMPLATE_GROUP_PATH.
- Le nouveau projet est créé sur l'instance GitLab locale (celle qui exécute
  ce pipeline, via CI_SERVER_URL), sous GROUP_PATH.
Deux clients GitLabAPIClient distincts sont donc nécessaires, chacun avec son
propre serveur et son propre token :
- template_client -> gitlab.com, lecture seule (TEMPLATE_GITLAB_TOKEN)
- local_client     -> instance locale, écriture (GITLAB_API_TOKEN, existant)
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

from ci.lib.gitlab_api import GitLabAPIClient


class TemplateResolutionError(Exception):
    """Levée quand la résolution du template échoue (zéro ou multi-match non résolu)."""


def select_template(candidates: list[dict], project_type: str, variant: str | None) -> dict:
    """
    Sélectionne le template parmi les candidats trouvés par topic.

    - Zéro candidat -> échec dur.
    - Un seul candidat -> sélectionné directement.
    - Plusieurs candidats -> nécessite TEMPLATE_VARIANT, en égalité STRICTE
      (name ou path exact, pas de sous-chaîne — décision du 23/07).
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


def main() -> None:
    project_name = os.getenv("PROJECT_NAME", "").strip()
    project_type = os.getenv("PROJECT_TYPE", "").strip()
    group_path = os.getenv("GROUP_PATH", "").strip()
    template_group_path = os.getenv("TEMPLATE_GROUP_PATH", "").strip()
    template_variant = os.getenv("TEMPLATE_VARIANT", "").strip()
    template_gitlab_url = os.getenv("TEMPLATE_GITLAB_URL", "https://gitlab.com").strip()
    template_gitlab_token = os.getenv("TEMPLATE_GITLAB_TOKEN", "").strip()

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

    # Client "source" : gitlab.com, lecture seule des templates.
    template_client = GitLabAPIClient(server_url=template_gitlab_url, token=template_gitlab_token)
    # Client "destination" : instance locale (CI_SERVER_URL / GITLAB_API_TOKEN), écriture.
    local_client = GitLabAPIClient()

    print(f"Recherche des templates pour le topic '{project_type}' dans '{template_group_path}' sur {template_gitlab_url}...")
    candidates = template_client.search_templates_by_topic(template_group_path, project_type)

    try:
        selected_template = select_template(candidates, project_type, template_variant or None)
    except TemplateResolutionError as exc:
        sys.stderr.write(f"Erreur critique : {exc}\n")
        sys.exit(1)

    print(f"Template sélectionné : {selected_template['path_with_namespace']} (gitlab.com)")

    print(f"Récupération de l'ID du groupe cible '{group_path}' sur l'instance locale...")
    target_group_id = local_client.get_group_id(group_path)

    project_slug = slugify(project_name)
    print(f"Création du nouveau projet '{project_name}' (slug: {project_slug}) dans le groupe ID {target_group_id} (instance locale)...")
    new_project = local_client.create_project(
        name=project_name,
        path=project_slug,
        namespace_id=target_group_id,
        description=f"Projet {project_name} (type: {project_type}) initialisé depuis le template {selected_template['path_with_namespace']} (gitlab.com)",
    )

    new_project_path = new_project["path_with_namespace"]
    template_http_url = selected_template["http_url_to_repo"]
    new_project_http_url = new_project["http_url_to_repo"]

    # Authentification distincte : token gitlab.com pour le clone (source),
    # token instance locale pour le push (destination).
    auth_clone_url = template_client.get_authenticated_git_url(template_http_url)
    auth_push_url = local_client.get_authenticated_git_url(new_project_http_url)

    print("Exécution de git clone --mirror (gitlab.com) et git push --mirror (instance locale)...")
    with tempfile.TemporaryDirectory() as tmpdir:
        mirror_dir = os.path.join(tmpdir, "template.git")

        clone_cmd = ["git", "clone", "--mirror", auth_clone_url, mirror_dir]
        res_clone = subprocess.run(clone_cmd, capture_output=True, text=True)
        if res_clone.returncode != 0:
            sys.stderr.write(
                f"Erreur critique lors du clone --mirror du template (gitlab.com) : {res_clone.stderr}\n"
            )
            sys.exit(1)

        push_cmd = ["git", "push", "--mirror", auth_push_url]
        res_push = subprocess.run(push_cmd, cwd=mirror_dir, capture_output=True, text=True)
        if res_push.returncode != 0:
            sys.stderr.write(
                f"Erreur critique lors du push --mirror vers le nouveau projet (instance locale) : {res_push.stderr}\n"
            )
            sys.exit(1)

    print(f"Projet créé et initialisé avec succès : {new_project_path}")

    dotenv_filename = "create_project.env"
    with open(dotenv_filename, "w", encoding="utf-8") as f:
        f.write(f"NEW_PROJECT_PATH={new_project_path}\n")
        f.write(f"NEW_PROJECT_HTTP_URL={new_project_http_url}\n")

    print(f"Artifact dotenv '{dotenv_filename}' généré avec NEW_PROJECT_PATH={new_project_path}.")


if __name__ == "__main__":
    main()
```

---

## `governx-pipeline/ci/configure_tags.py`

```python
"""Stage 2 — Application des topics GitLab sur le projet importé.

Le protected tag n'est plus créé ici (déplacé vers audit_check.py, décision
du 24/07 : réutiliser la logique/règles réelles du audit_tool CIH plutôt que
la logique ad-hoc {nom}-*/Maintainer construite précédemment dans ce fichier).
"""
from __future__ import annotations

import os
import sys

from ci.lib.gitlab_api import GitLabAPIClient

# Mapping figé (Q1 révisée le 24/07) : chaque PROJECT_TYPE correspond à
# exactement un stack, aucune ambiguïté possible.
STACK_TAG = {
    "backend": "maven",
    "batch": "maven",
    "dependencie": "maven",
    "frontend": "npm",
}


def resolve_topics(project_type: str) -> list[str]:
    """Topics à appliquer : déterministes depuis PROJECT_TYPE, pas de scan requis."""
    tags = [project_type]
    stack = STACK_TAG.get(project_type)
    if stack:
        tags.append(stack)
    return tags


def main() -> None:
    new_project_path = os.getenv("NEW_PROJECT_PATH", "").strip()
    project_type = os.getenv("PROJECT_TYPE", "").strip()

    if not new_project_path:
        sys.stderr.write(
            "Erreur critique : La variable NEW_PROJECT_PATH est absente. Le stage create_project a-t-il réussi ?\n"
        )
        sys.exit(1)

    if project_type not in STACK_TAG:
        sys.stderr.write(
            f"Erreur critique : PROJECT_TYPE='{project_type}' inconnu. "
            f"Valeurs valides : {sorted(STACK_TAG)}.\n"
        )
        sys.exit(1)

    client = GitLabAPIClient()
    topics = resolve_topics(project_type)
    print(f"Application des topics {topics} sur le projet '{new_project_path}'...")
    client.update_project_topics(new_project_path, topics)
    print("Topics configurés avec succès.")


if __name__ == "__main__":
    main()
```

---

## `governx-pipeline/ci/audit_check.py`

```python
"""Stage 3 — Audit de conformité du projet importé.


Règles vérifiées : protected_branches, protected_tags, pipeline_success.
specific_user_access est explicitement HORS SCOPE ici (concerne un
utilisateur donné appliqué à tous les projets, pas la conformité du
projet importé lui-même).
"""
from __future__ import annotations

import json
import os
import sys

from audit_tool.gitlab_client import get_gitlab_connection, get_project
from audit_tool.rules.pipeline_success import check_pipeline_success, fix_pipeline_success
from audit_tool.rules.protected_branches import check_protected_branches, fix_protected_branches
from audit_tool.rules.protected_tags import check_protected_tags, fix_protected_tags


def run_checks(project) -> list[dict]:
    results: list[dict] = []
    results.extend(check_protected_branches(project))
    results.append(check_protected_tags(project))
    results.append(check_pipeline_success(project))
    return results


def apply_fixes(project, results: list[dict]) -> list[dict]:
    fixes: list[dict] = []
    for r in results:
        if r["compliant"]:
            continue
        if r["rule"] == "protected_branches":
            fixes.append(fix_protected_branches(project, r["branch"]))
        elif r["rule"] == "protected_tags":
            fixes.append(fix_protected_tags(project, r))
        elif r["rule"] == "pipeline_success":
            fixes.append(fix_pipeline_success(project))
    return fixes


def write_reports(reports_dir: str, report: dict) -> tuple[str, str]:
    json_path = os.path.join(reports_dir, "audit_report.json")
    txt_path = os.path.join(reports_dir, "audit_report.txt")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("=== RAPPORT D'AUDIT GOVERNX ===\n")
        f.write(f"Projet: {report['project']}\n")
        f.write(f"Conforme: {'OUI' if report['compliant'] else 'NON'}\n")
        f.write(f"Auto-fix demandé: {report['auto_fix_applied']}\n")
        f.write(f"Acceptation non-conforme: {report['accepted_noncompliant']}\n\n")
        for r in report["results"]:
            label = r.get("branch") or r["rule"]
            status = "OK" if r["compliant"] else "NON"
            f.write(f"[{status}] {r['rule']} ({label}) — {r['details']}\n")

    return json_path, txt_path


def main() -> None:
    new_project_path = os.getenv("NEW_PROJECT_PATH", "").strip()
    server_url = os.getenv("CI_SERVER_URL", "").strip()
    token = os.getenv("GITLAB_API_TOKEN", "").strip()
    audit_auto_fix = os.getenv("AUDIT_AUTO_FIX", "no").strip().lower() in ("yes", "true", "1")
    accept_noncompliant = os.getenv("AUDIT_ACCEPT_NONCOMPLIANT", "no").strip().lower() in ("yes", "true", "1")

    if not new_project_path:
        sys.stderr.write(
            "Erreur critique : La variable NEW_PROJECT_PATH est absente. Le stage create_project a-t-il réussi ?\n"
        )
        sys.exit(1)
    if not server_url or not token:
        sys.stderr.write("Erreur critique : CI_SERVER_URL ou GITLAB_API_TOKEN manquant.\n")
        sys.exit(1)

    gl = get_gitlab_connection(server_url, token)
    project = get_project(gl, new_project_path)

    reports_dir = os.path.abspath("reports")
    os.makedirs(reports_dir, exist_ok=True)

    results = run_checks(project)

    fixes: list[dict] = []
    if audit_auto_fix:
        fixes = apply_fixes(project, results)
        results = run_checks(project)  # re-vérifie après correctifs pour un rapport à jour

    is_compliant = all(r["compliant"] for r in results)

    report = {
        "project": new_project_path,
        "compliant": is_compliant,
        "auto_fix_applied": audit_auto_fix,
        "accepted_noncompliant": accept_noncompliant,
        "results": results,
        "fixes": fixes,
    }

    json_path, txt_path = write_reports(reports_dir, report)
    print(f"Rapport d'audit généré dans '{json_path}' et '{txt_path}'.")

    if is_compliant:
        print("Audit de conformité réussi.")
        sys.exit(0)

    if accept_noncompliant:
        print("ATTENTION : Le projet est non-conforme, mais le pipeline continue car AUDIT_ACCEPT_NONCOMPLIANT=yes.")
        sys.exit(0)

    sys.stderr.write(
        "Erreur critique : Le projet ne respecte pas les critères de conformité audit "
        "et AUDIT_ACCEPT_NONCOMPLIANT n'est pas activé (yes). Pipeline bloqué.\n"
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
```

---

## `governx-pipeline/ci/lib/__init__.py`

```python
"""Bibliothèque de helpers API et outils pour la CI GovernX."""
from __future__ import annotations
```

---

## `governx-pipeline/ci/lib/gitlab_api.py`

```python
"""Wrapper API REST GitLab pour les opérations du pipeline GovernX."""
from __future__ import annotations

import os
import sys
from typing import Any
from urllib.parse import quote, urlparse

import requests


class GitLabAPIClient:
    """Client REST pour interagir avec l'API v4 de GitLab."""

    def __init__(self, server_url: str | None = None, token: str | None = None) -> None:
        raw_url = server_url or os.getenv("CI_SERVER_URL", "https://gitlab.com")
        self.server_url = raw_url.rstrip("/")
        self.token = token or os.getenv("GITLAB_API_TOKEN", "")

        if not self.token:
            sys.stderr.write(
                "Erreur critique : La variable d'environnement GITLAB_API_TOKEN est manquante.\n"
            )
            sys.exit(1)

        self.session = requests.Session()
        self.session.headers.update(
            {
                "PRIVATE-TOKEN": self.token,
                "Content-Type": "application/json",
            }
        )

    def _handle_response(self, response: requests.Response, action_description: str) -> Any:
        """Vérifie le statut HTTP et retourne le JSON ou lève une erreur sur stderr."""
        if response.status_code >= 400:
            sys.stderr.write(
                f"Échec de l'action '{action_description}' (Code HTTP {response.status_code}) : {response.text}\n"
            )
            sys.exit(1)
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    def get_group_id(self, group_path: str) -> int:
        """Récupère l'identifiant numérique (ID) d'un groupe GitLab via son chemin."""
        encoded_path = quote(group_path.strip("/"), safe="")
        url = f"{self.server_url}/api/v4/groups/{encoded_path}"
        response = self.session.get(url)
        data = self._handle_response(response, f"Récupération du groupe '{group_path}'")
        return int(data["id"])

    def get_project(self, project_path_or_id: str | int) -> dict[str, Any]:
        """Récupère les détails d'un projet GitLab via son chemin ou son ID."""
        if isinstance(project_path_or_id, str):
            encoded_id = quote(project_path_or_id.strip("/"), safe="")
        else:
            encoded_id = str(project_path_or_id)

        url = f"{self.server_url}/api/v4/projects/{encoded_id}"
        response = self.session.get(url)
        return self._handle_response(response, f"Récupération du projet '{project_path_or_id}'")

    def search_templates_by_topic(self, template_group_path: str, topic: str) -> list[dict[str, Any]]:
        """Recherche tous les projets sous template_group_path associés au topic donné."""
        group_id = self.get_group_id(template_group_path)
        url = f"{self.server_url}/api/v4/groups/{group_id}/projects"
        params = {
            "include_subgroups": "true",
            "per_page": "100",
        }

        response = self.session.get(url, params=params)
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
        response = self.session.post(url, json=payload)
        return self._handle_response(response, f"Création du projet '{name}' dans le groupe (ID: {namespace_id})")

    def update_project_topics(self, project_path_or_id: str | int, topics: list[str]) -> dict[str, Any]:
        """Met à jour la liste des topics (tags) d'un projet GitLab."""
        if isinstance(project_path_or_id, str):
            encoded_id = quote(project_path_or_id.strip("/"), safe="")
        else:
            encoded_id = str(project_path_or_id)

        url = f"{self.server_url}/api/v4/projects/{encoded_id}"
        payload = {"topics": topics}
        response = self.session.put(url, json=payload)
        return self._handle_response(response, f"Mise à jour des tags pour le projet {project_path_or_id}")

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
        if isinstance(project_path_or_id, str):
            encoded_id = quote(project_path_or_id.strip("/"), safe="")
        else:
            encoded_id = str(project_path_or_id)

        url = f"{self.server_url}/api/v4/projects/{encoded_id}/protected_tags"
        payload = {"name": pattern, "create_access_level": create_access_level}
        response = self.session.post(url, json=payload)
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
```

---

## `governx-pipeline/audit_tool/__init__.py`

```python
"""audit_tool — logique métier partagée par configure_tags.py et audit_check.py.

scan_manifests et run_audit restent des stubs (voir doc GovernX.md, décision #8 :
pas de fallback tant que la logique réelle n'existe pas). extract_project_name
est implémentée (décision #11 du 24/07 : mapping PROJECT_TYPE -> manifeste
déterministe, plus d'ambiguïté à détecter).
"""
from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from typing import Any

# Mapping figé (Q1 révisée le 24/07, cf. GovernX.md décision #10) :
# chaque PROJECT_TYPE correspond à exactement un manifeste attendu.
EXPECTED_MANIFEST = {
    "backend": "pom.xml",
    "batch": "pom.xml",
    "dependencie": "pom.xml",
    "frontend": "package.json",
}


def scan_manifests(project_path: str) -> dict[str, bool]:
    """Scanne le projet spécifié à la recherche des manifestes pom.xml et package.json.

    Args:
        project_path: Chemin local du répertoire du projet.

    Returns:
        Dictionnaire indiquant la présence des manifestes (ex. {"maven": True, "npm": False}).

    Raises:
        NotImplementedError: Tant que l'implémentation réelle n'est pas disponible.
    """
    raise NotImplementedError(
        "L'interface audit_tool.scan_manifests n'est pas encore implémentée."
    )


def run_audit(project_path: str, auto_fix: bool = False) -> dict[str, Any]:
    """Exécute les contrôles d'audit de conformité sur le projet.

    ⚠️ PLACEHOLDER : les vrais critères de conformité CIH Bank ne sont pas
    encore définis (cf. GovernX.md, "Prochaine étape"). Cette implémentation
    minimale vérifie uniquement la présence d'un README.md, juste pour que
    le pipeline puisse tourner de bout en bout. À REMPLACER dès que les
    vrais critères métier sont connus — ne pas considérer ce comportement
    comme la spec finale de l'audit.

    Args:
        project_path: Chemin local du projet à auditer.
        auto_fix: Si True et README.md manquant, le crée automatiquement
            (seul "fix" implémenté pour l'instant).

    Returns:
        Dictionnaire avec au moins "compliant" (bool), "issues" (liste des
        problèmes non corrigés), "fixed" (liste des corrections appliquées).
    """
    issues: list[str] = []
    fixed: list[str] = []

    readme_path = os.path.join(project_path, "README.md")
    if not os.path.isfile(readme_path):
        if auto_fix:
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write("# Projet\n\nGénéré automatiquement par GovernX.\n")
            fixed.append("README.md créé automatiquement (AUDIT_AUTO_FIX=yes)")
        else:
            issues.append("README.md manquant à la racine du projet")

    return {
        "compliant": len(issues) == 0,
        "issues": issues,
        "fixed": fixed,
        "auto_fix_applied": auto_fix,
        "details": "Audit placeholder — critères réels à définir avec CIH (cf. GovernX.md).",
    }


def _extract_maven_artifact_id(manifest_path: str) -> tuple[str | None, str]:
    """Extrait <artifactId> à la racine d'un pom.xml (jamais une dépendance imbriquée)."""
    try:
        tree = ET.parse(manifest_path)
    except ET.ParseError as exc:
        return None, f"pom.xml illisible (XML invalide) : {exc}"

    root = tree.getroot()
    # Gère le namespace Maven par défaut (xmlns="http://maven.apache.org/POM/4.0.0").
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    # root.find() sans './/' ne cherche que les enfants directs de la racine,
    # donc ça ne remonte jamais l'artifactId d'une <dependency> imbriquée.
    artifact_id_el = root.find(f"{ns}artifactId")
    if artifact_id_el is None or not (artifact_id_el.text or "").strip():
        return None, "pom.xml sans <artifactId> au niveau racine du projet"

    return artifact_id_el.text.strip(), "manifest"


def _extract_npm_name(manifest_path: str) -> tuple[str | None, str]:
    """Extrait le champ "name" d'un package.json."""
    try:
        with open(manifest_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"package.json illisible (JSON invalide) : {exc}"

    name = data.get("name")
    if not name or not str(name).strip():
        return None, "package.json sans champ 'name'"

    return str(name).strip(), "manifest"


_EXTRACTORS = {
    "pom.xml": _extract_maven_artifact_id,
    "package.json": _extract_npm_name,
}


def extract_project_name(project_type: str, repo_path: str) -> tuple[str | None, str]:
    """Extrait le nom "métier" du projet (artifactId Maven ou name npm) depuis
    le manifeste attendu pour ce PROJECT_TYPE (cf. EXPECTED_MANIFEST).

    Args:
        project_type: Type de projet (backend/batch/dependencie/frontend).
        repo_path: Chemin local du repo cloné.

    Returns:
        Tuple (name, reason) :
        - (nom, "manifest") si l'extraction a réussi.
        - (None, raison_lisible) si le manifeste attendu est absent, illisible
          ou sans le champ requis — à l'appelant de décider du repli. Jamais
          d'exception non gérée : toute cause d'échec est retournée explicitement.
    """
    manifest_filename = EXPECTED_MANIFEST.get(project_type)
    if manifest_filename is None:
        return None, f"PROJECT_TYPE='{project_type}' inconnu du mapping EXPECTED_MANIFEST"

    manifest_path = os.path.join(repo_path, manifest_filename)
    if not os.path.isfile(manifest_path):
        return None, (
            f"'{manifest_filename}' absent à la racine du projet "
            f"(attendu pour PROJECT_TYPE='{project_type}')"
        )

    extractor = _EXTRACTORS[manifest_filename]
    return extractor(manifest_path)
```

---

## `governx-pipeline/audit_tool/gitlab_client.py`

```python
"""audit_tool.gitlab_client — connexion GitLab et récupération du projet à auditer.

Version adaptée pour GovernX (Axe 1) : le audit_tool CIH original (projet
séparé, cf. projet_audit_gitlab_cih.md) scanne toute l'instance GitLab.
Ici, la même logique/règles sont appliquées à un seul projet : celui créé
par create_project.py (décision du 24/07).
"""
from __future__ import annotations

import gitlab


def get_gitlab_connection(url: str, token: str) -> gitlab.Gitlab:
    """Ouvre et authentifie une connexion python-gitlab."""
    gl = gitlab.Gitlab(url, private_token=token)
    gl.auth()
    return gl


def get_project(gl: gitlab.Gitlab, project_path: str):
    """Récupère l'objet Project (python-gitlab) pour le projet audité."""
    return gl.projects.get(project_path)
```

---

## `governx-pipeline/audit_tool/rules/pipeline_success.py`

```python
"""Règle pipeline_success — vérifie que 'Pipelines must succeed' est activé
pour les merge requests (only_allow_merge_if_pipeline_succeeds)."""
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
```

---

## `governx-pipeline/audit_tool/rules/protected_branches.py`

```python
"""Règle protected_branches — main/develop/release/* avec niveaux d'accès attendus.

⚠️ Les niveaux exacts pour main/develop sont reconstruits à partir des logs de
test du audit_tool CIH (projet_audit_gitlab_cih.md : "main = Maintainers",
"develop/release/* = Developers + Maintainers, push = Maintainers partout"),
pas du code source littéral (non fourni dans le doc). La règle release/* est
en revanche explicitement spécifiée (merge=Developer+Maintainer, push=Maintainer).
À vérifier/ajuster si ça ne correspond pas exactement à l'implémentation CIH réelle.
"""
from __future__ import annotations

from typing import Any

MAINTAINER = 40
DEVELOPER = 30

# branche -> (niveau merge attendu, niveau push attendu)
# Un access_level est un SEUIL, pas une liste : 30 = "Developer et au-dessus"
# (donc Maintainer inclus automatiquement), pas besoin de lister {30, 40}.
BRANCH_RULES: dict[str, tuple[int, int]] = {
    "main": (MAINTAINER, MAINTAINER),
    "develop": (DEVELOPER, MAINTAINER),
    "release/*": (DEVELOPER, MAINTAINER),
}


def check_protected_branches(project: Any) -> list[dict]:
    try:
        protected = {b.name: b for b in project.protectedbranches.list(get_all=True)}
    except Exception as exc:
        return [_result(project, branch, False, f"Erreur API : {exc}") for branch in BRANCH_RULES]

    results = []
    for branch, (merge_expected, push_expected) in BRANCH_RULES.items():
        pb = protected.get(branch)
        if pb is None:
            results.append(_result(project, branch, False, f"Branche '{branch}' non protégée"))
            continue

        merge_actual = {lvl["access_level"] for lvl in pb.merge_access_levels}
        push_actual = {lvl["access_level"] for lvl in pb.push_access_levels}

        problems = []
        if merge_actual != {merge_expected}:
            problems.append(f"merge access {sorted(merge_actual)} != attendu [{merge_expected}]")
        if push_actual != {push_expected}:
            problems.append(f"push access {sorted(push_actual)} != attendu [{push_expected}]")

        results.append(_result(project, branch, not problems, "; ".join(problems) or "OK"))

    return results


def fix_protected_branches(project: Any, branch: str, dry_run: bool = False) -> dict:
    """Fix (tier "free") : supprime la règle existante puis la recrée avec les
    niveaux attendus — l'API de base ne permet pas de PATCH partiellement les
    access levels d'une protected branch."""
    if branch not in BRANCH_RULES:
        return _fix_result(
            project, branch, f"Branche '{branch}' hors du périmètre des règles connues",
            dry_run=dry_run, success=False, details="branche non gérée",
        )

    merge_expected, push_expected = BRANCH_RULES[branch]
    action = (
        f"Reconfigurer la protection de '{branch}' "
        f"(merge={merge_expected}, push={push_expected})"
    )

    if dry_run:
        return _fix_result(project, branch, action, dry_run=True, success=True, details="dry-run")

    try:
        try:
            existing = project.protectedbranches.get(branch)
            existing.delete()
        except Exception:
            pass  # pas de règle existante, rien à supprimer

        project.protectedbranches.create({
            "name": branch,
            "merge_access_level": merge_expected,
            "push_access_level": push_expected,
        })
    except Exception as exc:
        return _fix_result(project, branch, action, dry_run=False, success=False, details=f"Erreur API : {exc}")

    return _fix_result(project, branch, action, dry_run=False, success=True, details="OK")


def _result(project: Any, branch: str, compliant: bool, details: str) -> dict:
    return {
        "rule": "protected_branches",
        "project": project.path_with_namespace,
        "branch": branch,
        "compliant": compliant,
        "details": details,
    }


def _fix_result(project: Any, branch: str, action: str, *, dry_run: bool, success: bool, details: str) -> dict:
    return {
        "rule": "protected_branches",
        "project": project.path_with_namespace,
        "branch": branch,
        "action": action,
        "dry_run": dry_run,
        "success": success,
        "details": details,
    }
```

---

## `governx-pipeline/audit_tool/rules/protected_tags.py`

```python
"""Règle protected_tags — détection dynamique du pattern de version attendu
(Maven "*" / npm "v*") et vérification/application de la règle GitLab
correspondante (create_access_level = Owner uniquement).

Logique reprise du audit_tool CIH (projet séparé, cf. projet_audit_gitlab_cih.md),
appliquée ici à un seul projet (celui créé par create_project.py) plutôt qu'à
toute l'instance.
"""
from __future__ import annotations

from typing import Any

# "Allowed to create" = Owner uniquement — convention confirmée par les tests
# CIH (validation manuelle sur un projet test-maven, cf. doc source).
OWNER_ACCESS_LEVEL = 60


def detect_version_pattern(project: Any) -> tuple[str | None, str | None]:
    """
    Détecte le pattern de tag protégé attendu selon le stack du projet, en
    cherchant pom.xml/package.json dans TOUTE l'arborescence via l'API (pas
    seulement la racine — bug connu côté CIH : un scan root-only rate les
    manifestes en sous-dossier, ex. my-app/pom.xml). Aucun clone local requis.

    Returns:
        ("*", "maven"), ("v*", "npm"), ou (None, None) si aucun manifeste trouvé.
    """
    default_branch = project.default_branch or "main"
    try:
        tree = project.repository_tree(ref=default_branch, recursive=True, get_all=True)
    except Exception:
        return None, None

    filenames = {item["path"].rsplit("/", 1)[-1] for item in tree if item.get("type") == "blob"}

    if "pom.xml" in filenames:
        return "*", "maven"
    if "package.json" in filenames:
        return "v*", "npm"
    return None, None


def check_protected_tags(project: Any) -> dict:
    """Vérifie qu'un protected tag existe pour le pattern attendu, en Owner-only."""
    pattern, stack = detect_version_pattern(project)

    if pattern is None:
        return _result(project, False, "Aucun pom.xml/package.json détecté — pattern indéterminé", None, None)

    try:
        protected_tags = project.protectedtags.list(get_all=True)
    except Exception as exc:
        return _result(project, False, f"Erreur API lecture protected tags : {exc}", pattern, stack)

    matching = [t for t in protected_tags if t.name == pattern]
    if not matching:
        return _result(
            project, False,
            f"Aucun protected tag avec le pattern '{pattern}' (attendu pour un projet {stack})",
            pattern, stack,
        )

    levels = {lvl["access_level"] for lvl in matching[0].create_access_levels}
    if levels != {OWNER_ACCESS_LEVEL}:
        return _result(
            project, False,
            f"Protected tag '{pattern}' existe mais create_access_level != Owner (trouvé : {sorted(levels)})",
            pattern, stack,
        )

    return _result(project, True, "OK", pattern, stack)


def fix_protected_tags(project: Any, check_result: dict, dry_run: bool = False) -> dict:
    """Crée le protected tag manquant/incorrect avec create_access_level = Owner.

    L'API GitLab ne permet pas de PATCH le niveau d'accès d'une règle
    existante : si un tag avec ce pattern existe déjà mais avec le mauvais
    niveau, on le supprime puis on le recrée.
    """
    pattern = check_result.get("pattern")
    if pattern is None:
        return _fix_result(
            project, "Aucune action possible : pattern de version indéterminé",
            dry_run=dry_run, success=False, details="manifeste absent",
        )

    action = f"Créer un protected tag pattern='{pattern}' (create_access_level=Owner)"

    if dry_run:
        return _fix_result(project, action, dry_run=True, success=True, details="dry-run, aucune écriture réelle")

    try:
        existing = [t for t in project.protectedtags.list(get_all=True) if t.name == pattern]
        for t in existing:
            t.delete()
        project.protectedtags.create({"name": pattern, "create_access_level": OWNER_ACCESS_LEVEL})
    except Exception as exc:
        return _fix_result(project, action, dry_run=False, success=False, details=f"Erreur API : {exc}")

    return _fix_result(project, action, dry_run=False, success=True, details="OK")


def _result(project: Any, compliant: bool, details: str, pattern: str | None, stack: str | None) -> dict:
    return {
        "rule": "protected_tags",
        "project": project.path_with_namespace,
        "compliant": compliant,
        "details": details,
        "pattern": pattern,
        "project_type": stack,
    }


def _fix_result(project: Any, action: str, *, dry_run: bool, success: bool, details: str) -> dict:
    return {
        "rule": "protected_tags",
        "project": project.path_with_namespace,
        "action": action,
        "dry_run": dry_run,
        "success": success,
        "details": details,
    }
```

---

## Fichiers ignorés (non reproduits)

| Fichier / Dossier | Raison |
|---|---|
| `governx-pipeline/audit_tool/.gitkeep` | Fichier vide de marquage Git |
| `governx-pipeline/ci/__pycache__/` | Cache Python généré automatiquement |
| `governx-pipeline/ci/lib/__pycache__/` | Cache Python généré automatiquement |
| `governx-pipeline/audit_tool/__pycache__/` | Cache Python généré automatiquement |
| `governx-pipeline/audit_tool/rules/__pycache__/` | Cache Python généré automatiquement |
