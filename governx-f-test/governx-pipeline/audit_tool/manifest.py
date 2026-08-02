
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
    """Convertit un nom de projet en kebab-case.

    Minuscules, toute suite de caractères non alphanumériques réduite à un seul
    `-`, pas de `-` en tête ni en fin. « Simple SpringBoot App » ->
    « simple-springboot-app ».

    Note : distinct de `ci.create_project.slugify`, qui produit le *path* GitLab
    et supprime la ponctuation au lieu de la convertir en séparateur
    (« api.v2 » -> « apiv2» côté path, « api-v2 » ici).
    """
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        raise ManifestError(
            f"le nom '{name}' ne contient aucun caractère alphanumérique : "
            "impossible d'en dériver un identifiant."
        )
    return slug


def expected_manifest(project_type: str) -> str:
    """Nom de fichier du manifeste attendu pour ce PROJECT_TYPE."""
    manifest = MANIFEST_BY_TYPE.get(project_type)
    if manifest is None:
        raise ManifestError(
            f"PROJECT_TYPE='{project_type}' inconnu du mapping "
            f"{sorted(MANIFEST_BY_TYPE)} : manifeste attendu indéterminable."
        )
    return manifest


def locate_manifest(paths: list[str], filename: str) -> str:
    """Trouve l'unique `filename` dans une arborescence complète de chemins.

    Le manifeste n'est pas toujours à la racine (bug connu côté CIH : un scan
    root-only rate `my-app/pom.xml`), d'où la recherche sur tout l'arbre.

    Zéro candidat comme plusieurs candidats sont des erreurs : avec plusieurs
    `pom.xml` (projet multi-modules), rien ne permet de désigner le module
    porteur de l'identité du projet sans deviner.
    """
    matches = sorted(p for p in paths if p.rsplit("/", 1)[-1] == filename)

    if not matches:
        raise ManifestError(f"aucun '{filename}' trouvé dans l'arborescence du projet.")
    if len(matches) > 1:
        raise ManifestError(
            f"{len(matches)} '{filename}' trouvés ({', '.join(matches)}) : "
            "impossible de déterminer lequel porte l'identité du projet."
        )
    return matches[0]


def detect_manifest(paths: list[str]) -> tuple[str, str]:
    """Détecte le manifeste d'un projet sans connaître son PROJECT_TYPE.

    Utilisé côté audit, qui ne reçoit pas PROJECT_TYPE. Retourne
    (chemin, nom de fichier). Un projet portant les deux manifestes est ambigu.
    """
    present = [f for f in (POM, PACKAGE_JSON)
               if any(p.rsplit("/", 1)[-1] == f for p in paths)]

    if not present:
        raise ManifestError(
            f"aucun '{POM}' ni '{PACKAGE_JSON}' trouvé dans l'arborescence du projet."
        )
    if len(present) > 1:
        raise ManifestError(
            f"manifestes concurrents détectés ({' et '.join(present)}) : "
            "stack du projet ambigu."
        )

    filename = present[0]
    return locate_manifest(paths, filename), filename


# --------------------------------------------------------------------- Maven

def _strip_comments(text: str) -> str:
    """Neutralise les commentaires XML en préservant les offsets."""
    return _COMMENT_RE.sub(lambda m: " " * len(m.group(0)), text)


def _find_root_artifact_id(text: str) -> tuple[int, int, str]:
    """Localise le `<artifactId>` enfant direct de `<project>`.

    Retourne (début_du_texte, fin_du_texte, valeur). Le suivi de profondeur
    garantit qu'on ne remonte jamais l'artifactId d'un `<parent>` ou d'une
    `<dependency>`, qui sont à une profondeur strictement supérieure.
    """
    scan = _strip_comments(text)
    depth = 0

    for m in _TAG_RE.finditer(scan):
        closing, tag, _attrs, self_closing = m.groups()
        local = tag.split(":")[-1]

        if closing:
            depth -= 1
            continue

        if not self_closing and local == "artifactId" and depth == 1:
            end = scan.find("<", m.end())
            if end == -1:
                break
            return m.end(), end, text[m.end():end].strip()

        if not self_closing:
            depth += 1

    raise ManifestError(
        f"'{POM}' sans <artifactId> au niveau racine du projet "
        "(un artifactId de <parent> ou de <dependency> ne compte pas)."
    )


def _parse_pom(text: str) -> None:
    """Vérifie que le POM est du XML valide avant toute réécriture."""
    try:
        ET.fromstring(text)
    except ET.ParseError as exc:
        raise ManifestError(f"'{POM}' illisible (XML invalide) : {exc}") from exc


