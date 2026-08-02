import gitlab
from urllib.parse import quote

VALID_ACCESS_TYPES = {"push", "merge", "both"}


def check_specific_user_access(project, user_ids, tier="free", branches=None):
    """
    user_ids : liste d'IDs GitLab déjà résolus (int)
    branches : dict {branch_name: access_type} — access_type dans {"push", "merge", "both"}
               Utilisé uniquement si tier="premium". Ignoré si tier="free".
               Exemple : {"main": "both", "develop": "merge", "release/*": "push"}

    Renvoie toujours une liste de dicts (jamais un dict seul) :
    - tier="free"    : un dict par utilisateur (branch=None)
    - tier="premium" : un dict par couple (utilisateur, branche)
    """
    if not user_ids:
        return []

    if tier == "premium":
        return _check_specific_user_access_premium(project, user_ids, branches)

    return [_check_specific_user_access_free(project, uid) for uid in user_ids]


def _result(project, user_id, compliant, details, branch=None):
    return {
        "rule": "specific_user_access",
        "project": project.path_with_namespace,
        "compliant": compliant,
        "details": details,
        "user_id": user_id,
        "branch": branch,
    }


# --- tier="free" : contournement CE, on joue sur le rôle projet -------------

def _check_specific_user_access_free(project, user_id):
    """
    Élève le rôle projet de l'utilisateur à Developer minimum. Seul levier
    disponible en CE pour donner un accès push/merge sur une branche protégée.
    Toute erreur GitLab est capturée ici pour ne pas interrompre la boucle
    sur les utilisateurs suivants.
    """
    try:
        member = project.members.get(user_id)
    except gitlab.exceptions.GitlabGetError:
        return _add_member_as_developer(project, user_id)
    except gitlab.exceptions.GitlabError as e:
        return _result(project, user_id, False, f"Erreur API GitLab à la lecture du membre : {e}")

    if member.access_level >= gitlab.const.DEVELOPER_ACCESS:
        return _result(project, user_id, True, "OK")

    old_level = member.access_level
    member.access_level = gitlab.const.DEVELOPER_ACCESS
    try:
        member.save()
    except gitlab.exceptions.GitlabError as e:
        return _result(project, user_id, False, f"Échec de l'ajustement du rôle : {e}")

    return _result(project, user_id, True, f"Rôle ajusté de {old_level} à Developer (30)")


def _add_member_as_developer(project, user_id):
    try:
        project.members.create({
            "user_id": user_id,
            "access_level": gitlab.const.DEVELOPER_ACCESS,
        })
    except gitlab.exceptions.GitlabError as e:
        return _result(project, user_id, False, f"Échec de l'ajout au projet : {e}")

    return _result(project, user_id, True, "Utilisateur ajouté au projet avec le rôle Developer (30)")


# --- tier="premium" : accès nommé au niveau de la branche protégée ---------

def _check_specific_user_access_premium(project, user_ids, branches):
    # Sans branches ciblées, la règle n'a rien à vérifier : on la saute
    # proprement plutôt que de remonter de fausses non-conformités.
    if not branches:
        return []

    results = []
    for branch_name, access_type in branches.items():
        if access_type not in VALID_ACCESS_TYPES:
            results.extend(
                _result(project, uid, False,
                        f"access_type invalide pour '{branch_name}' : {access_type}",
                        branch=branch_name)
                for uid in user_ids
            )
            continue
        results.extend(_check_branch_users_access(project, user_ids, branch_name, access_type))
    return results


def _check_branch_users_access(project, user_ids, branch_name, access_type):
    """
    Accorde l'accès nommé (Premium/Ultimate) aux utilisateurs manquants sur une
    branche protégée, via UN SEUL PATCH additif pour toute la branche.

    Contrairement à _fix_protected_branches_premium (diff complet avec _destroy),
    on n'envoie jamais de _destroy et on ne renvoie jamais les entrées déjà
    présentes : les accès existants, par rôle ou par utilisateur, restent intacts.
    """
    want_push = access_type in ("push", "both")
    want_merge = access_type in ("merge", "both")

    try:
        pb = project.protectedbranches.get(branch_name)
    except gitlab.exceptions.GitlabGetError:
        return [
            _result(project, uid, False,
                    f"Branche '{branch_name}' non protégée — accès non accordé "
                    f"(protéger la branche n'est pas du ressort de cette règle)",
                    branch=branch_name)
            for uid in user_ids
        ]
    except gitlab.exceptions.GitlabError as e:
        return [
            _result(project, uid, False,
                    f"Erreur API GitLab à la lecture de la branche '{branch_name}' : {e}",
                    branch=branch_name)
            for uid in user_ids
        ]

    existing_push_ids = _existing_user_ids(pb, "push_access_levels")
    existing_merge_ids = _existing_user_ids(pb, "merge_access_levels")

    missing_push = [uid for uid in user_ids if uid not in existing_push_ids] if want_push else []
    missing_merge = [uid for uid in user_ids if uid not in existing_merge_ids] if want_merge else []

    payload = {}
    if missing_push:
        payload["allowed_to_push"] = [{"user_id": uid} for uid in missing_push]
    if missing_merge:
        payload["allowed_to_merge"] = [{"user_id": uid} for uid in missing_merge]

    patch_error = None
    if payload:
        # quote() indispensable : les patterns type 'release/*' contiennent
        # des caractères à encoder dans le path de l'URL
        encoded_name = quote(branch_name, safe="")
        api_path = f"/projects/{project.id}/protected_branches/{encoded_name}"
        try:
            project.manager.gitlab.http_patch(api_path, post_data=payload)
        except gitlab.exceptions.GitlabError as e:
            patch_error = str(e)

    results = []
    for uid in user_ids:
        granted = []
        if uid in missing_push:
            granted.append("push")
        if uid in missing_merge:
            granted.append("merge")

        if not granted:
            results.append(_result(project, uid, True, "OK", branch=branch_name))
        elif patch_error is None:
            results.append(_result(
                project, uid, True,
                f"Accès {'/'.join(granted)} accordé sur la branche '{branch_name}'",
                branch=branch_name,
            ))
        else:
            results.append(_result(
                project, uid, False,
                f"Échec de l'octroi de l'accès {'/'.join(granted)} "
                f"sur la branche '{branch_name}' : {patch_error}",
                branch=branch_name,
            ))
    return results


def _existing_user_ids(pb, field):
    """IDs des utilisateurs déjà présents dans push_access_levels/merge_access_levels."""
    entries = getattr(pb, field, None) or []
    return {entry.get("user_id") for entry in entries if entry.get("user_id")}


def fix_specific_user_access(project, result):
    pass
