"""ci.create_project — renommage du champ identifiant du manifeste."""
from __future__ import annotations

import types

import pytest

from audit_tool.manifest import ManifestError
from ci.create_project import provision_all, rename_manifest_identifier


class FakeClient:
    """GitLabAPIClient simulé : arborescence + fichiers + commits en mémoire."""

    token = "TOK"

    def __init__(self, files: dict[str, str], default_branch: str = "master") -> None:
        self.files = dict(files)
        self.default_branch = default_branch
        self.commits: list[dict] = []
        self.created_projects: list[dict] = []

    # --- utilisé par rename_manifest_identifier
    def get_project(self, path):
        return {"path_with_namespace": path, "default_branch": self.default_branch}

    def list_repository_tree(self, path, ref, recursive=True):
        assert ref == self.default_branch, f"ref inattendue : {ref}"
        return [{"path": p, "type": "blob"} for p in self.files]

    def get_raw_file(self, path, file_path, ref):
        assert ref == self.default_branch
        return self.files[file_path]

    def create_commit(self, path, branch, commit_message, actions):
        assert branch == self.default_branch
        for a in actions:
            self.files[a["file_path"]] = a["content"]
        self.commits.append(
            {"project": path, "branch": branch, "message": commit_message, "actions": actions}
        )
        return {"id": "deadbeef"}

    # --- utilisé par provision_project
    def create_project(self, name, path, namespace_id, description=""):
        self.created_projects.append({"name": name, "path": path})
        return {
            "path_with_namespace": f"grp/{path}",
            "http_url_to_repo": f"https://srv/grp/{path}.git",
        }

    def get_authenticated_git_url(self, url):
        return url


def test_deja_aligne_aucun_commit(pom_simple):
    """Le template porte déjà le bon artifactId : pas de commit vide."""
    client = FakeClient({"svc/pom.xml": pom_simple})
    out = rename_manifest_identifier(client, "grp/p", "backend", "Simple SpringBoot App")

    assert out["identifier"] == "simple-springboot-app"
    assert out["previous"] == "simple-springboot-app"
    assert out["committed"] is False
    assert client.commits == []


def test_renomme_vers_un_nom_different(pom_simple):
    client = FakeClient({"svc/pom.xml": pom_simple})
    out = rename_manifest_identifier(client, "grp/p", "backend", "Facturation Batch")

    assert out["identifier"] == "facturation-batch"
    assert out["previous"] == "simple-springboot-app"
    assert out["committed"] is True
    assert out["manifest"] == "svc/pom.xml"
    assert len(client.commits) == 1
    assert client.commits[0]["actions"][0]["file_path"] == "svc/pom.xml"
    assert client.commits[0]["actions"][0]["action"] == "update"
    assert "facturation-batch" in client.commits[0]["actions"][0]["content"]
    assert "<artifactId>facturation-batch</artifactId>" in client.files["svc/pom.xml"]


def test_renomme_package_json(package_json_simple):
    client = FakeClient({"package.json": package_json_simple})
    out = rename_manifest_identifier(client, "grp/p", "frontend", "Portail Client")

    assert out["identifier"] == "portail-client"
    assert '"name": "portail-client"' in client.files["package.json"]


def test_utilise_la_branche_par_defaut_reelle(pom_simple):
    # FakeClient assert sur la ref : un "main" en dur ferait échouer le test.
    client = FakeClient({"pom.xml": pom_simple}, default_branch="master")
    out = rename_manifest_identifier(client, "grp/p", "backend", "Nouveau Nom")
    assert out["branch"] == "master"


def test_branche_par_defaut_vide_fail_closed(pom_simple):
    client = FakeClient({"pom.xml": pom_simple}, default_branch="")
    with pytest.raises(ManifestError, match="branche par défaut indéterminée"):
        rename_manifest_identifier(client, "grp/p", "backend", "X")
    assert client.commits == []


def test_manifeste_absent_fail_closed():
    client = FakeClient({"README.md": "# rien"})
    with pytest.raises(ManifestError, match="aucun 'pom.xml'"):
        rename_manifest_identifier(client, "grp/p", "backend", "X")
    assert client.commits == []


def test_multi_manifestes_fail_closed(pom_simple):
    client = FakeClient({"a/pom.xml": pom_simple, "b/pom.xml": pom_simple})
    with pytest.raises(ManifestError, match="2 'pom.xml' trouvés"):
        rename_manifest_identifier(client, "grp/p", "backend", "X")
    assert client.commits == []


def test_champ_absent_fail_closed():
    client = FakeClient({"pom.xml": "<project><groupId>g</groupId></project>"})
    with pytest.raises(ManifestError, match="sans <artifactId>"):
        rename_manifest_identifier(client, "grp/p", "backend", "X")
    assert client.commits == []


def test_manifeste_illisible_fail_closed():
    client = FakeClient({"pom.xml": "<project><artifactId>x</project>"})
    with pytest.raises(ManifestError, match="XML invalide"):
        rename_manifest_identifier(client, "grp/p", "backend", "X")
    assert client.commits == []


def test_mauvais_manifeste_pour_le_type(package_json_simple):
    # PROJECT_TYPE=backend attend un pom.xml, pas un package.json.
    client = FakeClient({"package.json": package_json_simple})
    with pytest.raises(ManifestError, match="aucun 'pom.xml'"):
        rename_manifest_identifier(client, "grp/p", "backend", "X")


def test_renommage_par_projet_dans_un_lot(pom_simple, monkeypatch):
    """Le lot multi-projets renomme chaque manifeste avec SON propre slug."""
    import ci.create_project as cp

    monkeypatch.setattr(
        cp.subprocess, "run",
        lambda *a, **k: types.SimpleNamespace(returncode=0, stdout="", stderr=""),
    )

    client = FakeClient({"pom.xml": pom_simple})
    targets = [("API Clients", "api-clients"), ("Facturation Batch", "facturation-batch")]

    created, failed = provision_all(
        client, targets, target_group_id=1, project_type="backend",
        template_path="tpl/backend", mirror_dir="/tmp/x", max_parallel=2,
    )

    assert failed == []
    assert [c["manifest"]["identifier"] for c in created] == ["api-clients", "facturation-batch"]
    assert [c["path_with_namespace"] for c in created] == ["grp/api-clients", "grp/facturation-batch"]
    assert len(client.commits) == 2


def test_echec_de_renommage_isole_le_projet(pom_simple, monkeypatch):
    """Un manifeste illisible fait échouer SON projet, pas tout le lot."""
    import ci.create_project as cp

    monkeypatch.setattr(
        cp.subprocess, "run",
        lambda *a, **k: types.SimpleNamespace(returncode=0, stdout="", stderr=""),
    )

    class Partiel(FakeClient):
        def get_raw_file(self, path, file_path, ref):
            if path.endswith("casse"):
                return "<project><groupId>g</groupId></project>"
            return super().get_raw_file(path, file_path, ref)

    client = Partiel({"pom.xml": pom_simple})
    targets = [("ok un", "ok-un"), ("casse", "casse"), ("ok deux", "ok-deux")]

    created, failed = provision_all(
        client, targets, target_group_id=1, project_type="backend",
        template_path="tpl/backend", mirror_dir="/tmp/x", max_parallel=3,
    )

    assert [c["name"] for c in created] == ["ok un", "ok deux"]
    assert len(failed) == 1 and failed[0]["name"] == "casse"
    assert "artifactId" in failed[0]["error"]