def _read_pom_artifact_id(text: str) -> str:
    _parse_pom(text)
    _start, _end, value = _find_root_artifact_id(text)
    if not value:
        raise ManifestError(f"'{POM}' : <artifactId> racine vide.")
    return value


def _write_pom_artifact_id(text: str, new_value: str) -> str:
    _parse_pom(text)
    start, end, _old = _find_root_artifact_id(text)
    return text[:start] + new_value + text[end:]


# ----------------------------------------------------------------------- npm

def _load_package_json(text: str) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"'{PACKAGE_JSON}' illisible (JSON invalide) : {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError(f"'{PACKAGE_JSON}' : l'objet racine n'est pas un objet JSON.")
    return data


def _read_npm_name(text: str) -> str:
    data = _load_package_json(text)
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ManifestError(f"'{PACKAGE_JSON}' sans champ \"name\" racine exploitable.")
    return name.strip()


def _find_root_name_span(text: str) -> tuple[int, int]:
    """Localise la valeur de la clé `"name"` de l'objet racine.

    Suit la profondeur des accolades/crochets comme `_find_root_artifact_id`
    suit celle des balises : un `"name"` imbriqué (ex. `author.name`) est à une
    profondeur > 1 et ne peut donc jamais être sélectionné.
    """
    depth = 0
    in_string = False
    escaped = False
    key_start: int | None = None
    pending_key: str | None = None
    i, n = 0, len(text)

    while i < n:
        c = text[i]

        if in_string:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_string = False
                if depth == 1 and key_start is not None:
                    pending_key = text[key_start:i]
                key_start = None
            i += 1
            continue

        if c == '"':
            in_string = True
            key_start = i + 1
        elif c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
        elif c == ",":
            pending_key = None
        elif c == ":" and depth == 1 and pending_key == "name":
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j >= n or text[j] != '"':
                raise ManifestError(f"'{PACKAGE_JSON}' : \"name\" racine n'est pas une chaîne.")
            k, esc = j + 1, False
            while k < n:
                if esc:
                    esc = False
                elif text[k] == "\\":
                    esc = True
                elif text[k] == '"':
                    return j, k + 1
                k += 1
            break

        i += 1

    raise ManifestError(f"'{PACKAGE_JSON}' : champ \"name\" racine non localisable dans le texte.")


def _write_npm_name(text: str, new_value: str) -> str:
    """Remplace la valeur de "name" racine en touchant le moins de texte possible."""
    data = _load_package_json(text)
    _read_npm_name(text)  # valide la présence du champ avant de toucher au texte

    start, end = _find_root_name_span(text)
    updated = text[:start] + json.dumps(new_value, ensure_ascii=False) + text[end:]

    # Garde-fou : la réécriture textuelle doit produire le résultat structurel voulu.
    check = _load_package_json(updated)
    if check.get("name") != new_value:
        raise ManifestError(f"'{PACKAGE_JSON}' : la réécriture n'a pas produit \"name\"='{new_value}'.")
    if {k: v for k, v in check.items() if k != "name"} != {k: v for k, v in data.items() if k != "name"}:
        raise ManifestError(f"'{PACKAGE_JSON}' : la réécriture a altéré d'autres champs.")

    return updated


# ------------------------------------------------------------------ dispatch

_READERS = {POM: _read_pom_artifact_id, PACKAGE_JSON: _read_npm_name}
_WRITERS = {POM: _write_pom_artifact_id, PACKAGE_JSON: _write_npm_name}


def read_identifier(filename: str, content: str) -> str:
    """Lit le champ identifiant du manifeste (artifactId Maven ou name npm)."""
    reader = _READERS.get(filename)
    if reader is None:
        raise ManifestError(f"manifeste '{filename}' non supporté.")
    return reader(content)


def rewrite_identifier(filename: str, content: str, new_value: str) -> str:
    """Retourne le contenu du manifeste avec le champ identifiant remplacé.

    Édition textuelle ciblée (diff minimal), puis relecture structurelle pour
    confirmer que seule la bonne valeur a changé.
    """
    writer = _WRITERS.get(filename)
    if writer is None:
        raise ManifestError(f"manifeste '{filename}' non supporté.")

    updated = writer(content, new_value)

    if read_identifier(filename, updated) != new_value:
        raise ManifestError(
            f"'{filename}' : relecture après réécriture ne renvoie pas '{new_value}'."
        )
    return updated
