"""Fixtures partagées — aucune dépendance réseau, aucun vrai GitLab."""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

# Les tests importent `ci.*` et `audit_tool.*` depuis la racine du pipeline.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# python-gitlab n'est utilisé qu'à l'exécution réelle ; les règles sont testées
# contre des objets simulés, on évite d'en faire une dépendance de test.
if "gitlab" not in sys.modules:
    try:
        import gitlab  # noqa: F401
    except ModuleNotFoundError:
        stub = types.ModuleType("gitlab")
        stub.exceptions = types.SimpleNamespace(GitlabGetError=Exception)
        stub.Gitlab = object
        sys.modules["gitlab"] = stub


POM_SIMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>ma.cih</groupId>
  <artifactId>simple-springboot-app</artifactId>
  <version>0.0.1-SNAPSHOT</version>
</project>
"""

# Piège : artifactId sous <parent> ET sous <dependency>, avant et après le vrai.
POM_NESTED = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.2.0</version>
  </parent>
  <groupId>ma.cih</groupId>
  <artifactId>simple-springboot-app</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
  </dependencies>
</project>
"""

PACKAGE_JSON_SIMPLE = """{
  "name": "simple-react-app",
  "version": "0.1.0",
  "private": true,
  "dependencies": {
    "react": "^18.2.0"
  }
}
"""


class FakeFile:
    def __init__(self, content: str) -> None:
        self._content = content

    def decode(self):
        return self._content.encode("utf-8")


class FakeFiles:
    def __init__(self, by_path: dict[str, str]) -> None:
        self.by_path = by_path

    def get(self, file_path: str, ref: str):
        if file_path not in self.by_path:
            raise RuntimeError(f"404 File Not Found: {file_path}")
        return FakeFile(self.by_path[file_path])


class FakeTag:
    def __init__(self, name: str, levels: list[int], mgr=None) -> None:
        self.name = name
        self.create_access_levels = [{"access_level": lvl} for lvl in levels]
        self._mgr = mgr

    def delete(self):
        if self._mgr:
            self._mgr.items = [i for i in self._mgr.items if i is not self]


class FakeTagManager:
    def __init__(self, items: list[FakeTag]) -> None:
        self.items = list(items)
        self.created: list[dict] = []
        for i in self.items:
            i._mgr = self

    def list(self, get_all=True):
        return list(self.items)

    def create(self, data: dict):
        self.created.append(dict(data))
        tag = FakeTag(data["name"], [data["create_access_level"]], self)
        self.items.append(tag)
        return tag


class FakeProject:
    """Projet python-gitlab simulé, strict sur la ref demandée."""

    def __init__(self, files: dict[str, str], *, default_branch="master",
                 tags: list[FakeTag] | None = None, tree_error: str | None = None) -> None:
        self.path_with_namespace = "grp/projet"
        self.default_branch = default_branch
        self.files = FakeFiles(files)
        self.protectedtags = FakeTagManager(tags or [])
        self._paths = list(files)
        self._tree_error = tree_error

    def repository_tree(self, ref, recursive, get_all):
        if self._tree_error:
            raise RuntimeError(self._tree_error)
        if ref != self.default_branch:
            raise RuntimeError(f"404 Tree Not Found for ref '{ref}'")
        return [{"path": p, "type": "blob"} for p in self._paths]


@pytest.fixture
def pom_simple() -> str:
    return POM_SIMPLE


@pytest.fixture
def pom_nested() -> str:
    return POM_NESTED


@pytest.fixture
def package_json_simple() -> str:
    return PACKAGE_JSON_SIMPLE
