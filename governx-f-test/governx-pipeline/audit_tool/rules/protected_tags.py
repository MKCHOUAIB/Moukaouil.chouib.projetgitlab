"""Règle protected_tags — pattern dérivé du **contenu** du manifeste.

Le pattern attendu est dérivé de la valeur identifiante écrite dans le
manifeste par `create_project` : `{artifactId}-*` pour Maven, `{name}-*` pour npm.

La valeur est **relue depuis le manifeste** à chaque check et à chaque fix,
jamais reprise d'un slug calculé en amont : `create_project` et `audit_check`
sont des jobs CI distincts, et repasser par le fichier garde les deux étapes
synchronisées par construction plutôt que par convention.

`create_access_level` vaut Admin (60).
"""
from __future__ import annotations

from typing import Any

from audit_tool.manifest import ManifestError, detect_manifest, read_identifier

OWNER_ACCESS_LEVEL = 60

TAG_PATTERN_SUFFIX = "-*"


def build_pattern(identifier: str) -> str:
    """Pattern de protected tag pour un identifiant de manifeste donné."""
    return f"{identifier}{TAG_PATTERN_SUFFIX}"


def detect_tag_pattern(project: Any) -> tuple[str, str, str]:
    """Relit le manifeste du projet et en dérive le pattern de protected tag.

    Cherche le manifeste dans **toute** l'arborescence via l'API (un scan
    root-only rate `my-app/pom.xml` — bug connu côté CIH), sur la branche par
    défaut réelle du projet.

    Returns:
        (pattern, identifiant, chemin du manifeste).

    Raises:
        ManifestError: aucun manifeste, plusieurs candidats, champ identifiant
            absent/illisible, ou branche par défaut indéterminée. Aucun repli
            deviné : un pattern faux protégerait les mauvais tags.
    """
    default_branch = (getattr(project, "default_branch", None) or "").strip()
    if not default_branch:
        raise ManifestError(
            "branche par défaut indéterminée sur le projet : manifeste illisible."
        )

    try:
        tree = project.repository_tree(ref=default_branch, recursive=True, get_all=True)
    except ManifestError:
        raise
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
    """Vérifie qu'un protected tag existe pour le pattern attendu, en Admin-only."""
    try:
        pattern, identifier, manifest_path = detect_tag_pattern(project)
    except ManifestError as exc:
        return _result(project, False, f"Pattern indéterminable : {exc}", None, None, None)

    try:
        protected_tags = project.protectedtags.list(get_all=True)
    except Exception as exc:
        return _result(
            project, False, f"Erreur API lecture protected tags : {exc}",
            pattern, identifier, manifest_path,
        )

    matching = [t for t in protected_tags if t.name == pattern]
    if not matching:
        return _result(
            project, False,
            f"Aucun protected tag avec le pattern '{pattern}' "
            f"(attendu d'après {manifest_path})",
            pattern, identifier, manifest_path,
        )

    levels = {lvl["access_level"] for lvl in matching[0].create_access_levels}
    if levels != {OWNER_ACCESS_LEVEL}:
        return _result(
            project, False,
            f"Protected tag '{pattern}' existe mais create_access_level != Admin "
            f"(trouvé : {sorted(levels)})",
            pattern, identifier, manifest_path,
        )

    return _result(project, True, "OK", pattern, identifier, manifest_path)


def fix_protected_tags(project: Any, check_result: dict, dry_run: bool = False) -> dict:
    """Crée le protected tag attendu avec create_access_level = Admin.

    Le pattern est **re-dérivé du manifeste**, pas repris de `check_result` :
    si le manifeste a changé entre le check et le fix, c'est le fichier qui fait
    foi. L'API GitLab ne permet pas de modifier le niveau d'accès d'une règle
    existante — on supprime puis on recrée.
    """
    try:
        pattern, _identifier, manifest_path = detect_tag_pattern(project)
    except ManifestError as exc:
        return _fix_result(
            project, "Aucune action possible : pattern indéterminable",
            dry_run=dry_run, success=False, details=str(exc),
        )

    action = f"Créer un protected tag pattern='{pattern}' (create_access_level=Admin), d'après {manifest_path}"

    if dry_run:
        return _fix_result(project, action, dry_run=True, success=True,
                           details="dry-run, aucune écriture réelle")

    try:
        for t in [t for t in project.protectedtags.list(get_all=True) if t.name == pattern]:
            t.delete()
        project.protectedtags.create({"name": pattern, "create_access_level": OWNER_ACCESS_LEVEL})
    except Exception as exc:
        return _fix_result(project, action, dry_run=False, success=False, details=f"Erreur API : {exc}")

    return _fix_result(project, action, dry_run=False, success=True, details="OK")


def _result(project: Any, compliant: bool, details: str, pattern: str | None,
            identifier: str | None, manifest_path: str | None) -> dict:
    return {
        "rule": "protected_tags",
        "project": project.path_with_namespace,
        "compliant": compliant,
        "details": details,
        "pattern": pattern,
        "identifier": identifier,
        "manifest": manifest_path,
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
