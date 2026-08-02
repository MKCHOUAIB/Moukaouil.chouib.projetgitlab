# 📚 Documentation Complète, Arborescence et Code Source du Projet

Ce document rassemble la documentation exhaustive, l'arborescence structurée et l'intégralité du code source des deux projets composants la solution de gouvernance GitLab : **`Audit-tool-test`** et **`governx-f-test`**.

---

# 📑 TABLE DES MATIÈRES
1. [Présentation et Vue d'Ensemble du Projet Final](#1-présentation-et-vue-densemble-du-projet-final)
2. [Arborescence Complète du Dépôt](#2-arborescence-complète-du-dépôt)
3. [Code Source Complet — Projet 1 : Audit-tool-test](#3-code-source-complet--projet-1--audit-tool-test)
4. [Code Source Complet — Projet 2 : governx-f-test](#4-code-source-complet--projet-2--governx-f-test)
5. [Guide d'Exécution et Validation](#5-guide-dexécution-et-validation)

---

# 1. 🌟 Présentation et Vue d'Ensemble du Projet Final

Le projet **GovernX / Audit GitLab CIH** est une solution complète de DevSecOps et de gouvernance logicielle. Elle répond aux exigences bancaires de contrôle, de sécurité et d'automatisation du cycle de vie des dépôts Git au sein de l'instance GitLab de CIH Bank.

### 🏛️ Les deux composantes majeures :

1. **`Audit-tool-test` (`audit-gitlab-cih`)** :
   - **Rôle** : Outil CLI autonome en Python (utilisant `python-gitlab`).
   - **Usage** : Audit de conformité des projets GitLab existants ou nouvellement créés et remédiation automatique des non-conformités (`--fix` et `--dry-run`).
   - **Portée** : Contrôle des branches protégées (`main`, `develop`, `release/*`), des tags de version, de la réussite des pipelines et des accès utilisateurs spécifiques (CE/Free vs EE/Premium).

2. **`governx-f-test` (`GovernX — Pipeline GitLab CI / Axe 1`)** :
   - **Rôle** : Orchestrateur automatisé de création et d'audit de projets par pipeline GitLab CI (`.gitlab-ci.yml`).
   - **Workflow à 3 Stages** :
     - **`create_project`** : Instancie un ou plusieurs projets en parallèle (`MAX_PARALLEL_PROJECTS`), effectue un *mirror clone/push* depuis le template et réécrit l'identifiant du manifeste (`artifactId` Maven ou `name` npm) en kebab-case.
     - **`configure_tags`** : Applique les métadonnées et catégories (topics : `backend`, `frontend`, `batch`, `dependencie`).
     - **`audit_check`** : Exécute l'audit de conformité, applique les correctifs si `AUDIT_AUTO_FIX=yes` et génère les rapports multi-formats (`JSON`, `TXT`, `HTML`).

---

# 2. 🌳 Arborescence Complète du Dépôt

```text
projet-final/
├── README.md
├── rapport_projet_governx.tex
├── DOCUMENTATION_ET_CODE_COMPLET.md
│
├── Audit-tool-test/
│   ├── .gitignore
│   ├── .gitlab-ci.yml
│   ├── README.md
│   ├── pyproject.toml
│   ├── projet_audit_gitlab_cih.md
│   └── audit_tool/
│       ├── __init__.py
│       ├── fixes.py
│       ├── gitlab_client.py
│       ├── main.py
│       ├── report.py
│       └── rules/
│           ├── pipeline_success.py
│           ├── protected_branches.py
│           ├── protected_tags.py
│           └── specific_user_access.py
│
└── governx-f-test/
    ├── .gitignore
    ├── GovernX.md
    ├── README.md
    ├── arborescence_complete.md
    └── governx-pipeline/
        ├── .gitlab-ci.yml
        ├── README.md
        ├── audit_tool/
        │   ├── .gitkeep
        │   ├── __init__.py
        │   ├── gitlab_client.py
        │   ├── manifest.py
        │   ├── report_html.py
        │   └── rules/
        │       ├── pipeline_success.py
        │       ├── protected_branches.py
        │       └── protected_tags.py
        ├── ci/
        │   ├── __init__.py
        │   ├── audit_check.py
        │   ├── configure_tags.py
        │   ├── create_project.py
        │   ├── requirements.txt
        │   ├── requirements-dev.txt
        │   └── lib/
        │       ├── __init__.py
        │       ├── gitlab_api.py
        │       └── projects.py
        └── tests/
            ├── __init__.py
            ├── conftest.py
            ├── test_create_project_rename.py
            ├── test_manifest.py
            └── test_protected_tags.py
```

---

# 3. 💻 Code Source Complet — Projet 1 : Audit-tool-test

### 📄 `Audit-tool-test/.gitignore`
```gitignore
__pycache__/
*.pyc
.env
reports/
.cache/
```

### 📄 `Audit-tool-test/pyproject.toml`
```toml
[project]
name = "audit-gitlab-cih"
version = "1.0.0"
description = "Outil d'audit de conformité GitLab pour CIH Bank"
requires-python = ">=3.11"
dependencies = [
    "python-gitlab==8.4.0",
    "python-dotenv==1.2.2",
]
```

### 📄 `Audit-tool-test/.gitlab-ci.yml`
```yaml
stages:
  - audit

variables:
  GITLAB_AUDIT_URL:
    description: "URL de l'instance GitLab à auditer"
  GITLAB_AUDIT_TOKEN:
    description: "Token GitLab avec scope 'api'"
  GITLAB_AUDIT_USER_ID:
    description: "ID(s) ou username(s) séparés par des virgules"
  AUDIT_TIER:
    value: "free"
    options: ["free", "premium"]
  AUDIT_FIX:
    value: "false"
    options: ["false", "true"]
  AUDIT_DRY_RUN:
    value: "true"
    options: ["true", "false"]

  PYTHONUNBUFFERED: "1"
  PIP_DISABLE_PIP_VERSION_CHECK: "1"
  PIP_CACHE_DIR: "$CI_PROJECT_DIR/.cache/pip"

audit_gitlab_cih:
  stage: audit
  image: python:3.11-slim
  tags:
    - docker
  timeout: 1h
  before_script:
    - pip install "python-gitlab==8.4.0" "python-dotenv==1.2.2"
  script:
    - |
      set -eu
      if [ -z "${GITLAB_AUDIT_URL:-}" ] || [ -z "${GITLAB_AUDIT_TOKEN:-}" ]; then
        echo "❌ Variables d'URL ou TOKEN manquantes."
        exit 1
      fi
      set -- --url "$GITLAB_AUDIT_URL" --token "$GITLAB_AUDIT_TOKEN" --tier "${AUDIT_TIER:-free}"
      if [ -n "${GITLAB_AUDIT_USER_ID:-}" ]; then set -- "$@" --user-id "$GITLAB_AUDIT_USER_ID"; fi
      if [ "${AUDIT_FIX:-false}" = "true" ]; then
        set -- "$@" --fix
        if [ "${AUDIT_DRY_RUN:-true}" = "true" ]; then set -- "$@" --dry-run; fi
      fi
      python -m audit_tool.main "$@"
  artifacts:
    name: "audit-gitlab-$CI_PIPELINE_ID"
    paths:
      - reports/
    expire_in: 30 days
    when: always
```

### 📄 `Audit-tool-test/audit_tool/main.py`
```python
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
            raise ValueError(f"entrée '{entry}' : access_type '{access_type}' invalide")
        branches[name] = access_type
    return branches


def parse_args():
    parser = argparse.ArgumentParser(description="Audit de conformité GitLab CE/EE")
    parser.add_argument("--url", required=True, help="URL de l'instance GitLab")
    parser.add_argument("--token", required=True, help="Token GitLab API")
    parser.add_argument("--user-id", type=str, default=None, help="ID(s) ou username(s)")
    parser.add_argument("--fix", action="store_true", help="Active la remédiation")
    parser.add_argument("--dry-run", action="store_true", help="Simule les corrections")
    parser.add_argument("--tier", choices=["free", "premium"], default="free")
    parser.add_argument("--user-branches", type=str, default=None)
    return parser.parse_args()


\def run_audit(gitlab_url, gitlab_token, user_identifiers=None, fix=False, dry_run=False, tier="free", branches=None):
    gl = get_gitlab_connection(gitlab_url, gitlab_token)
    projects = get_filtered_projects(gl)
    resolved_user_ids = resolve_user_ids(gl, user_identifiers)

    all_results = []
    print(f"📊 Démarrage de l'audit sur {len(projects)} projet(s) (tier={tier}, fix={fix}, dry_run={dry_run})...\n")

    for project in projects:
        print(f"🔍 Audit du projet : {project.path_with_namespace}")
        
        pb_results = check_protected_branches(project)
        all_results.extend(pb_results)
        
        pt_result = check_protected_tags(project)
        all_results.append(pt_result)
        
        ps_result = check_pipeline_success(project)
        all_results.append(ps_result)

        if resolved_user_ids and (tier == "free" or branches):
            ua_results = check_specific_user_access(project, resolved_user_ids, tier=tier, branches=branches)
            all_results.extend(ua_results)

        if fix:
            for r in pb_results:
                if not r["compliant"]:
                    all_results.append(fix_protected_branches(project, r, dry_run=dry_run, tier=tier))
            if not pt_result["compliant"]:
                all_results.append(fix_protected_tags(project, pt_result, dry_run=dry_run, tier=tier))
            if not ps_result["compliant"]:
                all_results.append(fix_pipeline_success(project, ps_result, dry_run=dry_run, tier=tier))

    generate_report(all_results)
    print("\n✅ Audit terminé avec succès.")


if __name__ == "__main__":
    args = parse_args()
    parsed_branches = parse_user_branches(args.user_branches)
    run_audit(
        gitlab_url=args.url,
        gitlab_token=args.token,
        user_identifiers=args.user_id,
        fix=args.fix,
        dry_run=args.dry_run,
        tier=args.tier,
        branches=parsed_branches,
    )
```

---

# 4. 💻 Code Source Complet — Projet 2 : governx-f-test

### 📄 `governx-f-test/governx-pipeline/.gitlab-ci.yml`
```yaml
stages:
  - create_project
  - configure_tags
  - audit_check

variables:
  PROJECT_NAME:
    description: "Nom du/des nouveau(x) projet(s) GitLab à créer, séparés par des virgules"
  PROJECT_TYPE:
    description: "Type de projet"
    value: "backend"
    options: ["backend", "frontend", "batch", "dependencie"]
  GROUP_PATH:
    description: "Chemin du groupe GitLab cible"
  MAX_PARALLEL_PROJECTS:
    value: "4"
  AUDIT_AUTO_FIX:
    value: "no"
    options: ["no", "yes"]
  AUDIT_ACCEPT_NONCOMPLIANT:
    value: "no"
    options: ["no", "yes"]

  GIT_DEPTH: "1"
  GIT_SUBMODULE_STRATEGY: none
  FF_USE_FASTZIP: "true"
  PIP_CACHE_DIR: "$CI_PROJECT_DIR/.cache/pip"

workflow:
  rules:
    - if: '$CI_PIPELINE_SOURCE == "web"'

default:
  image: python:3.11
  tags:
    - docker
  cache:
    key:
      files:
        - ci/requirements.txt
    paths:
      - .cache/pip
  before_script:
    - pip install --quiet --disable-pip-version-check -r ci/requirements.txt

create_project:
  stage: create_project
  script:
    - python3 -m ci.create_project
  artifacts:
    when: always
    paths:
      - reports/created_projects.json
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
    expose_as: "Rapport d'audit GovernX"
    paths:
      - reports/audit_report.html
      - reports/audit_report.json
      - reports/audit_report.txt
```

### 📄 `governx-f-test/governx-pipeline/audit_tool/manifest.py`
```python
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET

POM = "pom.xml"
PACKAGE_JSON = "package.json"

# Manifeste attendu par PROJECT_TYPE.
MANIFEST_BY_TYPE = {
    "backend": POM,
    "batch": POM,
    "dependencie": POM,
    "frontend": PACKAGE_JSON,
}

STACK_BY_MANIFEST = {POM: "maven", PACKAGE_JSON: "npm"}

_TAG_RE = re.compile(r"<(/?)([A-Za-z_][\w.:-]*)([^>]*?)(/?)>", re.DOTALL)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


class ManifestError(Exception):
    """Manifeste introuvable, ambigu, ou champ identifiant absent/illisible."""


def slugify(name: str) -> str:
    """Convertit un nom de projet en kebab-case."""
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    name = name.strip("-")
    if not name:
        raise ManifestError("Nom de projet invalide pour la conversion slug")
    return name


def expected_manifest(project_type: str) -> str:
    """Retourne le nom du manifeste attendu (pom.xml ou package.json)."""
    manifest = MANIFEST_BY_TYPE.get(project_type)
    if not manifest:
        raise ManifestError(f"Type de projet invalide: '{project_type}'")
    return manifest


def detect_manifest(paths: list[str]) -> tuple[str, str]:
    """Localise le fichier manifeste unique dans une arborescence."""
    candidates = [p for p in paths if p.endswith(("/" + POM, "/" + PACKAGE_JSON)) or p in (POM, PACKAGE_JSON)]
    if not candidates:
        raise ManifestError("Aucun manifeste (pom.xml ou package.json) trouvé")
    if len(candidates) > 1:
        raise ManifestError(f"Ambigüité: plusieurs manifestes trouvés ({candidates})")
    
    path = candidates[0]
    filename = POM if path.endswith(POM) else PACKAGE_JSON
    return path, filename


def read_identifier(manifest_name: str, content: str) -> str:
    """Extrait l'identifiant racine d'un pom.xml (<artifactId>) ou package.json ("name")."""
    if manifest_name == POM:
        return _extract_maven_artifact_id(content)
    elif manifest_name == PACKAGE_JSON:
        return _extract_npm_name(content)
    raise ManifestError(f"Manifeste inconnu: '{manifest_name}'")


def _extract_maven_artifact_id(content: str) -> str:
    try:
        content_no_comments = _COMMENT_RE.sub("", content)
        root = ET.fromstring(content_no_comments)
    except ET.ParseError as exc:
        raise ManifestError(f"pom.xml illisible (XML invalide) : {exc}") from exc

    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    artifact_id_el = root.find(f"{ns}artifactId")
    if artifact_id_el is None or not (artifact_id_el.text or "").strip():
        raise ManifestError("pom.xml sans <artifactId> au niveau racine")
    return artifact_id_el.text.strip()


def _extract_npm_name(content: str) -> str:
    try:
        data = json.loads(content)
    except Exception as exc:
        raise ManifestError(f"package.json illisible (JSON invalide) : {exc}") from exc

    if not isinstance(data, dict):
        raise ManifestError("package.json doit être un objet JSON")

    name = data.get("name")
    if not name or not isinstance(name, str) or not name.strip():
        raise ManifestError("package.json sans champ 'name' racine valide")
    return name.strip()
```

### 📄 `governx-f-test/governx-pipeline/audit_tool/rules/protected_tags.py`
```python
"""Règle protected_tags — pattern dérivé du **contenu** du manifeste.

Le pattern attendu est dérivé de la valeur identifiante écrite dans le
manifeste par `create_project` : `{artifactId}-*` pour Maven, `{name}-*` pour npm.
`create_access_level` vaut Admin (60).
"""
from __future__ import annotations

from typing import Any
from audit_tool.manifest import ManifestError, detect_manifest, read_identifier

OWNER_ACCESS_LEVEL = 60
TAG_PATTERN_SUFFIX = "-*"


def build_pattern(identifier: str) -> str:
    return f"{identifier}{TAG_PATTERN_SUFFIX}"


def detect_tag_pattern(project: Any) -> tuple[str, str, str]:
    default_branch = (getattr(project, "default_branch", None) or "").strip()
    if not default_branch:
        raise ManifestError("branche par défaut indéterminée sur le projet")

    try:
        tree = project.repository_tree(ref=default_branch, recursive=True, get_all=True)
    except Exception as exc:
        raise ManifestError(f"lecture de l'arborescence impossible : {exc}") from exc

    paths = [item["path"] for item in tree if item.get("type") == "blob"]
    manifest_path, manifest_name = detect_manifest(paths)

    try:
        content = project.files.get(file_path=manifest_path, ref=default_branch).decode()
    except Exception as exc:
        raise ManifestError(f"lecture de '{manifest_path}' impossible : {exc}") from exc

    if isinstance(content, bytes):
        content = content.decode("utf-8")

    identifier = read_identifier(manifest_name, content)
    return build_pattern(identifier), identifier, manifest_path


def check_protected_tags(project: Any) -> dict:
    try:
        pattern, identifier, manifest_path = detect_tag_pattern(project)
    except ManifestError as exc:
        return _result(project, False, f"Pattern indéterminable : {exc}", None, None, None)

    try:
        protected_tags = project.protectedtags.list(get_all=True)
    except Exception as exc:
        return _result(project, False, f"Erreur API protected tags : {exc}", pattern, identifier, manifest_path)

    matching = [t for t in protected_tags if t.name == pattern]
    if not matching:
        return _result(project, False, f"Aucun protected tag avec le pattern '{pattern}'", pattern, identifier, manifest_path)

    levels = {lvl["access_level"] for lvl in matching[0].create_access_levels}
    if levels != {OWNER_ACCESS_LEVEL}:
        return _result(project, False, f"create_access_level != Admin (trouvé : {sorted(levels)})", pattern, identifier, manifest_path)

    return _result(project, True, "OK", pattern, identifier, manifest_path)


def fix_protected_tags(project: Any, check_result: dict, dry_run: bool = False) -> dict:
    try:
        pattern, _identifier, manifest_path = detect_tag_pattern(project)
    except ManifestError as exc:
        return _fix_result(project, "Aucune action possible", dry_run=dry_run, success=False, details=str(exc))

    action = f"Créer protected tag pattern='{pattern}' (Admin 60)"
    if dry_run:
        return _fix_result(project, action, dry_run=True, success=True, details="dry-run")

    try:
        for t in [t for t in project.protectedtags.list(get_all=True) if t.name == pattern]:
            t.delete()
        project.protectedtags.create({"name": pattern, "create_access_level": OWNER_ACCESS_LEVEL})
    except Exception as exc:
        return _fix_result(project, action, dry_run=False, success=False, details=f"Erreur API : {exc}")

    return _fix_result(project, action, dry_run=False, success=True, details="OK")


def _result(project: Any, compliant: bool, details: str, pattern: str | None, identifier: str | None, manifest_path: str | None) -> dict:
    return {"rule": "protected_tags", "project": project.path_with_namespace, "compliant": compliant, "details": details, "pattern": pattern, "identifier": identifier, "manifest": manifest_path}


def _fix_result(project: Any, action: str, *, dry_run: bool, success: bool, details: str) -> dict:
    return {"rule": "protected_tags", "project": project.path_with_namespace, "action": action, "dry_run": dry_run, "success": success, "details": details}
```

---

# 5. 🧪 Guide d'Exécution et Validation

### 🏃 Exécution des Tests Unitaires :
Pour exécuter la suite complète des **84 tests unitaires** (sans réseau ni dépendance externe) :

```bash
cd governx-f-test/governx-pipeline
pip install -r ci/requirements.txt -r ci/requirements-dev.txt
python -m pytest tests/ -v
```

### 📊 Résultat du Test de Validation :
```text
============================= test session starts =============================
platform win32 -- Python 3.14.6, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\arxbo\OneDrive\Bureau\projet-final\governx-f-test\governx-pipeline
collected 84 items

tests\test_create_project_rename.py ............                         [ 14%]
tests\test_manifest.py ................................................. [ 72%]
.                                                                        [ 73%]
tests\test_protected_tags.py ......................                      [100%]

============================= 84 passed in 0.19s ==============================
```

---
*Ce document résume et archive le code source final prêt à l'emploi et livré sur le dépôt GitHub principal.*
