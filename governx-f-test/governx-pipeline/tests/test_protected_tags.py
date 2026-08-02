"""audit_tool.rules.protected_tags — pattern dérivé du contenu du manifeste."""
from __future__ import annotations

import pytest

from audit_tool.manifest import ManifestError
from audit_tool.rules.protected_tags import (
    OWNER_ACCESS_LEVEL,
    build_pattern,
    check_protected_tags,
    detect_tag_pattern,
    fix_protected_tags,
)
from tests.conftest import FakeProject, FakeTag


def test_build_pattern():
    assert build_pattern("simple-springboot-app") == "simple-springboot-app-*"


# --------------------------------------------------------------- détection

def test_detect_maven(pom_simple):
    project = FakeProject({"svc/pom.xml": pom_simple})
    pattern, identifier, path = detect_tag_pattern(project)
    assert pattern == "simple-springboot-app-*"
    assert identifier == "simple-springboot-app"
    assert path == "svc/pom.xml"


def test_detect_npm(package_json_simple):
    project = FakeProject({"app/package.json": package_json_simple})
    pattern, identifier, path = detect_tag_pattern(project)
    assert pattern == "simple-react-app-*"
    assert identifier == "simple-react-app"


def test_detect_lit_la_branche_par_defaut_reelle(pom_simple):
    # Le FakeProject rejette toute ref != default_branch : si la règle
    # retombait sur "main" en dur, ce test échouerait.
    project = FakeProject({"pom.xml": pom_simple}, default_branch="master")
    assert detect_tag_pattern(project)[1] == "simple-springboot-app"


def test_detect_branche_par_defaut_vide_fail_closed(pom_simple):
    project = FakeProject({"pom.xml": pom_simple}, default_branch="")
    with pytest.raises(ManifestError, match="branche par défaut indéterminée"):
        detect_tag_pattern(project)


def test_detect_branche_par_defaut_none_fail_closed(pom_simple):
    project = FakeProject({"pom.xml": pom_simple}, default_branch=None)
    with pytest.raises(ManifestError, match="branche par défaut indéterminée"):
        detect_tag_pattern(project)


def test_detect_sans_manifeste_fail_closed():
    project = FakeProject({"README.md": "# rien"})
    with pytest.raises(ManifestError, match="aucun 'pom.xml' ni 'package.json'"):
        detect_tag_pattern(project)


def test_detect_multi_manifestes_fail_closed(pom_simple):
    project = FakeProject({"module-a/pom.xml": pom_simple, "module-b/pom.xml": pom_simple})
    with pytest.raises(ManifestError, match="2 'pom.xml' trouvés"):
        detect_tag_pattern(project)


def test_detect_stacks_concurrents_fail_closed(pom_simple, package_json_simple):
    project = FakeProject({"pom.xml": pom_simple, "package.json": package_json_simple})
    with pytest.raises(ManifestError, match="concurrents"):
        detect_tag_pattern(project)


def test_detect_champ_manquant_fail_closed():
    project = FakeProject({"pom.xml": "<project><groupId>x</groupId></project>"})
    with pytest.raises(ManifestError, match="sans <artifactId> au niveau racine"):
        detect_tag_pattern(project)


def test_detect_erreur_api_arbre_fail_closed(pom_simple):
    project = FakeProject({"pom.xml": pom_simple}, tree_error="403 Forbidden")
    with pytest.raises(ManifestError, match="arborescence"):
        detect_tag_pattern(project)


# ------------------------------------------------------------------- check

def test_check_conforme(pom_simple):
    project = FakeProject(
        {"pom.xml": pom_simple},
        tags=[FakeTag("simple-springboot-app-*", [OWNER_ACCESS_LEVEL])],
    )
    r = check_protected_tags(project)
    assert r["compliant"] is True
    assert r["pattern"] == "simple-springboot-app-*"
    assert r["identifier"] == "simple-springboot-app"
    assert r["manifest"] == "pom.xml"


def test_check_ancien_pattern_generique_desormais_non_conforme(pom_simple):
    # L'ancien pattern générique ne satisfait plus la règle.
    project = FakeProject({"pom.xml": pom_simple}, tags=[FakeTag("*", [OWNER_ACCESS_LEVEL])])
    r = check_protected_tags(project)
    assert r["compliant"] is False
    assert "simple-springboot-app-*" in r["details"]


def test_check_absent(pom_simple):
    project = FakeProject({"pom.xml": pom_simple}, tags=[])
    r = check_protected_tags(project)
    assert r["compliant"] is False
    assert "Aucun protected tag" in r["details"]


def test_check_mauvais_niveau_dacces(pom_simple):
    project = FakeProject(
        {"pom.xml": pom_simple}, tags=[FakeTag("simple-springboot-app-*", [40])]
    )
    r = check_protected_tags(project)
    assert r["compliant"] is False
    assert "create_access_level != Admin" in r["details"]
    assert "[40]" in r["details"]


def test_check_manifeste_absent_non_conforme_sans_crash():
    project = FakeProject({"README.md": "#"})
    r = check_protected_tags(project)
    assert r["compliant"] is False
    assert r["pattern"] is None
    assert "Pattern indéterminable" in r["details"]


# --------------------------------------------------------------------- fix

def test_fix_cree_le_tag_avec_admin(pom_simple):
    project = FakeProject({"pom.xml": pom_simple}, tags=[])
    r = fix_protected_tags(project, check_protected_tags(project))
    assert r["success"] is True
    assert project.protectedtags.created == [
        {"name": "simple-springboot-app-*", "create_access_level": OWNER_ACCESS_LEVEL}
    ]


def test_fix_remplace_lancien_pattern(pom_simple):
    project = FakeProject({"pom.xml": pom_simple}, tags=[FakeTag("simple-springboot-app-*", [40])])
    fix_protected_tags(project, check_protected_tags(project))
    noms = [t.name for t in project.protectedtags.list()]
    assert noms == ["simple-springboot-app-*"]
    niveaux = {lvl["access_level"] for lvl in project.protectedtags.list()[0].create_access_levels}
    assert niveaux == {OWNER_ACCESS_LEVEL}


def test_fix_redderive_le_pattern_et_ignore_un_check_result_perime(pom_simple):
    """Le fix relit le manifeste : un pattern périmé dans check_result est ignoré."""
    project = FakeProject({"pom.xml": pom_simple}, tags=[])
    perime = {"rule": "protected_tags", "pattern": "obsolete-*", "identifier": "obsolete"}
    fix_protected_tags(project, perime)
    assert project.protectedtags.created[0]["name"] == "simple-springboot-app-*"


def test_fix_dry_run_nécrit_rien(pom_simple):
    project = FakeProject({"pom.xml": pom_simple}, tags=[])
    r = fix_protected_tags(project, check_protected_tags(project), dry_run=True)
    assert r["success"] is True and r["dry_run"] is True
    assert project.protectedtags.created == []


def test_fix_fail_closed_sans_manifeste():
    project = FakeProject({"README.md": "#"})
    r = fix_protected_tags(project, check_protected_tags(project))
    assert r["success"] is False
    assert "indéterminable" in r["action"]
    assert project.protectedtags.created == []


def test_check_puis_fix_puis_recheck_converge(pom_simple):
    """Boucle réelle d'audit_check : non conforme -> fix -> conforme."""
    project = FakeProject({"pom.xml": pom_simple}, tags=[])
    assert check_protected_tags(project)["compliant"] is False
    assert fix_protected_tags(project, check_protected_tags(project))["success"] is True
    assert check_protected_tags(project)["compliant"] is True
