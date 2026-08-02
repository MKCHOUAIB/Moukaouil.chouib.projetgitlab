"""Rendu HTML du rapport d'audit GovernX.

Produit une page autonome (CSS inline, aucune ressource externe) pour être
consultable directement depuis les artefacts GitLab.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape

_CSS = """
:root {
  --bg: #f6f7f9; --card: #ffffff; --fg: #1b1f24; --muted: #5c6773;
  --border: #e1e5ea; --head: #f0f2f5;
  --ok-bg: #e6f6ec; --ok-fg: #1a7f42; --ko-bg: #fdeaea; --ko-fg: #b3261e;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14171a; --card: #1c2024; --fg: #e6e9ec; --muted: #9aa4af;
    --border: #2c3238; --head: #23282e;
    --ok-bg: #12301e; --ok-fg: #5fd68a; --ko-bg: #3a1614; --ko-fg: #ff8a80;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 2rem 1rem; background: var(--bg); color: var(--fg);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
  font-size: 15px; line-height: 1.5;
}
.wrap { max-width: 1080px; margin: 0 auto; }
h1 { font-size: 1.45rem; margin: 0 0 .25rem; }
h2 { font-size: 1.1rem; margin: 2rem 0 .75rem; }
.sub { color: var(--muted); font-size: .875rem; margin: 0 0 1.5rem; }
.card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 10px; padding: 1.25rem; margin-bottom: 1.5rem;
}
.project { margin-top: 2.5rem; }
.project h2 { display: flex; align-items: center; flex-wrap: wrap; gap: .6rem; }
h3 { font-size: .8rem; text-transform: uppercase; letter-spacing: .04em;
     color: var(--muted); margin: 0 0 .6rem; }
h3 + .table-scroll, h3 + p { margin-bottom: 1.25rem; }
.card > h3:not(:first-child) { margin-top: 1.5rem; }
.meta { display: flex; flex-wrap: wrap; gap: 1.5rem 2.5rem; }
.meta div { min-width: 150px; }
.meta dt { color: var(--muted); font-size: .75rem; text-transform: uppercase;
           letter-spacing: .04em; margin: 0 0 .3rem; }
.meta dd { margin: 0; font-weight: 600; }
.badge {
  display: inline-block; padding: .18rem .6rem; border-radius: 999px;
  font-size: .78rem; font-weight: 700; letter-spacing: .02em;
}
.badge.ok { background: var(--ok-bg); color: var(--ok-fg); }
.badge.ko { background: var(--ko-bg); color: var(--ko-fg); }
.badge.big { font-size: .95rem; padding: .3rem .9rem; }
.table-scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: .9rem; }
th, td { text-align: left; padding: .6rem .7rem; border-bottom: 1px solid var(--border); vertical-align: top; }
th { background: var(--head); font-size: .75rem; text-transform: uppercase;
     letter-spacing: .04em; color: var(--muted); white-space: nowrap; }
tbody tr:last-child td { border-bottom: none; }
code, .mono { font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
              font-size: .85em; }
.empty { color: var(--muted); font-style: italic; }
footer { color: var(--muted); font-size: .8rem; text-align: center; margin-top: 2rem; }
"""


def _badge(compliant: bool, ok_label: str = "CONFORME", ko_label: str = "NON CONFORME",
           big: bool = False) -> str:
    cls = "ok" if compliant else "ko"
    size = " big" if big else ""
    label = ok_label if compliant else ko_label
    return f'<span class="badge {cls}{size}">{escape(label)}</span>'


def _target(entry: dict) -> str:
    """Cible lisible d'une règle : branche, pattern de tag, ou projet entier."""
    if entry.get("branch"):
        return f"<code>{escape(str(entry['branch']))}</code>"
    if entry.get("pattern"):
        source = entry.get("manifest") or entry.get("project_type")
        suffix = f" <span class=\"empty\">({escape(str(source))})</span>" if source else ""
        return f"<code>{escape(str(entry['pattern']))}</code>{suffix}"
    return '<span class="empty">projet</span>'


