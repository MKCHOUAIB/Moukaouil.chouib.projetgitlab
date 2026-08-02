"""Stage 3 — Audit de conformité du/des projet(s) importé(s).

Multi-projets : chaque projet listé dans NEW_PROJECT_PATHS est audité
indépendamment (en parallèle), et un rapport unique agrège les résultats aux
formats JSON, TXT et HTML.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

from audit_tool.gitlab_client import get_gitlab_connection, get_project
from audit_tool.report_html import render_report_html
from audit_tool.rules.pipeline_success import check_pipeline_success, fix_pipeline_success
from audit_tool.rules.protected_branches import check_protected_branches, fix_protected_branches
from audit_tool.rules.protected_tags import check_protected_tags, fix_protected_tags
from ci.lib.projects import max_parallel, read_project_paths

# python-gitlab n'offre aucune garantie de thread-safety : une connexion par thread.
_thread_state = threading.local()


def _connection(server_url: str, token: str):
    if not hasattr(_thread_state, "gl"):
        _thread_state.gl = get_gitlab_connection(server_url, token)
    return _thread_state.gl


def run_checks(project) -> list[dict]:
    results: list[dict] = []
    results.extend(check_protected_branches(project))
    results.append(check_protected_tags(project))
    results.append(check_pipeline_success(project))
    return results


def apply_fixes(project, results: list[dict], tier: str = "free") -> list[dict]:
    fixes: list[dict] = []
    for r in results:
        if r["compliant"]:
            continue
        if r["rule"] == "protected_branches":
            fixes.append(fix_protected_branches(project, r, tier=tier))
        elif r["rule"] == "protected_tags":
            fixes.append(fix_protected_tags(project, r))
        elif r["rule"] == "pipeline_success":
            fixes.append(fix_pipeline_success(project))
    return fixes


def audit_project(project, auto_fix: bool, tier: str) -> dict:
    """Audite un projet et retourne son bloc de rapport."""
    results = run_checks(project)
    fixes: list[dict] = []

    if auto_fix:
        fixes = apply_fixes(project, results, tier=tier)
        results = run_checks(project)  # re-vérifie après correctifs pour un rapport à jour

    return {
        "project": project.path_with_namespace,
        "compliant": all(r["compliant"] for r in results),
        "results": results,
        "fixes": fixes,
    }


def audit_all(server_url: str, token: str, project_paths: list[str],
              auto_fix: bool, tier: str) -> list[dict]:
    """Audite tous les projets en parallèle, en conservant l'ordre d'entrée.

    Un projet injoignable produit un bloc non conforme au lieu de faire échouer
    le stage : le rapport doit couvrir l'ensemble du lot.
    """
    def worker(project_path: str) -> dict:
        try:
            project = get_project(_connection(server_url, token), project_path)
            block = audit_project(project, auto_fix, tier)
        except Exception as exc:  # noqa: BLE001 — l'erreur est reportée dans le rapport
            print(f"  [KO]  {project_path} : {exc}")
            return {
                "project": project_path,
                "compliant": False,
                "results": [{
                    "rule": "audit",
                    "project": project_path,
                    "compliant": False,
                    "details": f"Audit impossible : {exc}",
                }],
                "fixes": [],
            }

        print(f"  [{'OK' if block['compliant'] else 'NON'}]  {project_path}")
        return block

    workers = max(1, min(max_parallel(), len(project_paths)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(worker, project_paths))


def write_reports(reports_dir: str, report: dict) -> tuple[str, str, str]:
    json_path = os.path.join(reports_dir, "audit_report.json")
    txt_path = os.path.join(reports_dir, "audit_report.txt")
    html_path = os.path.join(reports_dir, "audit_report.html")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    projects = report["projects"]
    compliant_count = sum(1 for p in projects if p["compliant"])

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("=== RAPPORT D'AUDIT GOVERNX ===\n")
        f.write(f"Projets audités: {len(projects)}\n")
        f.write(f"Conforme: {'OUI' if report['compliant'] else 'NON'} "
                f"({compliant_count}/{len(projects)} projet(s) conforme(s))\n")
        f.write(f"Auto-fix demandé: {report['auto_fix_applied']}\n")
        f.write(f"Acceptation non-conforme: {report['accepted_noncompliant']}\n")

        for block in projects:
            f.write(f"\n--- {block['project']} — "
                    f"{'CONFORME' if block['compliant'] else 'NON CONFORME'} ---\n")
            for r in block["results"]:
                label = r.get("branch") or r.get("pattern") or r["rule"]
                status = "OK" if r["compliant"] else "NON"
                f.write(f"[{status}] {r['rule']} ({label}) — {r['details']}\n")
            for fix in block["fixes"]:
                status = "OK" if fix.get("success") else "ECHEC"
                f.write(f"[FIX {status}] {fix['rule']} — {fix.get('action', '')} "
                        f"— {fix.get('details', '')}\n")

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render_report_html(report))

    return json_path, txt_path, html_path


def main() -> None:
    project_paths = read_project_paths()
    server_url = os.getenv("CI_SERVER_URL", "").strip()
    token = os.getenv("GITLAB_API_TOKEN", "").strip()
    audit_auto_fix = os.getenv("AUDIT_AUTO_FIX", "no").strip().lower() in ("yes", "true", "1")
    accept_noncompliant = os.getenv("AUDIT_ACCEPT_NONCOMPLIANT", "no").strip().lower() in ("yes", "true", "1")
    audit_tier = os.getenv("AUDIT_TIER", "free").strip().lower()
    if audit_tier not in ("free", "premium"):
        sys.stderr.write(f"AUDIT_TIER='{audit_tier}' invalide, retombe sur 'free'.\n")
        audit_tier = "free"

    if not project_paths:
        sys.stderr.write(
            "Erreur critique : Aucun projet dans NEW_PROJECT_PATHS/NEW_PROJECT_PATH. "
            "Le stage create_project a-t-il réussi ?\n"
        )
        sys.exit(1)
    if not server_url or not token:
        sys.stderr.write("Erreur critique : CI_SERVER_URL ou GITLAB_API_TOKEN manquant.\n")
        sys.exit(1)

    reports_dir = os.path.abspath("reports")
    os.makedirs(reports_dir, exist_ok=True)

    print(f"Audit de {len(project_paths)} projet(s)...")
    projects = audit_all(server_url, token, project_paths, audit_auto_fix, audit_tier)

    is_compliant = all(block["compliant"] for block in projects)

    report = {
        "compliant": is_compliant,
        "auto_fix_applied": audit_auto_fix,
        "accepted_noncompliant": accept_noncompliant,
        "projects": projects,
    }

    json_path, txt_path, html_path = write_reports(reports_dir, report)
    print(f"Rapport d'audit généré dans '{json_path}', '{txt_path}' et '{html_path}'.")

    if is_compliant:
        print(f"Audit de conformité réussi sur {len(projects)} projet(s).")
        sys.exit(0)

    noncompliant = [b["project"] for b in projects if not b["compliant"]]

    if accept_noncompliant:
        print(
            f"ATTENTION : {len(noncompliant)} projet(s) non-conforme(s) ({', '.join(noncompliant)}), "
            "mais le pipeline continue car AUDIT_ACCEPT_NONCOMPLIANT=yes."
        )
        sys.exit(0)

    sys.stderr.write(
        f"Erreur critique : {len(noncompliant)} projet(s) ne respectent pas les critères de "
        f"conformité audit ({', '.join(noncompliant)}) et AUDIT_ACCEPT_NONCOMPLIANT n'est pas "
        "activé (yes). Pipeline bloqué.\n"
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
