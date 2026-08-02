MAINTAINER = 40
DEVELOPER = 30


EXPECTED_RULES = [
    {"pattern": "main", "push": {MAINTAINER}, "merge": {MAINTAINER}},
    {"pattern": "develop", "push": {MAINTAINER}, "merge": {DEVELOPER}},
    {"pattern": "release/*", "push": {MAINTAINER}, "merge": {DEVELOPER}},
]


def check_protected_branches(project):
    results = []
    protected_branches = project.protectedbranches.list(get_all=True)
    protected_by_name = {pb.name: pb for pb in protected_branches}

    for rule in EXPECTED_RULES:
        branch_name = rule["pattern"]
        pb = protected_by_name.get(branch_name)

        if pb is None:
            results.append({
                "rule": "protected_branches",
                "project": project.path_with_namespace,
                "branch": branch_name,
                "compliant": False,
                "details": "Règle absente : la branche n'est pas protégée",
            })
            continue

        actual_push = {lvl["access_level"] for lvl in pb.push_access_levels}
        actual_merge = {lvl["access_level"] for lvl in pb.merge_access_levels}

        push_ok = actual_push == rule["push"]
        merge_ok = actual_merge == rule["merge"]

        if push_ok and merge_ok:
            results.append({
                "rule": "protected_branches",
                "project": project.path_with_namespace,
                "branch": branch_name,
                "compliant": True,
                "details": "OK",
            })
        else:
            problems = []
            if not push_ok:
                problems.append(f"push attendu={rule['push']} trouvé={actual_push}")
            if not merge_ok:
                problems.append(f"merge attendu={rule['merge']} trouvé={actual_merge}")
            results.append({
                "rule": "protected_branches",
                "project": project.path_with_namespace,
                "branch": branch_name,
                "compliant": False,
                "details": "; ".join(problems),
            })

    return results

