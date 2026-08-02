def check_pipeline_success(project):
    is_compliant = getattr(project, "only_allow_merge_if_pipeline_succeeds", False)
    
    return {
        "rule": "pipeline_must_succeed",
        "project": project.path_with_namespace,
        "compliant": is_compliant,
        "details": "OK" if is_compliant else "L'option 'Pipeline must succeed' est désactivée",
    }