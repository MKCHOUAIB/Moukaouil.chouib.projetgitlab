# GovernX — État d'avancement

> Doc unique et vivante. Remplace `architecture_pipeline_creation_projet.md`, `plan_backstage_govplane.md` et `projet_govplane_devsecops_pipeline.md`. Mettre à jour cette doc au fil de l'eau plutôt que d'en créer une nouvelle.

**Dernière mise à jour :** 27 juillet 2026 (suite de session 4)
**Stagiaire :** Chouaib — CIH Bank
**Encadrante :** Mme. Houda Mouttali

> ⚠️ **Note de synchronisation (24/07)** : une divergence est apparue le 24/07 entre ce doc et une autre source (message relayant des décisions attribuées à l'encadrante, dont une contredisait ce qui était déjà codé/testé ici). Ce doc reste la source de vérité pour cette conversation — si un autre doc/canal dit autre chose, vérifier lequel est à jour avant de coder dessus.

> ⚠️ **Note de synchronisation (27/07)** : l'architecture cross-instance de `create_project.py` (templates sur gitlab.com via `TEMPLATE_GITLAB_URL`/`TEMPLATE_GITLAB_TOKEN`, création sur l'instance locale) a été découverte dans le code réel du repo, jamais discutée dans cette conversation — probablement tranchée directement avec l'encadrante. Documentée ici comme fait constaté (le code tourne), à confirmer. Par ailleurs, `tests/` a disparu du repo réel (jamais commité) et `audit_tool/__init__.py` contenait encore l'ancienne interface stub (`scan_manifests`/`run_audit`/`extract_project_name`) malgré son remplacement prévu le 24/07 — corrigés dans cette session.

