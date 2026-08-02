"""audit_tool — logique métier partagée par configure_tags.py et audit_check.py.

scan_manifests et run_audit restent des stubs. extract_project_name
est implémentée (mapping PROJECT_TYPE -> manifeste déterministe).
"""
from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from typing import Any

# Mapping figé : chaque PROJECT_TYPE correspond à exactement un manifeste attendu.
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
    encore définis. Cette implémentation minimale vérifie uniquement la présence
    d'un README.md, juste pour que le pipeline puisse tourner de bout en bout.
    À REMPLACER dès que les vrais critères métier sont connus — ne pas considérer
    ce comportement comme la spec finale de l'audit.

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
        "details": "Audit placeholder — critères réels à définir avec CIH.",
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