def _results_table(results: list[dict]) -> str:
    if not results:
        return '<p class="empty">Aucune vérification exécutée.</p>'

    rows = []
    for r in results:
        rows.append(
            "<tr>"
            f"<td>{_badge(bool(r.get('compliant')), 'OK', 'NON')}</td>"
            f"<td><code>{escape(str(r.get('rule', '')))}</code></td>"
            f"<td>{_target(r)}</td>"
            f"<td>{escape(str(r.get('details', '')))}</td>"
            "</tr>"
        )
    return (
        '<div class="table-scroll"><table><thead><tr>'
        "<th>Statut</th><th>Règle</th><th>Cible</th><th>Détails</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def _fixes_table(fixes: list[dict]) -> str:
    if not fixes:
        return '<p class="empty">Aucun correctif appliqué.</p>'

    rows = []
    for f in fixes:
        mode = "Dry-run" if f.get("dry_run") else "Appliqué"
        rows.append(
            "<tr>"
            f"<td>{_badge(bool(f.get('success')), 'OK', 'ÉCHEC')}</td>"
            f"<td><code>{escape(str(f.get('rule', '')))}</code></td>"
            f"<td>{_target(f)}</td>"
            f"<td>{escape(str(f.get('action', '')))}</td>"
            f"<td>{escape(mode)}</td>"
            f"<td>{escape(str(f.get('details', '')))}</td>"
            "</tr>"
        )
    return (
        '<div class="table-scroll"><table><thead><tr>'
        "<th>Statut</th><th>Règle</th><th>Cible</th><th>Action</th><th>Mode</th><th>Détails</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def _project_blocks(report: dict) -> list[dict]:
    """Normalise le rapport en liste de blocs projet.

    Accepte la forme multi-projets (clé "projects") et l'ancienne forme à plat
    (results/fixes au premier niveau, un seul projet)."""
    projects = report.get("projects")
    if projects is not None:
        return list(projects)
    return [{
        "project": report.get("project", ""),
        "compliant": bool(report.get("compliant")),
        "results": report.get("results") or [],
        "fixes": report.get("fixes") or [],
    }]


def _overview_table(blocks: list[dict]) -> str:
    """Vue d'ensemble : une ligne par projet, affichée dès qu'il y en a plusieurs."""
    rows = []
    for block in blocks:
        results = block.get("results") or []
        ok = sum(1 for r in results if r.get("compliant"))
        fixes = block.get("fixes") or []
        fix_summary = (
            f"{sum(1 for f in fixes if f.get('success'))} / {len(fixes)}" if fixes else "—"
        )
        rows.append(
            "<tr>"
            f"<td>{_badge(bool(block.get('compliant')))}</td>"
            f"<td><code>{escape(str(block.get('project', '')))}</code></td>"
            f"<td>{ok} / {len(results)}</td>"
            f"<td>{fix_summary}</td>"
            "</tr>"
        )
    return (
        '<div class="table-scroll"><table><thead><tr>'
        "<th>Statut</th><th>Projet</th><th>Règles OK</th><th>Correctifs réussis</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def _project_section(block: dict) -> str:
    project = escape(str(block.get("project", "")))
    return f"""  <section class="project">
    <h2><code>{project}</code> {_badge(bool(block.get('compliant')))}</h2>
    <div class="card">
      <h3>Vérifications</h3>
      {_results_table(block.get('results') or [])}
      <h3>Correctifs</h3>
      {_fixes_table(block.get('fixes') or [])}
    </div>
  </section>"""


def render_report_html(report: dict, generated_at: datetime | None = None) -> str:
    """Sérialise le rapport d'audit en page HTML autonome."""
    blocks = _project_blocks(report)
    compliant = bool(report.get("compliant"))
    total_projects = len(blocks)
    ok_projects = sum(1 for b in blocks if b.get("compliant"))

    stamp = (generated_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M:%S UTC")

    if total_projects == 1:
        subtitle = f"<code>{escape(str(blocks[0].get('project', '')))}</code>"
        overview = ""
    else:
        subtitle = f"{total_projects} projets audités"
        overview = f'  <h2>Vue d\'ensemble</h2>\n  <div class="card">{_overview_table(blocks)}</div>\n'

    sections = "\n".join(_project_section(b) for b in blocks)

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rapport d'audit GovernX</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
  <h1>Rapport d'audit GovernX</h1>
  <p class="sub">{subtitle} — généré le {escape(stamp)}</p>

  <div class="card">
    <dl class="meta">
      <div><dt>Conformité globale</dt><dd>{_badge(compliant, big=True)}</dd></div>
      <div><dt>Projets conformes</dt><dd>{ok_projects} / {total_projects}</dd></div>
      <div><dt>Auto-fix demandé</dt><dd>{'Oui' if report.get('auto_fix_applied') else 'Non'}</dd></div>
      <div><dt>Acceptation non-conforme</dt>
           <dd>{'Oui' if report.get('accepted_noncompliant') else 'Non'}</dd></div>
    </dl>
  </div>

{overview}{sections}

  <footer>GovernX — pipeline de création de projet</footer>
</div>
</body>
</html>
"""
