import csv
import html
import json
import os
from datetime import datetime


def generate_csv_report(all_results, filepath="audit_report.csv"):
    fieldnames = ["rule", "project", "compliant", "details"]
    extra_keys = set()
    for result in all_results:
        extra_keys.update(result.keys())
    extra_keys -= set(fieldnames)
    fieldnames += sorted(extra_keys)

    try:
        with open(filepath, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, restval="")
            writer.writeheader()
            writer.writerows(all_results)
        print(f"Rapport CSV généré : {filepath}")
    except OSError as e:
        print(f"Erreur lors de l'écriture du CSV : {e}")


def generate_json_report(all_results, filepath="audit_report.json"):
    try:
        with open(filepath, mode="w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
        print(f"Rapport JSON généré : {filepath}")
    except OSError as e:
        print(f"Erreur lors de l'écriture du JSON : {e}")


def generate_html_report(all_results, filepath="audit_report.html"):
    rows_html = ""
    for result in all_results:
        is_fix_row = "success" in result
        rule_label = result.get("rule", "")
        if result.get("branch"):
            rule_label += f" ({result['branch']})"

        if is_fix_row:
            status_class = "fixed" if result.get("success") else "warn"
            status_icon = "🔧" if result.get("success") else "⚠️"
            action = result.get("action", "")
            details = result.get("details", "")
            detail_text = f"{action} — {details}" if action else details
        else:
            status_class = "ok" if result.get("compliant") else "fail"
            status_icon = "✅" if result.get("compliant") else "❌"
            detail_text = result.get("details", "")

        project_text = result.get("project", "")

        rows_html += f"""
        <tr class="{status_class}">
            <td>{status_icon}</td>
            <td>{html.escape(rule_label)}</td>
            <td>{html.escape(project_text)}</td>
            <td>{html.escape(detail_text)}</td>
        </tr>"""

    html_content = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Rapport d'audit GitLab - CIH Bank</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
        th {{ background-color: #333; color: white; }}
       tr.ok {{ background-color: #e6ffe6; }}
        tr.fail {{ background-color: #ffe6e6; }}
        tr.fixed {{ background-color: #e6f0ff; }}
        tr.warn {{ background-color: #fff3e0; }}
    </style>
</head>
<body>
    <h1>Rapport d'audit de conformité GitLab</h1>
    <p>Total : {len(all_results)} résultats</p>
    <table>
        <tr>
            <th>Statut</th><th>Règle</th><th>Projet</th><th>Détails</th>
        </tr>
        {rows_html}
    </table>
</body>
</html>"""

    try:
        with open(filepath, mode="w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"Rapport HTML généré : {filepath}")
    except OSError as e:
        print(f"Erreur lors de l'écriture du HTML : {e}")


def generate_report(all_results, output_prefix="audit_report"):
    # Crée reports/<date_heure_du_run>/ automatiquement si besoin
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    report_dir = os.path.join("reports", timestamp)
    os.makedirs(report_dir, exist_ok=True)

    base_path = os.path.join(report_dir, output_prefix)

    generate_csv_report(all_results, f"{base_path}.csv")
    generate_json_report(all_results, f"{base_path}.json")
    generate_html_report(all_results, f"{base_path}.html")

    print(f"\nTous les rapports ont été générés dans : {report_dir}/")