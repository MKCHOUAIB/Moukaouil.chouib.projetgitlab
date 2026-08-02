"""Stage 2 — Application des topics GitLab sur le(s) projet(s) importé(s).

Le protected tag n'est plus créé ici (déplacé vers audit_check.py,: réutiliser la logique/règles réelles du audit_tool).

Multi-projets : tous les projets listés dans NEW_PROJECT_PATHS reçoivent les
mêmes topics (ils partagent PROJECT_TYPE), traités en parallèle.
"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor

from ci.lib.gitlab_api import GitLabAPIClient, GitLabAPIError
from ci.lib.projects import max_parallel, read_project_paths

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


def apply_topics(client: GitLabAPIClient, project_paths: list[str], topics: list[str]) -> list[dict]:
    """Applique les topics à chaque projet ; retourne la liste des échecs."""
    def worker(project_path: str) -> dict | None:
        try:
            client.update_project_topics(project_path, topics)
            print(f"  [OK]  {project_path}")
            return None
        except GitLabAPIError as exc:
            print(f"  [KO]  {project_path} : {exc}")
            return {"project": project_path, "error": str(exc)}

    workers = max(1, min(max_parallel(), len(project_paths)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        outcomes = list(pool.map(worker, project_paths))

    return [o for o in outcomes if o is not None]


def main() -> None:
    project_paths = read_project_paths()
    project_type = os.getenv("PROJECT_TYPE", "").strip()

    if not project_paths:
        sys.stderr.write(
            "Erreur critique : Aucun projet dans NEW_PROJECT_PATHS/NEW_PROJECT_PATH. "
            "Le stage create_project a-t-il réussi ?\n"
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
    print(f"Application des topics {topics} sur {len(project_paths)} projet(s)...")

    failures = apply_topics(client, project_paths, topics)

    if failures:
        sys.stderr.write(
            f"Erreur critique : topics non appliqués sur {len(failures)} projet(s) : "
            + "; ".join(f"{f['project']} ({f['error']})" for f in failures)
            + "\n"
        )
        sys.exit(1)

    print(f"Topics configurés avec succès sur {len(project_paths)} projet(s).")


if __name__ == "__main__":
    main()
