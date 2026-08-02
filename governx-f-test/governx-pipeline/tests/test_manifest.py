"""audit_tool.manifest — slug, localisation, lecture et réécriture du manifeste."""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pytest

from audit_tool.manifest import (
    PACKAGE_JSON,
    POM,
    ManifestError,
    detect_manifest,
    expected_manifest,
    locate_manifest,
    read_identifier,
    rewrite_identifier,
    slugify,
)


# ------------------------------------------------------------------- slugify

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Simple SpringBoot App", "simple-springboot-app"),   # cas de référence
        ("MonProjet", "monprojet"),                            # casse mixte
        ("mon_projet_batch", "mon-projet-batch"),              # underscores
        ("deja-en-kebab", "deja-en-kebab"),                    # déjà hyphéné
        ("  --Mon Projet--  ", "mon-projet"),                  # séparateurs en tête/fin
        ("API   v2", "api-v2"),                                # espaces multiples -> un seul -
        ("api.v2.client", "api-v2-client"),                    # ponctuation -> séparateur
        ("Projet 2024", "projet-2024"),                        # chiffres conservés
        ("service---batch", "service-batch"),                  # runs de séparateurs
        ("A", "a"),                                            # une seule lettre
        ("123", "123"),                                        # que des chiffres
    ],
)
def test_slugify(raw, expected):
    assert slugify(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "---", "!!!", "@#$%^&*()", "é" and "..."])
def test_slugify_fail_closed_sans_alphanumerique(raw):
    with pytest.raises(ManifestError, match="alphanumérique"):
        slugify(raw)


def test_slugify_accents_non_ascii_rejetes_comme_separateurs():
    # Les caractères non-ASCII ne sont pas alphanumériques au sens de la règle :
    # ils deviennent des séparateurs, pas des lettres translittérées.
    assert slugify("Café Über") == "caf-ber"


# ----------------------------------------------------------- expected/locate

def test_expected_manifest_par_type():
    assert expected_manifest("backend") == POM
    assert expected_manifest("batch") == POM
    assert expected_manifest("dependencie") == POM
    assert expected_manifest("frontend") == PACKAGE_JSON


def test_expected_manifest_type_inconnu():
    with pytest.raises(ManifestError, match="inconnu"):
        expected_manifest("mobile")


def test_locate_manifest_hors_racine():
    paths = ["README.md", "my-app/pom.xml", "my-app/src/Main.java"]
    assert locate_manifest(paths, POM) == "my-app/pom.xml"


def test_locate_manifest_absent_fail_closed():
    with pytest.raises(ManifestError, match="aucun 'pom.xml'"):
        locate_manifest(["README.md"], POM)


def test_locate_manifest_multi_candidats_fail_closed():
    paths = ["pom.xml", "module-a/pom.xml", "module-b/pom.xml"]
    with pytest.raises(ManifestError, match="3 'pom.xml' trouvés"):
        locate_manifest(paths, POM)


def test_locate_manifest_ne_confond_pas_un_suffixe():
    # 'parent-pom.xml' ne doit pas compter comme 'pom.xml'
    assert locate_manifest(["parent-pom.xml", "app/pom.xml"], POM) == "app/pom.xml"


def test_detect_manifest_maven():
    assert detect_manifest(["svc/pom.xml", "README.md"]) == ("svc/pom.xml", POM)


def test_detect_manifest_npm():
    assert detect_manifest(["app/package.json"]) == ("app/package.json", PACKAGE_JSON)


def test_detect_manifest_aucun_fail_closed():
    with pytest.raises(ManifestError, match="aucun 'pom.xml' ni 'package.json'"):
        detect_manifest(["README.md", "src/main.py"])


def test_detect_manifest_deux_stacks_fail_closed():
    with pytest.raises(ManifestError, match="concurrents"):
        detect_manifest(["pom.xml", "package.json"])


# ----------------------------------------------------------------- lecture

def test_read_pom_racine(pom_simple):
    assert read_identifier(POM, pom_simple) == "simple-springboot-app"


def test_read_pom_ignore_parent_et_dependency(pom_nested):
    assert read_identifier(POM, pom_nested) == "simple-springboot-app"


def test_read_pom_sans_artifact_id_racine():
    pom = "<project><groupId>ma.cih</groupId></project>"
    with pytest.raises(ManifestError, match="sans <artifactId> au niveau racine"):
        read_identifier(POM, pom)


def test_read_pom_artifact_id_seulement_dans_parent():
    pom = """<project>
      <parent><artifactId>spring-boot-starter-parent</artifactId></parent>
    </project>"""
    with pytest.raises(ManifestError, match="sans <artifactId> au niveau racine"):
        read_identifier(POM, pom)


def test_read_pom_xml_invalide():
    with pytest.raises(ManifestError, match="XML invalide"):
        read_identifier(POM, "<project><artifactId>x</project>")


def test_read_pom_artifact_id_vide():
    with pytest.raises(ManifestError, match="vide"):
        read_identifier(POM, "<project><artifactId>   </artifactId></project>")