> ⚠️ **Note de synchronisation (27/07, suite)** : un run CI réel avec `AUDIT_AUTO_FIX=yes` a révélé un bug de modélisation dans `protected_branches` (voir décision #14) : les fixes étaient déclarés `success: true` mais le re-check après correction échouait toujours sur `develop`/`release/*`. Corrigé. Un test manuel supplémentaire (repo `test-multi-branch` avec plusieurs branches) a permis de confirmer/clarifier le comportement du `mirror clone/push` vis-à-vis des branches, tags, et de leurs réglages de protection respectifs (voir section dédiée ci-dessous).

> ⚠️ **Note de synchronisation (27/07, suite 2)** : le correctif du bug `TypeError: 'int' object is not iterable` (décision #14) était **partiel** lors de son premier passage — seul `sorted(push_expected)` avait été retiré du message `action` de `fix_protected_branches`, `sorted(merge_expected)` restait présent et aurait fait replanter la fonction dès qu'une branche `main`/`develop`/`release/*` non conforme aurait nécessité un fix. Corrigé intégralement (retrait des deux `sorted()` restants sur des scalaires). Par ailleurs, hypothèse erronée levée en session : `fix_protected_tags` (`protected_tags.py`) et `fix_pipeline_success` (`pipeline_success.py`) **existaient déjà** dans le repo réel — `apply_fixes()` dans `audit_check.py` n'était donc pas cassé sur ce point, contrairement à une supposition formulée avant lecture du code réel. La valeur `OWNER_ACCESS_LEVEL = 60` pour `protected_tags` est confirmée correcte (cohérente avec la décision #12, pas de divergence à corriger). Un run de validation fail-closed sur un nouveau projet (`testaudit`, `AUDIT_AUTO_FIX=no`) confirme le comportement attendu.

> ⚠️ **Note de synchronisation (27/07, suite 3)** : comparaison avec un document de référence externe (`RULES_protected_branches_and_tags.md`, vraisemblablement la vraie source `audit_tool` CIH). Deux points vérifiés avec l'encadrante : (1) `protected_tags` — écart initial identifié entre "Owner" (documenté ici) et "Maintainer" (doc de référence) ; tranché : `60` est correct mais correspond au rôle **Admin** (palier spécifique à l'endpoint `protected_tags` de l'API GitLab, distinct des niveaux d'accès membres classiques où Owner=50), pas Maintainer(40) comme dans le doc de référence, ni "Owner" comme documenté avant. Constante renommée `OWNER_ACCESS_LEVEL` → `ADMIN_ACCESS_LEVEL`, aucun changement de valeur. (2) `protected_branches` — le doc de référence introduit une distinction free/premium sur le fix ; confirmé que l'instance locale est en tier Free/CE, donc l'implémentation actuelle (delete+create, seuil simple) reste correcte, pas de dispatcher tier à ajouter (le paramètre `tier="premium"` lève `NotImplementedError` plutôt que d'implémenter du code mort). Structure des deux règles (`EXPECTED_RULES` en liste de dicts, noms de variables) alignée sur le doc de référence par la même occasion.

> ⚠️ **Note de synchronisation (27/07, suite 4)** : run CI réel sur `cih-internship/testfinal2` (`AUDIT_AUTO_FIX=yes`) : `protected_branches` (main/develop/release/*) et `pipeline_success` confirmés **verts après fix** — le correctif décision #14 est validé de bout en bout en conditions réelles. `protected_tags` en échec — cause trouvée : la règle sur la branche principale était en dur sur `"main"`, qui n'existe sur aucun template réel (`testfinal2` a `master` comme branche par défaut, `main` n'existe pas du tout dans le repo). Le fix `protected_branches` avait pourtant déclaré `main` conforme après création de la règle — faux positif : GitLab accepte de créer une règle de protection sur un nom de branche inexistant, donc `master` (la vraie branche principale) restait sans aucune protection sans que ça remonte comme un problème. Corrigé par détection dynamique de la branche principale via `project.default_branch` (voir décision #14, amendement ci-dessous), remplaçant le nom en dur `"main"`. Fallback `or "main"` retiré de `protected_tags.py` pour la même raison. **Reste un doute non résolu** : si le vrai problème était un délai de propagation de la metadata `default_branch` juste après le mirror push (plutôt qu'un nom en dur simplement incorrect), ce correctif rend l'échec explicite mais ne le résout pas forcément — à confirmer au prochain run CI.

---

## Statut global

| Axe | Nom | Statut | Dernière décision |
|---|---|---|---|
| 1 | Pipeline GitLab (fixes + templates) | 🟡 **`protected_branches`/`pipeline_success` confirmés verts après fix en CI réelle (27/07, testfinal2) ; `protected_tags` bloqué par un nom de branche principale en dur (`main`) inexistant sur les templates réels — corrigé par détection dynamique via `project.default_branch` (décision #14, amendement) ; run complet vert de bout en bout toujours à confirmer** | Détection dynamique de la branche principale (amendement décision #14), fallback `main` retiré de `protected_tags.py` |
| 2 | Intégration Backstage | 🔵 Planification | Phase 0 (démo locale) non validée, `skeleton/` vides |
| 3 | Volet DevSecOps (Docker/Trivy) | 🔵 Planification | `.trivyignore` non décidé, aucun run réel |

---

## Axe 1 — Pipeline GitLab (socle)

### Statut : bug branche principale en dur corrigé, pipeline pas encore revalidé au vert bout en bout
Un run réel sur `testfinal2` (27/07) a confirmé `protected_branches` et `pipeline_success` verts après fix. `protected_tags` bloque toujours, cause identifiée et corrigée (voir amendement décision #14 ci-dessous). **Le run complet avec la version corrigée n'a pas encore été confirmé vert de bout en bout.**

### Bug 1 (27/07) — Templates sans topics GitLab (zéro-match `create_project`)
Un run réel a échoué sur `create_project` avec "aucun template trouvé pour PROJECT_TYPE='frontend'", alors que le token et l'architecture cross-instance fonctionnaient correctement (confirmé : `test-backend` avait bien son topic visible par l'API). Cause réelle : les topics GitLab sur `test-frontend`, `test-batch`, `test-dependecie` étaient vides côté API (`topics: []`) — probablement un oubli de clic sur "Save changes" lors d'un ajout précédent dans l'UI GitLab. **Corrigé manuellement** en resauvegardant les topics sur les 3 templates concernés. Confirmé par log CI détaillé de `search_templates_by_topic` (`[search_templates_by_topic] Aucun match... test-frontend (topics: []), ...`).

### Bug 2 (27/07) — Modèle `access_level` incorrect dans `protected_branches`
Après correction du Bug 1, `audit_check` avec `AUDIT_AUTO_FIX=yes` s'est exécuté : `main` passait, mais `develop` et `release/*` restaient non-conformes **après** un fix pourtant déclaré réussi (`"success": true"`). Cause : `BRANCH_RULES` modélisait les niveaux d'accès attendus comme un **ensemble de rôles explicites** (`frozenset({DEVELOPER, MAINTAINER})` = `{30, 40}`), alors que l'API GitLab modélise `access_level` comme un **seuil unique** (un rôle et tout rôle supérieur en hérite automatiquement — pas besoin de lister plusieurs entrées). Résultat : le fix envoyait deux entrées dont une seule persistait côté GitLab (`{40}` au lieu de `{30, 40}` attendu), donc le re-check échouait systématiquement sur les branches à seuil `Developer`.

**Correction appliquée** :
- `BRANCH_RULES` passe d'un modèle `frozenset` à un modèle **valeur unique** (`main: (MAINTAINER, MAINTAINER)`, `develop`/`release/*: (DEVELOPER, MAINTAINER)`).
- `check_protected_branches` compare désormais `{access_level actuel} == {access_level attendu}` (un seul élément de chaque côté).
- `fix_protected_branches` envoie `merge_access_level`/`push_access_level` (champs API "seuil simple") au lieu de `allowed_to_merge`/`allowed_to_push` (champs listes, réservés aux règles granulaires EE/Premium par utilisateur ou groupe spécifique — pas le besoin ici).
- Une régression de syntaxe (`sorted()` appelé sur un `int` après le premier correctif partiel) a été introduite puis corrigée dans la foulée (`TypeError: 'int' object is not iterable`, traceback CI).

⚠️ Ce correctif invalide la partie "niveaux reconstruits depuis les logs de test" de la décision #12 concernant le *format* des données (la valeur des seuils eux-mêmes — Maintainer pour main, Developer+ pour develop/release — reste inchangée et non remise en cause).

### Bug 3 (27/07, suite 4) — Branche principale en dur sur `"main"`, inexistante sur les templates réels
Run CI réel sur `cih-internship/testfinal2` (PROJECT_TYPE=backend, `AUDIT_AUTO_FIX=yes`) : `protected_branches` et `pipeline_success` verts après fix (validation du correctif Bug 2 en conditions réelles), mais `protected_tags` en échec avec "Aucun pom.xml ni package.json trouvé" alors que le projet devait en avoir un (template backend).

Cause trouvée : `EXPECTED_RULES` de `protected_branches.py` et le fallback de `detect_version_pattern` dans `protected_tags.py` supposaient tous deux un nom de branche principale en dur (`"main"`). Vérification manuelle sur `testfinal2` : la branche par défaut réelle est `master`, et `main` **n'existe pas du tout** dans le repo.

Conséquence en deux temps :
1. **`protected_tags`** : `detect_version_pattern` cherchait `pom.xml` sur la ref `main`, qui n'existe pas → exception silencieuse → `(None, None)` → échec du check.
2. **`protected_branches`** (bug plus sournois, faux positif) : le fix a "réussi" à créer une règle de protection sur `main` — GitLab accepte de créer une règle de protection sur un nom de branche qui n'existe pas encore, donc l'appel API renvoie un succès. Le re-check trouvait donc la règle présente et déclarait `main` conforme, **alors que la vraie branche principale (`master`) n'était vérifiée ni protégée par aucune règle**.

**Correction appliquée** (décision explicite : détection dynamique plutôt que substitution `main`→`master` en dur, voir amendement décision #14) :
- `protected_branches.py` : `EXPECTED_RULES` scindé en `STATIC_RULES` (`develop`, `release/*`, inchangés) + une règle dynamique construite par projet via une nouvelle fonction `get_effective_rules(project)`, qui lit `project.default_branch`. Si `default_branch` est vide/None, le check échoue explicitement (`branch: None`, message clair) plutôt que de deviner un nom.
- `protected_tags.py` : le fallback `project.default_branch or "main"` dans `detect_version_pattern` est retiré. Si `default_branch` est vide/None, retour explicite `(None, None)`.

⚠️ **Doute non résolu** : ce correctif suppose que le problème vient du nom en dur. Il reste possible que la vraie cause soit un **délai de propagation** de la metadata `default_branch` côté GitLab juste après un `mirror push` (le job `audit_check` tournant peu après `create_project`/`configure_tags` dans le même pipeline). Si `default_branch` continue de renvoyer vide/None en CI réelle après ce correctif alors qu'il est correctement affiché dans l'UI GitLab, ce sera le signal qu'il faut introduire un délai/retry entre les stages plutôt qu'un problème de code.

### Clarification (27/07) — Ce que `git mirror clone/push` importe réellement
Testé et confirmé via un repo de test dédié (`test-template4274630/test-multi-branch`, créé avec 5 branches : `main`, `develop`, `release/1.0`, `release/2.0`, `feature/test-extra`) :

| | Contenu Git (copié par `mirror clone/push`) | Réglage GitLab (jamais copié) |
|---|---|---|
| Branches | ✅ `Code > Branches` — toutes les branches et leur historique | ❌ `Settings > Repository > Protected branches` — réglage en base, pas dans le repo Git |
| Tags | ✅ `Code > Tags` — tous les tags Git existants | ❌ `Settings > Repository > Protected tags` — réglage en base, pas dans le repo Git |

**Conséquence confirmée** : un projet fraîchement créé par `create_project` a bien toutes les branches/tags du template (le `git push --mirror` les copie automatiquement, contrairement à un push simple qui ne prendrait que la branche par défaut), mais **aucune protection** dessus — c'est `audit_check` (`AUDIT_AUTO_FIX=yes`) qui doit les configurer via l'API, indépendamment de ce qui existait côté template source. Ce comportement est voulu et cohérent avec la décision #12 (les règles de protection viennent du référentiel CIH, pas d'une copie de config du template).

### Validation du comportement fail-closed (27/07)
Un run volontairement lancé **sans** `AUDIT_AUTO_FIX=yes` sur le repo de test `test-multi-branch` a confirmé le comportement attendu : toutes les règles (`protected_branches` sur `main`/`develop`/`release/*`, `protected_tags`, `pipeline_success`) sont détectées non-conformes, aucun fix n'est tenté, le pipeline bloque avec message explicite. `protected_tags` échoue en particulier avec "Aucun pom.xml/package.json détecté" car ce repo de test ne contient qu'un `README.md` — comportement correct vu l'absence de manifeste, pas un bug.

Un second run manuel dédié (27/07, suite 2) sur un nouveau projet `cih-internship/testaudit` avec `AUDIT_AUTO_FIX=no` explicite a reconfirmé ce comportement : 5/5 règles non-conformes détectées, pipeline bloqué proprement, rapport généré.

### Réconciliation avec l'état réel du repo (24/07)
Un envoi du contenu réel du repo (`arborescence_complete.md`) a révélé une divergence avec les corrections précédentes : seuls 2 des 4 bugs de la revue du 23/07 étaient effectivement passés dans le vrai code (`gitlab_api.py` et `.gitlab-ci.yml`). Deux correctifs manquants ont été ré-appliqués sur l'état réel :
- `create_project.py` : `TEMPLATE_VARIANT` était resté en correspondance souple (sous-chaîne) — repassé en égalité stricte.
- `audit_check.py` : le fallback (`run_audit_fallback`) était resté en place — supprimé, échec explicite tant qu'`audit_tool.run_audit` n'est pas implémenté.

Leçon retenue : vérifier l'état réel des fichiers avant d'empiler des corrections, plutôt que de supposer qu'un correctif donné a été appliqué.

### Réconciliation avec l'état réel du repo (27/07)
Nouvel envoi de `arborescence_complete.md` (généré 27/07). Deux écarts trouvés avec la session du 24/07 :
- `audit_tool/__init__.py` était resté dans son ancienne version (`scan_manifests`/`run_audit`/`extract_project_name`) — le remplacement minimal prévu le 24/07 n'était pas passé dans le vrai repo. Ne cassait rien (plus aucun appelant), mais code mort trompeur. **Toujours à corriger** (en cours par Chouaib directement).
- `tests/` (26 tests `pytest`) était absent du repo réel — jamais commité. Le pipeline tournait donc sans filet de sécurité local. **Toujours à recommiter**.
- `README.md` : noté à tort comme "mis à jour 27/07" dans une session précédente — un nouvel envoi de `arborescence_complete.md` a confirmé que le fichier réel était resté dans son ancienne version (structure `audit_tool` obsolète, variables `TEMPLATE_GITLAB_URL`/`TEMPLATE_GITLAB_TOKEN` absentes de la doc infra). **En cours de correction par Chouaib directement.**

### Réconciliation avec l'état réel du repo (01/08)

Lecture directe du repo avant d'implémenter la décision #15. Trois écarts, dont un **critique**, entre ce que ce document déclare fait et ce que le code contient réellement.

**1. Les correctifs de l'amendement 27/07 suite 4 (Bug 3) sont absents du code.** Le document les décrit comme appliqués ; ils ne le sont ni dans le repo, ni dans le dump `arborescence_complete.md` du 27/07 :

| Déclaré appliqué (27/07 suite 3 & 4) | État réel du code |
|---|---|
| `EXPECTED_RULES` scindé en `STATIC_RULES` + `get_effective_rules(project)` | `EXPECTED_RULES` contient toujours `{"pattern": "main", ...}` en dur. `get_effective_rules` **n'existe nulle part** dans le repo. |
| Fallback `default_branch or "main"` retiré de `detect_version_pattern` | Toujours présent (retiré seulement maintenant, par la réécriture #15 — voir plus bas) |
| `OWNER_ACCESS_LEVEL` renommé `ADMIN_ACCESS_LEVEL` | Toujours `OWNER_ACCESS_LEVEL`. Valeur 60 correcte, nom trompeur inchangé. |
| `tier="premium"` lève `NotImplementedError` | `_fix_protected_branches_premium` est **entièrement implémenté** (http_patch, `allowed_to_*`) — ici le code est *en avance* sur le doc |

Datation croisée : le dump 27/07 contient `BRANCH_RULES` (modèle suite 2) alors que le repo contient `EXPECTED_RULES` (suite 3) — le repo est donc **post-suite-3, pré-suite-4**, et la suite 4 n'a jamais atterri dans cette lignée. Reste à vérifier côté instance GitLab (`cih-internship/governx-pipeline`) si elle y a été commitée directement.

⚠️ **`protected_branches.py` n'a volontairement pas été corrigé** dans le cadre de #15 (hors périmètre). Le faux positif décrit au Bug 3 — règle créée sur une branche `main` inexistante, vraie branche principale laissée sans protection — est donc **toujours actif**. C'est le point le plus urgent de la liste "Prochaine étape".

**2. `tests/` était toujours absent** (constaté à chaque réconciliation depuis le 24/07). Recréé et commité dans le cadre de #15, avec `ci/requirements-dev.txt` (également absent malgré sa présence dans l'arborescence documentée).

**3. Écart de niveau d'accès sur les protected tags (`*` = "Maintainers" dans l'UI)** — investigué, **non corrigé** (hors périmètre de #15) :

- `fix_protected_tags` **envoie bien** `create_access_level: 60`. L'hypothèse "le code n'envoie pas 60" est écartée par lecture du code.
- Mais d'après l'historique des runs documentés ici, `fix_protected_tags` **n'a jamais créé de règle avec succès** : `AUDIT_AUTO_FIX=no` sur `test-multi-branch` et `testaudit` (aucun fix tenté), et sur `testfinal2` le check échouait en amont sur la détection du manifeste (`pattern=None` → "Aucune action possible"). Une règle `*` visible dans l'UI ne vient donc **pas** de cette automatisation → **création manuelle antérieure**, ce qui répond à la question posée.
- ⚠️ **Problème latent distinct** : l'API GitLab documente `create_access_level` des protected **tags** avec les valeurs 0/30/40 (défaut 40 = Maintainer) ; 60 (Admin) est documenté pour les protected **branches**. La décision #12 affirme l'inverse ("palier 60 propre à l'endpoint `protected_tags`"). Si GitLab ignore 60 et stocke 40, `levels != {60}` ne pourra **jamais** passer → boucle de non-conformité permanente dès le premier fix réellement exécuté. À trancher par un `GET /projects/:id/protected_tags` juste après un fix réussi : si `access_level` vaut 40, la valeur 60 de la décision #12 est à revoir.

### Architecture actée (ne pas rediscuter)
- **Déclenchement :** pipeline manuel, variables CI/CD (`PROJECT_NAME`, `PROJECT_TYPE` dropdown `batch|dependencie|frontend|backend`, `GROUP_PATH`).
- **Méthode de copie :** `mirror clone + push` (pas fork+unlink, pas export/import natif — aucune métadonnée résiduelle, fonctionne identiquement CE/EE). Copie tout le contenu Git (branches, tags, historique) mais aucun réglage GitLab (protections, settings) — voir clarification ci-dessus.
- **Stages :** `create_project → configure_tags → audit_check`
  - `create_project` : résout le template via **topic GitLab** sur **gitlab.com** (cf. décision #13), mirror-clone + push vers l'instance locale, transmet `NEW_PROJECT_PATH` en dotenv.
  - `configure_tags` : applique uniquement les topics (déterministes depuis `PROJECT_TYPE`, cf. Q1 révisée). Ne crée plus de protected tag (déplacé vers `audit_check`, cf. décision #12).
  - `audit_check` : audite le projet importé via les vraies règles `audit_tool` (`protected_branches`, `protected_tags`, `pipeline_success`) et corrige si `AUDIT_AUTO_FIX=yes`.

### Arborescence (état réel confirmé 27/07)
```
governx-pipeline/
├── .gitlab-ci.yml
├── README.md                     # ⚠️ pas réellement à jour malgré note précédente — en cours de correction par Chouaib
├── ci/
│   ├── __init__.py
│   ├── requirements.txt          # requests, python-gitlab (27/07)
│   ├── requirements-dev.txt      # pytest — créé 01/08 (absent du repo réel jusque-là)
│   ├── create_project.py         # cross-instance + lot multi-projets (29/07) + renommage du manifeste (01/08, #15)
│   ├── configure_tags.py         # simplifié 27/07 : topics uniquement, plus de protected tag ici
│   ├── audit_check.py            # réécrit 27/07 : orchestre les 3 règles audit_tool via python-gitlab
│   └── lib/
│       ├── __init__.py
│       ├── gitlab_api.py         # + list_repository_tree / get_raw_file / create_commit (01/08, #15)
│       └── projects.py           # liste des projets du lot entre stages (29/07)
├── audit_tool/                   # logique/règles reprises du audit_tool CIH (projet séparé), scope réduit au projet importé
│   ├── __init__.py               # ⚠️ ancienne interface stub — extract_project_name réimplémentée dans manifest.py (01/08), le reste reste du code mort
│   ├── manifest.py               # NOUVEAU 01/08 (#15) : slug, localisation fail-closed, lecture/réécriture de l'identifiant
│   ├── gitlab_client.py          # connexion python-gitlab + récupération du projet audité
│   ├── report_html.py            # rendu HTML autonome du rapport d'audit (29/07)
│   └── rules/
│       ├── protected_branches.py # ⚠️ branche principale TOUJOURS en dur sur "main" — correctif 27/07 (suite 4) jamais appliqué, cf. réconciliation 01/08
│       ├── protected_tags.py     # pattern {artifactId}-* dérivé du contenu du manifeste + check/fix (Admin-only) — réécrit 01/08 (#15)
│       └── pipeline_success.py   # "Pipelines must succeed" + check/fix
└── tests/                        # recréé 01/08 (#15) — absent du repo réel depuis le 24/07
    ├── __init__.py
    ├── conftest.py               # fixtures : manifestes types, projet GitLab simulé
    ├── test_manifest.py          # slug, localisation, lecture/réécriture (50 tests)
    ├── test_protected_tags.py    # pattern dérivé du contenu + cas fail-closed (22 tests)
    └── test_create_project_rename.py  # renommage par projet dans le lot (12 tests)
```

### Décisions actées (23 juillet 2026)

1. ~~**Priorité Maven vs npm**~~ ⚠️ **SUPERSÉDÉE le 24/07, voir décision #10** — l'hypothèse de double manifeste ne tient plus.

2. **Zéro/multi-match de template** 🟡 **Statut incertain depuis le 24/07** (voir note ci-dessous)
   - Zéro match sur le topic GitLab → **échec dur** immédiat (pipeline stoppé, message explicite). Confirmé fonctionnel en CI réelle le 27/07 (cause du Bug 1 : topics manquants, pas un défaut du code).
   - Multi-match → **échec dur par défaut**, sauf si une variable de désambiguïsation `TEMPLATE_VARIANT` est fournie explicitement dans le run.
   - ⚠️ Le 24/07, cette décision a été qualifiée de "pas sûre pour le moment" sans raison précisée. `create_project.py` reste codé et testé sur cette base pour l'instant — **rien n'a été changé dans le code**. À clarifier : qu'est-ce qui remet ça en cause, et est-ce que ça affecte réellement le comportement voulu ?

3. **Comportement `audit_check`** ✅ (confirmé inchangé le 24/07, comportement fail-closed validé en CI réelle le 27/07)
   - Le rapport d'audit est **toujours généré**.
   - Variable `AUDIT_AUTO_FIX` (yes/no) déclenche le mode correctif automatique d'`audit_tool`.
   - Si le projet est non-conforme et qu'aucun fix n'est demandé → **pipeline bloqué**, sauf si `AUDIT_ACCEPT_NONCOMPLIANT=yes` est explicitement fourni (traçabilité de l'acceptation).

4. **`TEMPLATE_GROUP_PATH`** ✅ (confirmé inchangé le 24/07)
   Variable CI/CD **masquée et protégée**, définie au niveau du groupe racine GitLab. Non exposée dans le formulaire "Run pipeline" (donnée d'infra, pas un choix utilisateur). Contrainte confirmée le 24/07 : le contenu réel des templates ne peut pas être inspecté à l'avance — le code se base uniquement sur le mapping `PROJECT_TYPE`→stack (décision #10), pas sur un accès direct aux repos templates.

### Décisions d'implémentation (23 juillet 2026)

5. **Langage** ✅ Tout le dossier `ci/` en Python (pas de bash), cohérent avec `audit_tool`.
6. **Garde-fou "pipeline manuel"** ✅ `workflow: rules` global sur `$CI_PIPELINE_SOURCE == "web"`, plutôt que `when: manual` job par job — empêche même la création d'un pipeline hors formulaire "Run pipeline".
7. **Pas de dossier `templates/` local** ✅ Les templates vivent uniquement sur GitLab via `TEMPLATE_GROUP_PATH`, aucune copie de référence dans le repo `governx-pipeline`.

### Décisions complémentaires (23 juillet 2026)

8. **Fallback audit/scan** ✅ Supprimé. `audit_check.py` échoue explicitement (message clair, exit non-zéro) tant qu'`audit_tool.run_audit` lève `NotImplementedError`, plutôt que d'utiliser une logique de repli locale qui masquerait l'absence de logique métier réelle. (`configure_tags.py` suit désormais la même règle pour `extract_project_name`, cf. #10.)
9. **`TEMPLATE_VARIANT`** ✅ Correspondance **stricte** (égalité exacte sur `name` ou `path` du candidat), pas de sous-chaîne — évite qu'un futur template au nom proche casse silencieusement une désambiguïsation qui marchait avant.

### Décisions actées (24 juillet 2026)

10. **Q1 révisée — mapping `PROJECT_TYPE` → manifeste déterministe** ✅
    Confirmé par l'encadrante : pas d'ambiguïté possible, chaque `PROJECT_TYPE` correspond à exactement un stack/manifeste.

    | `PROJECT_TYPE` | Stack | Manifeste | Champ nom |
    |---|---|---|---|
    | `backend` | Spring Boot | `pom.xml` | `<artifactId>` |
    | `batch` | Spring Boot | `pom.xml` | `<artifactId>` |
    | `dependencie` | Spring Boot | `pom.xml` | `<artifactId>` |
    | `frontend` | React | `package.json` | `name` |

    Conséquences :
    - **Remplace entièrement** la décision #1 (priorité Maven/npm + tie-breaker) — pas de filet de sécurité conservé, la coexistence des deux manifestes est structurellement impossible dans ce mapping.
    - `configure_tags.py` : la fonction `resolve_final_type()` (tie-breaker, 9 cas de test) est **retirée**, remplacée par un simple lookup + vérification de présence du manifeste attendu.
    - Design "registre extensible" (multi-langages Python/.NET/Go/Rust) noté comme extension future possible, **pas à implémenter maintenant**.

11. ~~**Protected tags sur le projet importé (pattern `{nom}-*`, Maintainer)**~~ ⚠️ **SUPERSÉDÉE le 24/07 (même session), voir décision #12** — remplacée par la réutilisation directe des règles du vrai `audit_tool` CIH, pattern générique (pas dérivé du nom) et accès Admin (pas Maintainer). `extract_project_name` et la création du protected tag dans `configure_tags.py` sont retirées.

### Décisions actées (24/07, suite — réutilisation du vrai `audit_tool` CIH)

12. **Réutilisation directe des règles du `audit_tool` CIH** ✅
    Un document décrivant un `audit_tool` déjà construit et testé côté CIH (projet séparé, `projet_audit_gitlab_cih.md`) a été fourni. Décision : ne pas garder l'interface stub inventée précédemment (`extract_project_name`/`run_audit`), mais reprendre la logique/règles réelles, **appliquées au seul projet importé** (pas à toute l'instance comme l'outil CIH original).
    - Règles reprises : `protected_branches` (branche principale + develop/release/*), `protected_tags` (pattern dynamique générique `*`/`v*` selon Maven/npm, accès **Admin** — cf. amendement 27/07 suite 3, palier `60` propre à l'endpoint `protected_tags`, distinct d'Owner=50), `pipeline_success` (`only_allow_merge_if_pipeline_succeeds`).
    - `specific_user_access` explicitement **hors scope** : concerne un utilisateur donné appliqué à tous les projets d'une instance, pas la conformité du projet importé lui-même.
    - `configure_tags.py` simplifié : topics uniquement, ne crée plus le protected tag (déplacé dans `audit_check.py`).
    - `audit_check.py` réécrit : se connecte via `python-gitlab` (nouvelle dépendance), récupère le projet importé, exécute les 3 `check_*`, applique les `fix_*` correspondants si `AUDIT_AUTO_FIX=yes`, re-vérifie, génère le rapport.
    - ⚠️ Les niveaux d'accès exacts pour les branches (règle `protected_branches`) sont **reconstruits depuis les logs de test** du doc CIH, pas du code source littéral (non fourni) — les *valeurs* (Maintainer pour la branche principale, Developer+ pour develop/release) restent la référence, mais le *format* de représentation (liste vs seuil) était erroné, cf. décision #14 ; le *nom de la branche principale* était également erroné (en dur sur `main`), cf. amendement décision #14 (27/07, suite 4).
    - Le scope réel de `GITLAB_API_TOKEN` doit inclure le droit d'écrire les protected branches/tags et les settings de projet (les `fix_*` modifient l'instance) — pas seulement API + push comme documenté jusqu'ici.

13. **Architecture cross-instance de `create_project.py`** ✅ (constatée dans le code réel, 27/07 — jamais discutée dans cette conversation, probablement actée avec l'encadrante ; **confirmée fonctionnelle en CI réelle le 27/07**)
    Les templates vivent sur **gitlab.com**, le nouveau projet est créé sur **l'instance GitLab locale** (celle qui exécute le pipeline). Deux clients `GitLabAPIClient` distincts :
    - `template_client` → `TEMPLATE_GITLAB_URL` (nouvelle variable, défaut `https://gitlab.com`) + `TEMPLATE_GITLAB_TOKEN` (nouvelle variable, **obligatoire**, lecture seule sur gitlab.com).
    - `local_client` → `CI_SERVER_URL` + `GITLAB_API_TOKEN` (existants), écriture sur l'instance locale.
    `TEMPLATE_GROUP_PATH` désigne donc un groupe sur **gitlab.com**, pas sur l'instance locale — à clarifier dans la doc si ce n'était pas déjà le cas avant.

### Décision actée (27 juillet 2026)

14. **Modèle `access_level` pour `protected_branches` : seuil unique, pas un ensemble de rôles** ✅
    Bug trouvé en CI réelle (voir "Bug 2" ci-dessus). L'API GitLab modélise l'accès à une protected branch comme **un seuil minimum** (un `access_level` du type "Developer et tout rôle supérieur"), pas comme une liste explicite de rôles distincts à additionner. `BRANCH_RULES` passe donc de `frozenset[int]` à un simple `int` par branche et par action (merge/push). Champs API utilisés : `merge_access_level`/`push_access_level` (seuil simple), et non `allowed_to_merge`/`allowed_to_push` (listes de dicts, réservées aux règles granulaires EE/Premium par utilisateur ou groupe spécifique — hors scope ici). Les valeurs métier (Maintainer pour la branche principale, Developer+ pour `develop`/`release/*`) restent celles actées en décision #12, seule la représentation technique était fausse.

    **Correctif complémentaire (27/07, suite)** : le premier passage du correctif n'avait retiré `sorted()` que sur `push_expected` dans le message `action` de `fix_protected_branches`, laissant `sorted(merge_expected)` intact — un run CI réel (`python3 -m ci.audit_check`, `AUDIT_AUTO_FIX=yes`) a reproduit le même `TypeError: 'int' object is not iterable`, cette fois sur `merge_expected`. Corrigé en retirant les deux `sorted()` restants (les deux variables sont des `int` scalaires depuis le passage à un modèle seuil unique, `sorted()` n'a jamais été applicable dessus). Leçon retenue : vérifier que toutes les occurrences d'un pattern fautif sont corrigées, pas seulement celle qui apparaît dans la trace de la première erreur.

    **Amendement structurel (27/07, suite 3)** : `EXPECTED_RULES` restructuré en liste de dicts (`{"pattern": ..., "push": {...}, "merge": {...}}`, sets à un seul élément), alignée sur un document de référence externe confirmé comme la vraie source `audit_tool` CIH. Comparaison via égalité de sets à un seul élément — fonctionnellement équivalent à l'`int` scalaire précédent, juste une autre représentation. `fix_protected_branches` prend un paramètre `tier` ("free"/"premium") pour cohérence de signature ; seul `tier="free"` est implémenté (instance locale confirmée CE), `tier="premium"` lève `NotImplementedError` explicitement plutôt que du code mort jamais exercé.

    **Amendement — branche principale dynamique (27/07, suite 4)** : le nom de la branche principale était en dur sur `"main"` dans `EXPECTED_RULES`/`BRANCH_RULES` depuis l'origine de la règle. Run CI réel sur `testfinal2` a révélé que ce nom n'existe sur aucun template réel testé (branche par défaut réelle = `master`). Pire, le fix avait déclaré `main` conforme après avoir créé une règle de protection dessus (GitLab l'accepte même pour une branche inexistante), masquant le fait que la vraie branche principale (`master`) n'était ni vérifiée ni protégée. Corrigé : `EXPECTED_RULES` scindé en règles statiques (`develop`, `release/*`) + une règle dynamique par projet construite via `get_effective_rules(project)`, qui lit `project.default_branch` (pas de fallback deviné — échec explicite si vide/None). Même correction appliquée par cohérence au fallback `or "main"` de `detect_version_pattern` dans `protected_tags.py` (retiré).

### Décision actée (1er août 2026)

15. **Pattern de protected tag dérivé du *contenu* du manifeste, plus de son *type*** ✅
    Le champ identifiant du manifeste (`<artifactId>` racine pour Maven, `"name"` racine pour npm) est réécrit sur un slug kebab-case de `PROJECT_NAME` juste après le mirror push, puis le pattern de protected tag en est dérivé : `{artifactId}-*` au lieu du générique `*`/`v*`.

    **Ce que cette décision renverse** : uniquement la partie "pattern générique par type de manifeste" des décisions #12/#14. Le reste de #12/#14 est **conservé sans changement** — réutilisation des règles réelles du `audit_tool` CIH, structure des règles (`EXPECTED_RULES` en liste de dicts, paramètre `tier`), périmètre limité au projet importé, et surtout `create_access_level = 60` (Admin), qui n'est **pas** concerné par cette décision.

    **Ce que ça reprend de #11** (supersédée le 24/07) : l'idée d'un pattern dérivé du nom du projet, sous la forme `{nom}-*`. #11 reste supersédée pour tout le reste — notamment son niveau d'accès Maintainer et son mécanisme de repli sur le nom GitLab, tous deux abandonnés.

    **Étape 1 — renommage (stage `create_project`)**
    - Slug = `PROJECT_NAME` en kebab-case : minuscules, toute suite de caractères non alphanumériques réduite à un seul `-`, pas de `-` en tête ni en fin. « Simple SpringBoot App » → `simple-springboot-app`, format déjà utilisé par l'`artifactId` des templates.
    - Manifeste cherché dans **toute** l'arborescence via l'API (même approche que l'ancien `detect_version_pattern` — un scan root-only rate `my-app/pom.xml`).
    - Commit via l'API GitLab (`POST /repository/commits`), sur la branche par défaut réelle du projet. Aucun clone local : le clone/push mirror reste cantonné à la copie initiale du template.
    - Réécriture **textuelle ciblée** (diff d'une seule ligne) avec suivi de profondeur, puis relecture structurelle de contrôle : un `<artifactId>` de `<parent>` ou de `<dependency>`, un `"name"` imbriqué (`author.name`) ou un `<artifactId>` en commentaire ne peuvent jamais être touchés.
    - Exécuté **par projet** dans le lot multi-projets, en parallèle. L'échec d'un projet n'interrompt pas les autres.

    **Étape 2 — pattern (`audit_tool/rules/protected_tags.py`)**
    - `detect_version_pattern` (pattern par type) est remplacée par `detect_tag_pattern` (pattern par contenu).
    - La valeur est **relue depuis le manifeste à chaque check et à chaque fix**, jamais reprise du slug calculé à l'étape 1 : `create_project` et `audit_check` sont des jobs CI distincts, repasser par le fichier garde les deux étapes synchronisées par construction plutôt que par convention. `fix_protected_tags` ignore délibérément le `pattern` présent dans le `check_result` qu'on lui passe.

    **Fail-closed** (aucun repli deviné, un pattern faux protégerait les mauvais tags) : aucun manifeste, plusieurs manifestes candidats, deux stacks concurrents, champ identifiant absent/vide/illisible, ou branche par défaut vide/None → erreur explicite. Le check renvoie non-conforme avec la cause, le fix n'écrit rien.

    ⚠️ **Conséquence assumée** : un projet Maven **multi-modules** (POM parent + POM par module) est refusé, car rien ne permet de désigner sans deviner le module porteur de l'identité du projet. À revoir si un template multi-modules entre au catalogue.

    ⚠️ **Deux slugs coexistent** pour un même projet : celui du *path* GitLab (`ci.create_project.slugify`, supprime la ponctuation → `api.v2` = `apiv2`) et celui de l'*identifiant de manifeste* (`audit_tool.manifest.slugify`, convertit la ponctuation en séparateur → `api.v2` = `api-v2`). Ils ne divergent que sur les noms ponctués. Non unifié volontairement : changer le slug de path modifierait l'URL des projets créés, hors périmètre de cette décision.

### `audit_tool` — implémentation (24-27 juillet 2026)
- **`gitlab_client.py`** ✅ Connexion `python-gitlab` (`get_gitlab_connection`) + récupération du projet audité (`get_project`).
- **`manifest.py`** ✅ *(nouveau 01/08, décision #15)* Slug kebab-case, localisation fail-closed du manifeste dans toute l'arborescence, lecture et réécriture ciblée du champ identifiant (`<artifactId>` racine / `"name"` racine). Sans dépendance GitLab : utilisable depuis `ci/` comme depuis `audit_tool/`.
- **`rules/protected_tags.py`** ✅ `detect_tag_pattern` *(remplace `detect_version_pattern` au 01/08, décision #15)* : scan `pom.xml`/`package.json` dans toute l'arborescence via l'API, pas seulement la racine — bug connu côté CIH évité ; branche inspectée = `project.default_branch`, **sans fallback** (le `or "main"` du 27/07 suite 4, jamais réellement retiré, l'est par cette réécriture). Pattern = `{artifactId}-*` relu depuis le manifeste à chaque check **et** à chaque fix. `check_protected_tags`, `fix_protected_tags` (accès Admin — constante toujours nommée `OWNER_ACCESS_LEVEL`, valeur 60, renommage du 27/07 suite 3 jamais appliqué). Échoue proprement si aucun manifeste n'est détectable, si plusieurs candidats existent, si le champ identifiant est absent/illisible, ou si `default_branch` est vide/None.
- **`rules/protected_branches.py`** ✅ `get_effective_rules`/`check_protected_branches`/`fix_protected_branches` pour la branche principale (détectée dynamiquement, 27/07 suite 4) et `develop`/`release/*` (statiques). **Bug de modèle access_level corrigé le 27/07 (décision #14)**, **bug de nom de branche principale en dur corrigé le 27/07 suite 4** — fix testé et confirmé fonctionnel en CI réelle sur `testfinal2` (`main`/`develop`/`release/*` tous verts après fix — mais ce test précédait la découverte du bug de branche principale ; à revalider avec la version corrigée).
- **`rules/pipeline_success.py`** ✅ `check_pipeline_success`/`fix_pipeline_success` (`only_allow_merge_if_pipeline_succeeds`). Confirmé fonctionnel en CI réelle (passe systématiquement au check comme au fix, y compris sur le run `testfinal2` du 27/07 suite 4).
- **Ancienne interface** (`scan_manifests`, `run_audit` placeholder, `extract_project_name`) **retirée du chemin d'exécution** — plus aucun appelant, mais le fichier `audit_tool/__init__.py` contient toujours le code mort au 27/07 (écart trouvé en réconciliation, en cours de correction par Chouaib directement).

### Revue de code — bugs corrigés (23 juillet 2026)
Code généré par IDE à partir d'un prompt de contexte, puis revu. 3 bugs critiques + 1 point de robustesse trouvés et corrigés, avec tests :
- **`gitlab_api.py` / `search_templates_by_topic`** : le filtre incluait à tort tout projet **sans topic du tout** (`or not topics`), cassant la garantie "zéro match → échec dur". Corrigé et testé avec données simulées (cas piège : projet sans topic bien exclu).
- **`configure_tags.py` / tie-breaker** *(obsolète depuis la révision Q1 du 24/07)* : quand `PROJECT_TYPE` contredisait la priorité Maven, le code l'ignorait et forçait `backend` — l'inverse de la décision actée à l'époque. Corrigé et testé sur 9 cas le 23/07 ; la fonction elle-même est retirée le 24/07 suite à la révision de Q1.
- **`.gitlab-ci.yml`** : variable dropdown `PROJECT_TYPE` sans `value` par défaut (requis par GitLab dès qu'`options` est utilisé). `value: "backend"` ajoutée.
- **Robustesse** : `configure_tags.py`/`audit_check.py` faisaient des appels API bruts (`client.session.get(...).json()`) sans passer par la gestion d'erreur commune → plantage non maîtrisé possible sur échec HTTP. Méthode `get_project()` ajoutée au client et utilisée partout.

### Revue de code — bugs corrigés (27 juillet 2026, session CI réelle)
- **`audit_tool/rules/protected_branches.py` / modèle `access_level`** : voir décision #14 ci-dessus. Bug critique — les fixes se déclaraient réussis sans que le re-check confirme la conformité.
- **`audit_tool/rules/protected_branches.py` / régression `TypeError`** : lors du premier correctif partiel du bug ci-dessus, `sorted()` était resté appelé sur les nouvelles valeurs `int` (non-itérables) dans le message `action` de `fix_protected_branches` — crash immédiat en CI (`TypeError: 'int' object is not iterable`). Corrigé dans la foulée (retrait de tous les `sorted()` sur les valeurs désormais scalaires).
- **`audit_tool/rules/protected_branches.py` / nom de branche principale en dur** : voir amendement décision #14 (27/07 suite 4) — bug critique, faux positif masquant l'absence totale de protection sur la vraie branche principale.
- **`audit_tool/rules/protected_tags.py` / fallback `default_branch or "main"`** : retiré pour la même raison (27/07 suite 4) — masquait un échec au lieu de le signaler.
- **Templates gitlab.com sans topics** : pas un bug de code, mais une donnée manquante côté GitLab (topics jamais sauvegardés sur `test-frontend`/`test-batch`/`test-dependecie`). Corrigé manuellement. Sert de rappel : toujours vérifier "Save changes" après ajout d'un topic dans l'UI GitLab.

### Nouvelles variables CI/CD à créer (suite aux décisions ci-dessus)
- `TEMPLATE_VARIANT` (optionnelle, désambiguïsation multi-match, égalité stricte)
- `AUDIT_AUTO_FIX` (yes/no)
- `AUDIT_ACCEPT_NONCOMPLIANT` (yes/no)
- `TEMPLATE_GROUP_PATH` (masquée/protégée, niveau groupe, sur **gitlab.com** — cf. décision #13)
- `TEMPLATE_GITLAB_URL` (masquée/protégée, défaut `https://gitlab.com` — cf. décision #13)
- `TEMPLATE_GITLAB_TOKEN` (masquée/protégée, **nouvelle, obligatoire** — lecture seule sur gitlab.com, cf. décision #13)
- `GITLAB_API_TOKEN` (masquée/protégée, niveau groupe, instance locale — droits API + push + écriture protected branches/tags/settings depuis le 24/07, cf. décision #12)

Le pattern des protected tags (`*`/`v*`, accès Admin) est déterminé dynamiquement par `audit_tool.rules.protected_tags`, aucune variable CI/CD dédiée. La branche principale pour `protected_branches` est désormais aussi déterminée dynamiquement (`project.default_branch`), aucune variable CI/CD dédiée non plus.

### Tests (24-27 juillet 2026)
Trois niveaux, du plus simple au plus complet :
1. **Unitaires** (`pytest tests/`, aucune dépendance externe) — 26 tests écrits et validés en local (désambiguïsation zéro/multi-match, filtre topic, topics déterministes, les 3 règles `audit_tool` avec objets simulés). ⚠️ **Absents du repo réel au 27/07** — jamais commités, à recommiter en priorité. **Non couverts par ces tests** : le bug de modèle `access_level` (décision #14) et le bug de branche principale en dur (amendement 27/07 suite 4) n'auraient probablement pas été détectés par des objets simulés trop permissifs — à renforcer si `tests/` est recommité (mock plus strict sur `protectedbranches.create`, et un cas de test avec `default_branch != "main"`).
2. **Intégration partielle** — `create_project.py` seul contre un vrai groupe GitLab sandbox, validé en sandbox le 24/07 (ancienne architecture, avant le cross-instance — à revalider).
3. **Pipeline complet en CI** 🟡 Plusieurs runs réels le 27/07 : `create_project`/`configure_tags` passent (architecture cross-instance + topics confirmés fonctionnels), `audit_check` a révélé puis vu corriger successivement le bug `access_level` (décision #14) et le bug de branche principale en dur (amendement 27/07 suite 4 — run `testfinal2`, `protected_branches`/`pipeline_success` verts après fix, `protected_tags` en échec, cause corrigée). **Un run complet vert de bout en bout avec `AUDIT_AUTO_FIX=yes` et l'ensemble des correctifs appliqués reste à confirmer.**
4. **Test manuel dédié (27/07)** — repo `test-template4274630/test-multi-branch` créé avec 5 branches pour valider empiriquement le comportement du `mirror clone/push` (branches/tags copiés, protections jamais copiées). Confirmé conforme à l'architecture voulue.
5. **Test manuel dédié (27/07, suite 2)** — run réel sur un nouveau projet `cih-internship/testaudit` avec `AUDIT_AUTO_FIX=no` explicite : les 5 règles (`protected_branches` × 3 branches, `protected_tags`, `pipeline_success`) sont détectées non-conformes comme attendu pour un projet fraîchement importé (aucune protection copiée par le mirror push), aucun fix tenté, pipeline bloqué avec message explicite et rapport généré (`audit_report.json`/`.txt`). Confirme une nouvelle fois le comportement fail-closed sur un cas réel indépendant de `test-multi-branch`.
6. **Test manuel dédié (27/07, suite 4)** — run réel sur `cih-internship/testfinal2` (PROJECT_TYPE=backend, `AUDIT_AUTO_FIX=yes`) : `protected_branches`/`pipeline_success` confirmés verts après fix, `protected_tags` en échec (cause : branche principale en dur sur `main`, inexistante — branche réelle `master`). A permis de découvrir le faux positif sur `protected_branches` (règle créée avec succès sur une branche inexistante). Correctif de détection dynamique appliqué, revalidation CI en attente.

### Prochaine étape
1. 🔴 **Appliquer réellement le correctif Bug 3 sur `protected_branches.py`** (`get_effective_rules` / `project.default_branch`) — documenté comme fait le 27/07 suite 4, mais absent du code (cf. réconciliation 01/08). Tant qu'il manque, le faux positif est actif : une règle est créée sur un `main` inexistant pendant que la vraie branche principale reste sans protection.
2. **Relancer le pipeline complet en CI** avec `AUDIT_AUTO_FIX=yes` pour confirmer un run vert de bout en bout — vérifier en particulier le nouveau pattern `{artifactId}-*` (décision #15) sur un projet backend, et si le doute sur un éventuel délai de propagation de `default_branch` après le mirror push se confirme ou non.
3. **Vérifier le niveau d'accès réellement stocké** par GitLab après un `fix_protected_tags` réussi (`GET /projects/:id/protected_tags`) : si `access_level` vaut 40 alors que 60 est envoyé, la valeur de la décision #12 est à revoir (cf. réconciliation 01/08).
4. ~~**Recommiter `tests/`**~~ ✅ fait le 01/08 (84 tests : slug, réécriture de manifeste, pattern dérivé du contenu, cas fail-closed, renommage par projet dans le lot). Restent à écrire : les régressions `access_level` (décision #14) et branche principale dynamique (`default_branch="master"`), qui portent sur `protected_branches.py`.
5. Finaliser le nettoyage de `audit_tool/__init__.py` — `extract_project_name` y est désormais redondante avec `audit_tool/manifest.py` (01/08), et `scan_manifests`/`run_audit` restent du code mort sans appelant. `README.md` du pipeline mis à jour le 29/07 puis le 01/08.
6. Nettoyage optionnel : `GitLabAPIClient.create_protected_tag()` est orpheline depuis le 24/07 (plus appelée).
7. Clarifier le statut réel de Q2 (zéro/multi-match template) — toujours en suspens depuis le 24/07.
8. Décider si le repo de test `test-multi-branch` est conservé comme fixture de test permanente (avec topic dédié) ou supprimé après usage.
9. Axe 2 (Backstage) : plan en 5 phases proposé le 24/07 (voir section Axe 2) — prérequis : vérifier le contenu réel des 3 actions scaffolder déjà esquissées avant de démarrer la Phase 0.

---

## Axe 2 — Backstage

### Statut : planification, rien testé
- 3 actions scaffolder esquissées (TypeScript) : `detect-and-tag`, `apply-topic`, `trigger-audit`
- 2 templates `template.yaml` esquissés : backend (complet), frontend (preuve de généralisation)
- Fichiers existants : `setup-backstage.md`, snippet `app-config.yaml`, 2× `template.yaml`, `detect-and-tag.ts`, `apply-topic.ts`, `trigger-audit.ts`, `index.ts`

### Bloquants connus
- [ ] Dossiers `skeleton/` **vides** — copier le contenu réel des templates GitLab dedans
- [ ] Aucun test end-to-end — TypeScript jamais compilé
- [ ] `branches[].protected` dépend de la version du plugin utilisée
- [ ] Support natif des topics dans `publish:gitlab` version-dépendant → contournement API direct déjà choisi (à garder)

### ⚠️ Prérequis avant Phase 0
Vérifier le contenu réel des 3 actions scaffolder déjà esquissées (`detect-and-tag.ts`, `apply-topic.ts`, `trigger-audit.ts`). Si elles **réimplémentent** la logique métier en TypeScript au lieu d'appeler l'API GitLab pour déclencher le pipeline `governx-pipeline` existant, c'est le même problème de duplication qu'on vient de corriger côté `audit_tool` (deux implémentations de la même règle qui divergent silencieusement). Principe à respecter : Backstage **déclenche** le pipeline Axe 1 via API, il ne duplique pas `create_project`/`configure_tags`/`audit_check`.

### Plan en 5 phases (proposé le 24/07, non encore validé par l'encadrante)
Phase 0 = démo locale de validation uniquement (pas un déploiement CIH). **À valider en premier**, scope tout le reste.

| Phase | Objectif | Statut |
|---|---|---|
| 0 | Démo locale : une action scaffolder `trigger-governx-pipeline` (POST `/projects/:id/pipeline` avec `PROJECT_NAME`/`PROJECT_TYPE`/`GROUP_PATH`) + un `template.yaml` (backend) → pipeline déclenché, statut vert | ⬜ Non commencée |
| 1 | Généralisation multi-stack (ajout `frontend`), un seul `template.yaml` paramétré par `PROJECT_TYPE`, affichage du statut/logs du pipeline dans l'UI | ⬜ |
| 2 | Intégration Software Catalog : `catalog-info.yaml` généré et publié automatiquement après création, lien catalogue → projet GitLab → dernier pipeline | ⬜ |
| 3 | Durcissement : remontée claire des échecs pipeline (zéro/multi-match, non-conformité audit) dans l'UI Backstage, timeout/retry sur le polling | ⬜ |
| 4 | Rollout CIH : permissions Backstage, doc utilisateur interne, décision sur le maintien du formulaire "Run pipeline" manuel en fallback | ⬜ |

### Dépendance
Attend que l'Axe 1 soit stabilisé et testé end-to-end (les actions scaffolder appellent la même logique métier).

### Prochaine étape
Vérifier le contenu des 3 actions scaffolder existantes (prérequis ci-dessus), puis démarrer la Phase 0.

---

## Axe 3 — DevSecOps (Docker + Trivy)

### Statut : planification, rien exécuté
Inspiré d'un post LinkedIn (pipeline DevSecOps complet Terraform/Jenkins/ArgoCD/K8s) — volet retenu pour GovernX : containeriser `audit_tool` et scanner l'image.

### Livrables déjà produits
- `Dockerfile` — multi-stage, utilisateur non-root, entrypoint `python -m audit_tool.main`, aucun argument par défaut baké
- `.dockerignore` — exclut `.env`, `reports/`, caches
- `gitlab-ci-phase1-2-snippet.yml` — jobs `docker-build`, `security-scan` (Trivy), `docker-push` (Docker Hub)

### Bloquants connus
- [ ] Mécanisme `.trivyignore` non décidé — le premier run va probablement échouer sur des CVE OS non pertinentes (`python:3.11-slim`)
- [ ] Aucun run Trivy réel effectué
- [ ] Variables `DOCKERHUB_USER` / `DOCKERHUB_TOKEN` à créer en CI (masquées + protégées)
- [ ] Gestion de secrets (Vault/K8s Secrets/SSM) non traitée — limite connue, à assumer explicitement plutôt qu'ignorer

### Dépendance
Le `Dockerfile` empaquette `audit_tool` de l'Axe 1 → attend que l'Axe 1 (y compris `audit_tool`) soit stabilisé pour rester cohérent.

### Prochaine étape
Décider du mécanisme `.trivyignore`, puis premier run réel en sandbox.

---

## Comment articuler les 3 axes

- **Axe 1** = socle métier (logique de création de projet + tagging + audit)
- **Axe 2** = couche d'interface au-dessus de l'Axe 1 (self-service via Backstage au lieu du formulaire "Run pipeline")
- **Axe 3** = couche de packaging/sécurité autour de l'Axe 1 (containerisation + scan CVE de `audit_tool`)

Aucun des deux axes 2 et 3 ne duplique la logique métier de l'Axe 1 — ils la consomment. C'est pourquoi la stabilisation de l'Axe 1 (décisions + implémentation + test end-to-end) doit avancer avant de sérieusement avancer sur 2 et 3.

---

## Backlog global (priorisé)

1. ~~**Axe 1** — Priorité Maven vs npm~~ ✅ tranché 23/07, **supersédé 24/07** par le mapping déterministe (#10)
2. **Axe 1** — Clarifier le statut de Q2 (zéro/multi-match template) — rouverte 24/07, toujours en suspens 27/07
3. ~~**Axe 1** — Comportement audit en cas de non-conformité~~ ✅ tranché 23/07, confirmé inchangé 24/07, comportement fail-closed validé en CI réelle 27/07
4. ~~**Axe 1** — Résolution de `TEMPLATE_GROUP_PATH`~~ ✅ tranché 23/07, précisé 27/07 (groupe sur gitlab.com, cf. #13)
5. ~~**Axe 1** — Écrire les stages `create_project → configure_tags → audit_check`~~ ✅ fait + revu + corrigé 23/07, réécrits 24-27/07
6. ~~**Axe 1** — Réutiliser les vraies règles du `audit_tool` CIH (protected_branches/tags, pipeline_success)~~ ✅ fait 24/07, bug de modèle `access_level` trouvé et corrigé en CI réelle 27/07 (décision #14). ⚠️ Le correctif de branche principale en dur (amendement suite 4) est documenté comme fait mais **absent du code réel** — cf. réconciliation 01/08.
7. ~~**Axe 1** — Recommiter `tests/` dans le repo réel (absent depuis au moins le 24/07)~~ ✅ fait 01/08 (84 tests, décision #15) — restent à couvrir les régressions de `protected_branches.py`
8. 🔴 **Axe 1** — Appliquer réellement le correctif de branche principale dynamique sur `protected_branches.py` (`get_effective_rules`), jamais passé dans le code malgré l'amendement 27/07 suite 4
9. **Axe 1** — Retester le pipeline complet en CI avec `AUDIT_AUTO_FIX=yes` + tous les correctifs (décision #14 + amendement branche dynamique + pattern #15) pour confirmer un run vert de bout en bout
10. ~~**Axe 1** — Vérifier/confirmer l'architecture cross-instance (décision #13)~~ ✅ confirmée fonctionnelle en CI réelle 27/07
11. **Axe 1** — Trancher la valeur `create_access_level` des protected tags (60 envoyé vs 40 documenté par l'API GitLab pour cet endpoint) — cf. réconciliation 01/08
12. **Axe 1** — Finaliser le nettoyage de `audit_tool/__init__.py` (`extract_project_name` redondante avec `manifest.py` depuis le 01/08, `scan_manifests`/`run_audit` sans appelant)
13. **Axe 1** — Nettoyage optionnel : `GitLabAPIClient.create_protected_tag()` orpheline
14. **Axe 2** — Vérifier le contenu réel des 3 actions scaffolder (`detect-and-tag.ts`, `apply-topic.ts`, `trigger-audit.ts`) avant Phase 0 — risque de duplication de logique métier
15. **Axe 2** — Démarrer la Phase 0 (démo locale, trigger via API)
16. **Axe 2** — Remplir les `skeleton/`
17. **Axe 2** — Premier test end-to-end en sandbox
18. **Axe 3** — Mécanisme `.trivyignore`
19. **Axe 3** — Premier run Trivy réel

---

## Journal des changements

| Date | Changement |
|---|---|
| 23 juillet 2026 | Fusion des 3 fichiers `.md` disjoints en un seul doc vivant. Axe 1 passé en statut "à reconstruire from 0" (architecture conservée, code repart de zéro). |
| 23 juillet 2026 | Les 4 décisions bloquantes de l'Axe 1 sont tranchées (Maven/npm, multi-match template, comportement audit, `TEMPLATE_GROUP_PATH`). Axe 1 passe en statut "décisions tranchées — prêt pour implémentation". Note : révision de la règle "`PROJECT_TYPE` jamais utilisé pour le tagging" (devient tie-breaker en cas d'ambiguïté). |
| 23 juillet 2026 | Arborescence finalisée (`governx-pipeline/` avec `ci/`, `ci/lib/`, `audit_tool/`) et 3 décisions d'implémentation actées (tout en Python, garde-fou `workflow:rules` global, pas de `templates/` local). Code des 3 stages + `gitlab_api.py` généré via IDE. |
| 23 juillet 2026 | Revue de code : 3 bugs critiques corrigés (filtre topic incluant à tort les projets sans topic, tie-breaker `PROJECT_TYPE` ignoré au lieu d'appliqué, `PROJECT_TYPE` dropdown sans `value` par défaut) + robustesse (`get_project()` ajoutée). Tests unitaires ajoutés et passés. Décisions complémentaires actées : fallback audit/scan supprimé (échec explicite tant qu'`audit_tool` n'existe pas), `TEMPLATE_VARIANT` en correspondance stricte. Axe 1 passe en statut "code écrit et corrigé — bloqué sur `audit_tool`". `GITLAB_API_TOKEN` ajoutée à la liste des variables à créer. |
| 24 juillet 2026 | Q1 (priorité Maven/npm) **révisée en profondeur** : confirmé par l'encadrante que chaque `PROJECT_TYPE` mappe vers un seul stack/manifeste (pas d'ambiguïté possible). La décision #1 du 23/07 est supersédée — `resolve_final_type()` et son tie-breaker sont retirés de `configure_tags.py`. Nouveau mécanisme acté : **protected tags** sur le projet importé (pattern `{nom}-*` dérivé du manifeste, accès Maintainer, fallback sur le nom GitLab si manifeste absent/invalide avec logging explicite — pas d'exception avalée silencieusement). Extraction déléguée à une nouvelle fonction `audit_tool.extract_project_name`. Q2 (zéro/multi-match template) **rouverte**, statut incertain, raison non précisée — `create_project.py` non modifié en attendant clarification. Q3/Q4 confirmées inchangées. Note de synchronisation ajoutée suite à une divergence entre ce doc et une autre source sur l'état de Q2/Q3/Q4. |
| 24 juillet 2026 | Réconciliation avec l'état réel du repo (`arborescence_complete.md` fourni) : seuls 2 des 4 correctifs du 23/07 étaient réellement passés dans le vrai code. `TEMPLATE_VARIANT` (strict) et le fallback `audit_check.py` ré-appliqués sur l'état réel. `configure_tags.py` réécrit sur cette base : topics déterministes (`resolve_topics`) + résolution du nom/protected tag (`resolve_project_name`, délègue à `audit_tool.extract_project_name`). `create_project.py` refactoré (`select_template()` extraite, testable). Suite `pytest` créée (`tests/`, 15 tests, aucune dépendance réseau) et passée en local. Plan de test à 3 niveaux documenté (unitaire / intégration partielle sandbox / pipeline complet en CI). Axe 1 passe en statut "code réécrit + testé unitairement — pas encore repoussé dans le repo réel". |
| 24 juillet 2026 | Code réintégré dans le repo réel. Pipeline testé en CI réelle : `create_project` et `configure_tags` passent (confirmé par run réel), `audit_check` échoue comme prévu sur `audit_tool.run_audit` non implémenté (comportement voulu, pas un bug). `audit_tool.extract_project_name` implémentée (Maven/npm, gère namespace + dépendances imbriquées, 10 tests). `audit_tool.run_audit` implémentée en **placeholder minimal** (présence `README.md` + auto-fix réel) pour débloquer le pipeline — critères de conformité CIH réels toujours à définir, marqué explicitement comme non-final dans le code et la doc. 28 tests `pytest` au total. **Pipeline end-to-end confirmé vert (3 stages) en CI réelle sur `cih-internship/governx-pipeline`.** Axe 1 passe en statut 🟢. |
| 24 juillet 2026 | Un document décrivant un `audit_tool` CIH déjà construit et testé (projet séparé, `projet_audit_gitlab_cih.md`) a été fourni — révèle un décalage important avec l'interface stub inventée précédemment (`extract_project_name`/`run_audit`). Décision : réutiliser la logique/règles réelles (`protected_branches`, `protected_tags`, `pipeline_success`), appliquées au seul projet importé plutôt qu'à toute l'instance. Décision #11 (protected tags `{nom}-*`/Maintainer) **supersédée** par #12 (pattern générique `*`/`v*`, accès Admin). `configure_tags.py` simplifié (topics uniquement), `audit_check.py` entièrement réécrit (orchestration des 3 règles via `python-gitlab`, nouvelle dépendance). `specific_user_access` explicitement hors scope. 26 tests `pytest` écrits et validés en local (objets simulés, aucune dépendance réseau). Plan Backstage en 5 phases proposé pour l'Axe 2, avec avertissement sur le risque de duplication de logique métier si les 3 actions scaffolder existantes réimplémentent la logique au lieu d'appeler l'API. |
| 27 juillet 2026 | Nouvel envoi de `arborescence_complete.md` : réconciliation avec l'état réel du repo. Deux écarts trouvés — `audit_tool/__init__.py` était resté dans son ancienne version (ancienne interface stub, remplacement du 24/07 pas passé dans le repo réel, corrigé), `tests/` absent du repo réel (jamais commité). Découverte d'une architecture cross-instance dans `create_project.py` (templates sur gitlab.com via `TEMPLATE_GITLAB_URL`/`TEMPLATE_GITLAB_TOKEN`, création sur l'instance locale) jamais discutée dans cette conversation — documentée comme décision #13 (fait constaté, à confirmer). `README.md` du pipeline mis à jour (archi cross-instance, vraie structure `audit_tool`, variables à jour). Axe 1 repasse en 🟡 : le pipeline vert du 24/07 concernait l'ancienne version placeholder de `audit_check`, la version réécrite (règles réelles) n'a pas encore été retestée en CI. |
| 27 juillet 2026 (suite) | Recommit partiel du code (`ci/audit_check.py`, `ci/configure_tags.py`, `ci/requirements.txt`, `audit_tool/gitlab_client.py`, `audit_tool/rules/`) vers l'instance locale — `tests/` toujours non recommité. Run CI réel : échec `create_project` sur zéro-match `frontend` — cause trouvée (topics vides côté API sur `test-frontend`/`test-batch`/`test-dependecie`, `Save changes` jamais persisté), corrigé manuellement dans l'UI GitLab. Run suivant : `create_project`/`configure_tags` passent, `audit_check` échoue avec `AUDIT_AUTO_FIX=yes` — bug trouvé dans `protected_branches` (décision #14) : modèle `access_level` traité comme un ensemble de rôles au lieu d'un seuil unique, fixes déclarés réussis mais re-check toujours en échec sur `develop`/`release/*`. Corrigé (`BRANCH_RULES` en valeurs uniques, champs API `merge_access_level`/`push_access_level`). Régression `TypeError` introduite puis corrigée dans la foulée. Repo de test `test-template4274630/test-multi-branch` créé (5 branches) pour valider empiriquement le comportement du `mirror clone/push` : confirmé que branches et tags Git sont copiés automatiquement, mais que les réglages de protection (protected branches/tags) ne le sont jamais — c'est `audit_check` qui doit les configurer via API sur le projet nouvellement créé, indépendamment de l'état du template source. Run volontaire sans `AUDIT_AUTO_FIX` sur ce repo de test : comportement fail-closed confirmé conforme (tout bloque proprement, `protected_tags` échoue sur absence de manifeste — attendu vu le contenu du repo de test). **Reste à faire : relancer avec `AUDIT_AUTO_FIX=yes` + correctif décision #14 pour confirmer un run vert de bout en bout, recommiter `tests/`.** |
| 27 juillet 2026 (suite 2) | Run CI réel a révélé que le correctif du bug `TypeError` (décision #14) était incomplet : `sorted(merge_expected)` restait présent dans `fix_protected_branches` malgré le retrait de `sorted(push_expected)` lors du 1er passage. Corrigé intégralement (les deux `sorted()` retirés). Run de validation fail-closed sur un nouveau projet (`cih-internship/testaudit`, `AUDIT_AUTO_FIX=no`) confirmé conforme au comportement attendu (5/5 règles non-conformes détectées — 3× `protected_branches`, `protected_tags`, `pipeline_success` — pipeline bloqué proprement, rapport généré). Hypothèse erronée sur l'absence de `fix_protected_tags`/`fix_pipeline_success` levée après lecture du code réel de `protected_tags.py`/`pipeline_success.py` : ces fonctions existaient déjà et sont correctes, y compris `OWNER_ACCESS_LEVEL = 60` cohérent avec la décision #12 (aucune divergence à corriger à ce stade). **Reste à faire : relancer avec `AUDIT_AUTO_FIX=yes` pour confirmer un run vert de bout en bout avec le correctif complet, recommiter `tests/`.** |
| 27 juillet 2026 (suite 3) | Comparaison avec un document de référence externe (`RULES_protected_branches_and_tags.md`, vraie source `audit_tool` CIH). `protected_tags` : `OWNER_ACCESS_LEVEL` (60) renommé `ADMIN_ACCESS_LEVEL` (60) — valeur confirmée correcte par l'encadrante, mais correspond au rôle Admin (palier spécifique à l'endpoint `protected_tags`), pas Owner (=50) ni Maintainer (=40, valeur du doc de référence) — nom de constante trompeur, aucun changement de valeur/comportement. `protected_branches` : instance locale confirmée Free/CE, pas de logique premium (`allowed_to_push`/`allowed_to_merge` + PATCH) à ajouter ; structure des deux règles (`protected_branches.py`, `protected_tags.py`) alignée sur le doc de référence (`EXPECTED_RULES` en liste de dicts, sets à un seul élément, paramètre `tier` sur les fonctions `fix_*`, `tier="premium"` lève `NotImplementedError`). Fallback `default_branch or "main"` confirmé déjà présent dans `protected_tags.py`. |
| 27 juillet 2026 (suite 4) | Run CI réel sur `testfinal2` (backend, `AUDIT_AUTO_FIX=yes`) : `protected_branches`/`pipeline_success` confirmés verts après fix (validation décision #14 en conditions réelles). `protected_tags` en échec — cause : règle sur la branche principale en dur sur `"main"`, qui n'existe sur aucun template réel (`testfinal2` a `master` comme branche par défaut, pas de branche `main`). Découverte d'un faux positif lié : le fix `protected_branches` avait déclaré `main` conforme après avoir créé une règle de protection dessus, alors que `main` n'existe pas — GitLab accepte la création d'une règle sur un nom de branche inexistant, donc `master` (la vraie branche principale) restait sans aucune protection. `EXPECTED_RULES` de `protected_branches.py` restructuré : détection dynamique de la branche principale via `project.default_branch` (au lieu d'un nom en dur), `develop`/`release/*` restent statiques. Fallback `or "main"` retiré de `protected_tags.py` pour la même raison — échec explicite si `default_branch` vide/None plutôt qu'un nom deviné. Mémoire et `GovernX.md` mis à jour. **Reste à faire : relancer en CI pour confirmer un run vert de bout en bout (avec un doute non résolu sur un éventuel délai de propagation de `default_branch` juste après le mirror push), recommiter `tests/`, README.md et `audit_tool/__init__.py` en cours de nettoyage par Chouaib.** |
| 29 juillet 2026 | `audit_check` génère un **rapport HTML autonome** (`audit_tool/report_html.py`) à côté du JSON et du TXT, exposé via `artifacts:expose_as`. `PROJECT_NAME` accepte désormais **plusieurs noms** (virgule/point-virgule/retour à la ligne) : le template n'est cloné qu'une fois puis poussé vers chaque destination, et création/tagging/audit tournent en parallèle (`MAX_PARALLEL_PROJECTS`, nouveau `ci/lib/projects.py`, `NEW_PROJECT_PATHS` en dotenv). L'échec d'un projet n'interrompt plus le lot — `GitLabAPIError` remplace les `sys.exit()` du client REST pour permettre cette isolation. Tokens masqués dans la sortie de git. Pipeline accéléré : suppression de l'`apt-get install git` de chaque job (image `python:3.11`), cache pip, clone superficiel ; `.gitlab-ci.yml` dédupliqué (son contenu y était présent deux fois). ⚠️ Schéma de `audit_report.json` modifié : `results`/`fixes` passent sous une liste `projects`. |
| 1er août 2026 | **Décision #15** — le pattern de protected tag passe de "générique par type de manifeste" (`*`/`v*`, #12/#14) à "dérivé du contenu du manifeste" (`{artifactId}-*`), reprenant l'idée nom-de-projet de #11 (supersédée) sans son niveau Maintainer ni son repli. Nouveau `audit_tool/manifest.py` : slug kebab-case, localisation fail-closed du manifeste dans toute l'arborescence, réécriture textuelle ciblée avec suivi de profondeur puis relecture structurelle de contrôle (un `artifactId` de `<parent>`/`<dependency>`, un `"name"` imbriqué ou un `artifactId` en commentaire ne peuvent pas être touchés). `create_project` renomme `<artifactId>`/`"name"` sur un slug de `PROJECT_NAME` et commite via l'API (`POST /repository/commits` — 3 nouvelles méthodes sur le client REST), **par projet** dans le lot. `protected_tags.py` réécrit : `detect_tag_pattern` relit le manifeste à chaque check **et** chaque fix plutôt que de réutiliser le slug de l'étape 1, les deux stages étant des jobs CI distincts. Fail-closed sur manifeste absent/multiple, stacks concurrents, champ absent/illisible, `default_branch` vide. `create_access_level = 60` inchangé. **`tests/` enfin recréé** (84 tests, absent depuis le 24/07) avec `ci/requirements-dev.txt`. **Réconciliation 01/08** : les correctifs du 27/07 suite 4 (`get_effective_rules`, retrait du fallback `"main"`, renommage `ADMIN_ACCESS_LEVEL`) sont documentés comme faits mais **absents du code réel** — `protected_branches.py` protège toujours un `main` en dur, le faux positif du Bug 3 est donc toujours actif ; non corrigé ici car hors périmètre. Écart "Maintainers" sur les protected tags tranché : règle **créée manuellement** (le fix n'a abouti dans aucun run documenté), avec un problème latent distinct signalé sur la validité même de la valeur 60 pour cet endpoint. |
