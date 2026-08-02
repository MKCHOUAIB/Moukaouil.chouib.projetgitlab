MAINTAINER = 40
OWNER = 50


def detect_version_pattern(project):
    default_branch = project.default_branch or "main"

    try:
        tree = project.repository_tree(ref=default_branch, recursive=True, get_all=True)
    except Exception as e:
        print(f"[DEBUG] Impossible de lister l'arbre du repo sur '{default_branch}' : {e}")
        return None, None

    filenames = {item["path"].split("/")[-1] for item in tree if item["type"] == "blob"}

    if "pom.xml" in filenames:
        return "*", "maven"

    if "package.json" in filenames:
        return "v*", "npm"

    return None, None


def check_protected_tags(project):
    pattern, project_type = detect_version_pattern(project)

    if pattern is None:
        return {
            "rule": "protected_tags",
            "project": project.path_with_namespace,
            "compliant": False,
            "details": "Aucun pom.xml ni package.json trouvé — impossible de déterminer le pattern de version",
            "pattern": None,
            "project_type": None,
        }

    protected_tags = project.protectedtags.list(get_all=True)
    matching_rule = next((pt for pt in protected_tags if pt.name == pattern), None)

    if matching_rule is None:
        return {
            "rule": "protected_tags",
            "project": project.path_with_namespace,
            "compliant": False,
            "details": f"Aucune règle de protected tag pour le pattern '{pattern}'",
            "pattern": pattern,
            "project_type": project_type,
        }

    actual_create = {lvl["access_level"] for lvl in matching_rule.create_access_levels}

    if actual_create == {MAINTAINER}:
        return {
            "rule": "protected_tags",
            "project": project.path_with_namespace,
            "compliant": True,
            "details": "OK",
            "pattern": pattern,
            "project_type": project_type,
        }
    else:
        return {
            "rule": "protected_tags",
            "project": project.path_with_namespace,
            "compliant": False,
            "details": f"Création attendue=Maintainer uniquement, trouvé={actual_create}",
            "pattern": pattern,
            "project_type": project_type,
        }