def test_read_pom_ignore_artifact_id_en_commentaire():
    pom = """<project>
      <!-- <artifactId>commente</artifactId> -->
      <artifactId>le-vrai</artifactId>
    </project>"""
    assert read_identifier(POM, pom) == "le-vrai"


def test_read_package_json(package_json_simple):
    assert read_identifier(PACKAGE_JSON, package_json_simple) == "simple-react-app"


def test_read_package_json_sans_name():
    with pytest.raises(ManifestError, match='sans champ "name"'):
        read_identifier(PACKAGE_JSON, '{"version": "1.0.0"}')


def test_read_package_json_invalide():
    with pytest.raises(ManifestError, match="JSON invalide"):
        read_identifier(PACKAGE_JSON, "{not json}")


def test_read_manifeste_non_supporte():
    with pytest.raises(ManifestError, match="non supporté"):
        read_identifier("build.gradle", "whatever")


# --------------------------------------------------------------- réécriture

def test_rewrite_pom_simple(pom_simple):
    out = rewrite_identifier(POM, pom_simple, "nouveau-nom")
    assert read_identifier(POM, out) == "nouveau-nom"
    assert "simple-springboot-app" not in out


def test_rewrite_pom_ne_touche_ni_parent_ni_dependency(pom_nested):
    out = rewrite_identifier(POM, pom_nested, "nouveau-nom")

    root = ET.fromstring(out)
    ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""

    assert root.find(f"{ns}artifactId").text == "nouveau-nom"
    assert root.find(f"{ns}parent/{ns}artifactId").text == "spring-boot-starter-parent"
    dep = root.find(f"{ns}dependencies/{ns}dependency/{ns}artifactId")
    assert dep.text == "spring-boot-starter-web"


def test_rewrite_pom_preserve_le_reste(pom_nested):
    out = rewrite_identifier(POM, pom_nested, "x")
    # Diff minimal : une seule ligne change.
    diff = [
        (a, b) for a, b in zip(pom_nested.splitlines(), out.splitlines()) if a != b
    ]
    assert len(diff) == 1
    assert "simple-springboot-app" in diff[0][0] and "<artifactId>x</artifactId>" in diff[0][1]


def test_rewrite_pom_avec_namespace_prefixe():
    pom = """<?xml version="1.0"?>
<m:project xmlns:m="http://maven.apache.org/POM/4.0.0">
  <m:artifactId>ancien</m:artifactId>
</m:project>"""
    out = rewrite_identifier(POM, pom, "recent")
    assert read_identifier(POM, out) == "recent"


def test_rewrite_package_json(package_json_simple):
    out = rewrite_identifier(PACKAGE_JSON, package_json_simple, "nouveau-front")
    data = json.loads(out)
    assert data["name"] == "nouveau-front"
    assert data["version"] == "0.1.0"
    assert data["private"] is True
    assert data["dependencies"] == {"react": "^18.2.0"}


def test_rewrite_package_json_diff_minimal(package_json_simple):
    out = rewrite_identifier(PACKAGE_JSON, package_json_simple, "nouveau-front")
    diff = [
        (a, b) for a, b in zip(package_json_simple.splitlines(), out.splitlines()) if a != b
    ]
    assert len(diff) == 1
    assert '"name": "nouveau-front"' in diff[0][1]


def test_rewrite_package_json_ne_touche_pas_un_name_imbrique():
    src = json.dumps(
        {"name": "racine", "author": {"name": "quelqu-un"}, "version": "1.0.0"}, indent=2
    )
    out = rewrite_identifier(PACKAGE_JSON, src, "renomme")
    data = json.loads(out)
    assert data["name"] == "renomme"
    assert data["author"]["name"] == "quelqu-un"


def test_rewrite_package_json_name_imbrique_avant_la_racine():
    # Piège : un "name" imbriqué apparaît AVANT le "name" racine, avec la même
    # valeur. Le suivi de profondeur doit quand même viser la racine.
    src = """{
  "author": { "name": "racine" },
  "name": "racine",
  "version": "1.0.0"
}"""
    out = rewrite_identifier(PACKAGE_JSON, src, "renomme")
    data = json.loads(out)
    assert data["name"] == "renomme"
    assert data["author"]["name"] == "racine"


def test_rewrite_package_json_name_dans_un_tableau():
    src = """{
  "contributors": [{ "name": "a" }, { "name": "b" }],
  "name": "le-projet"
}"""
    out = rewrite_identifier(PACKAGE_JSON, src, "x")
    data = json.loads(out)
    assert data["name"] == "x"
    assert [c["name"] for c in data["contributors"]] == ["a", "b"]


def test_rewrite_package_json_echappements_preserves():
    src = '{"description": "guillemet \\" et \\\\ backslash", "name": "old"}'
    out = rewrite_identifier(PACKAGE_JSON, src, "new")
    data = json.loads(out)
    assert data["name"] == "new"
    assert data["description"] == 'guillemet " et \\ backslash'


def test_rewrite_fail_closed_si_champ_absent():
    with pytest.raises(ManifestError):
        rewrite_identifier(PACKAGE_JSON, '{"version": "1.0.0"}', "x")
