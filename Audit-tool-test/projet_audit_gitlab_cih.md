# Projet de stage — Outil d'audit de conformité GitLab (CIH Bank)

## Contexte

- **Étudiant** : Chouaib, 3ème année Génie Informatique & Réseaux, EMSI Casablanca
- **Stage** : DevOps chez CIH Bank
- **Objectif du sujet initial** : scanner tous les repos d'une instance GitLab CE self-hosted (hors un groupe exclu) et vérifier les règles de conformité définies par le maître de stage
- **Stack de base** : Python 3 + `python-gitlab`, `gl.projects.list(iterator=True)` avec filtrage par préfixe de path (approche flat list)
- **Environnement local** : GitLab CE sur Docker (WSL2/Ubuntu), runner enregistré et fonctionnel, `.gitlab-ci.yml` de base déjà testé
- **Deadline réelle** : résultat à montrer au maître de stage sous **1 semaine**
- **Niveau Python de l'étudiant** : débutant complet (aucune expérience préalable) — apprentissage au fil de l'eau, concept par concept, directement sur le code du projet

## Scope confirmé — Couche 1 (livrable officiel, priorité absolue)

### Les 4 règles de conformité

1. **Branches protégées** (règle générique)
2. **Branches `release/*` (règle spécifique)** :
   - Allowed to merge : rôles **Developer + Maintainer**
   - Allowed to push : rôle **Maintainer** uniquement
3. **Tags protégés** avec détection dynamique des patterns de version (`pom.xml` / `package.json`)
4. **Condition "Pipeline must succeed"** sur les merge requests
5. **Accès utilisateur spécifique** (`specific_user_access`) — règle à part, **facultative** :
   - Paramètre : un `user_id`/nom, fourni une seule fois pour toute l'exécution du script (s'applique à tous les projets audités)
   - Si le paramètre n'est pas fourni → règle ignorée
   - Si fourni :
     - Si l'utilisateur n'est pas membre du projet → l'**ajouter** avec le rôle **Developer**
     - Si l'utilisateur est déjà membre avec un rôle insuffisant → **ajuster** son rôle à Developer minimum
   - **Seule règle qui écrit dans GitLab** (les 4 autres restent en lecture seule / audit)
   - Chaque action (ajout/ajustement) doit apparaître dans le rapport final
   - ⚠️ **Description historique, en partie obsolète** — conservée telle quelle comme trace de la V1. L'auto-add a été supprimé et la règle est devenue tier-aware (`free`/`premium`) avec un comportement radicalement différent selon la license GitLab. Voir la section **« Refonte `specific_user_access` — tier-aware »** plus bas pour le comportement actuel.
   - **Mise à jour** : `--user-id` accepte désormais soit un **ID numérique**, soit un **username** GitLab (résolution automatique via `resolve_user_id()` dans `gitlab_client.py`)

### Formats de sortie

- **CSV**
- **JSON**
- **HTML**

### Portée

- Tous les projets de l'instance GitLab, à l'exception d'un groupe exclu (filtrage par path-prefix)

### Authentification

- Token GitLab avec scope **`api`** (lecture + écriture) — nécessaire à cause de la règle `specific_user_access` qui modifie les accès
- ⚠️ Point de vigilance pour la prod CIH (pas bloquant maintenant) : le compte de service utilisé en prod devra avoir les droits Maintainer/Owner sur les projets concernés, pas seulement un token avec le bon scope

## Structure du projet (validée)

```
audit_tool/
├── __init__.py
├── gitlab_client.py           # connexion + liste des projets + exclusion du groupe + résolution user_id
├── rules/
│   ├── __init__.py
│   ├── protected_branches.py  # règle générique + logique release/* (check_* uniquement)
│   ├── protected_tags.py
│   ├── pipeline_success.py
│   └── specific_user_access.py # facultatif, ajoute/ajuste un membre
├── fixes.py                    # Couche 1.5 — les 3 fix_*, avec logique free/premium selon --tier
├── report.py                   # génère CSV + JSON + HTML
└── main.py                     # orchestre tout, flags --fix/--dry-run/--tier
```

- Pas d'OOP (classes) pour l'instant — fonctions simples, suffisant pour 4-5 règles fixes
- Pas de config externe (YAML) pour l'instant — constantes en dur / `.env`, à migrer plus tard si besoin
- **Paramètres d'exécution (décision mise à jour)** : `--url`, `--token` et `--user-id` sont passés en **arguments CLI** (via `argparse`), et non plus via `.env` — choix fait pour rendre la démo plus explicite devant le maître de stage
  - `--url` et `--token` : obligatoires
  - `--user-id` : optionnel (`type=str`, `default=None`), accepte ID numérique **ou** username, active la règle `specific_user_access` si fourni et résolu avec succès
  - ⚠️ Point de vigilance noté : passer le token en CLI le rend visible dans l'historique du shell et `ps aux` (contrairement à `.env`) — acceptable pour les tests locaux, à revoir si le script tourne un jour sur un serveur partagé
  - Seul `EXCLUDED_GROUP_PATH` reste dans `.env` (pas un paramètre par exécution, reste une constante de configuration)
- `.gitignore` prévu pour exclure `.env`, `__pycache__/`, fichiers de sortie générés

### Convention de format des résultats d'audit (décidée)

Toutes les fonctions `check_*` retournent un ou plusieurs dicts avec au minimum les clés communes suivantes, pour que `report.py` puisse traiter tous les résultats avec une seule boucle générique, sans cas particulier par règle :

```python
{
    "rule": "...",       # nom de la règle (ex: "protected_branches")
    "project": "...",    # project.path_with_namespace
    "compliant": True/False,
    "details": "...",    # message explicatif si non conforme, "OK" sinon
    # + clés optionnelles spécifiques à la règle (ex: "branch", "pattern", "project_type")
}
```

- `check_protected_branches` → retourne une **liste** de dicts (un par branche : `main`, `develop`, `release/*`)
- `check_protected_tags` → retourne **un seul** dict
- `check_pipeline_success` → retourne **un seul** dict
- `check_specific_user_access` → un seul dict par projet

Toutes les fonctions `fix_*` (stubs Couche 1.5) prennent `(project, result)` en paramètres, pour rester cohérentes entre les règles.

**⚠️ Bug corrigé (test end-to-end)** : `check_protected_branches` et `check_protected_tags` ne respectaient initialement pas cette convention (clés `branch`/`reason` au lieu de `rule`/`project`/`details`), causant un `KeyError: 'rule'` dans `main.py` lors de l'affichage console. Corrigé — les deux fonctions incluent désormais `rule`, `project` et `details` dans chaque dict retourné, en plus de leurs clés spécifiques (`branch`, `pattern`, `project_type`).

### Orchestration (`main.py`) — pattern `all_results`

`main.py` boucle sur tous les projets filtrés, appelle les 4 (bientôt 5) fonctions `check_*`, et accumule tout dans une liste plate `all_results` (via `.extend()` pour les listes, `.append()` pour les dicts uniques). Cette liste est ensuite transmise telle quelle à `report.py`.

```
gitlab_client.py  →  liste de projets + résolution user_id (ID ou username)
        ↓
rules/*.py        →  check_*(project) → dict ou liste de dicts
        ↓
main.py           →  boucle + accumule tout dans all_results
        ↓
report.py         →  all_results → CSV / JSON / HTML
```

## Questions en attente de réponse du maître de stage

*(Déjà répondues pour la plupart — gardé comme trace)*

- ✅ Audit only ou action réelle pour `specific_user_access` → **action réelle** (ajout/ajustement de membre)
- ✅ Ajout au projet si absent → **oui**
- ✅ Rôle minimum pour merge sur `release/*` → **Developer**
- ✅ Portée de l'action → **tous les projets audités**
- ✅ Fréquence du paramètre user_id → **une fois pour toute l'exécution**
- ✅ Paramètre facultatif à chaque exécution → **oui**
- ✅ Apparition dans le rapport → **oui**
- ❓ Droits du token en prod CIH → non tranché, à valider avec l'équipe infra le moment venu (pas bloquant pour le développement local)

## Vision long-terme (Couches 1.5-7 — mise en pause, à reprendre après livraison du script)

*Cette section reste la proposition d'enrichissement personnel/portfolio définie précédemment. Non prioritaire tant que la Couche 1 n'est pas livrée.*

### Pourquoi ce sujet est pertinent pour un profil Cloud/DevOps/Solutions Architect

- Vrai use case de gouvernance/conformité, pas un projet jouet — particulièrement pertinent dans une banque (exigences type ISO 27001, PCI-DSS)
- Croise API scripting, CI/CD, et Infra as Code — exactement le profil transversal recherché
- Debug réel d'un environnement self-hosted (networking WSL2/Docker, GitLab `external_url`, runner) — plus formateur qu'un environnement cloud managé "qui marche par magie"
- Point de vigilance : projet très on-prem au départ — à compenser avec une couche cloud public pour un profil qui vise aussi le cloud managé

### Architecture enrichie — 8 couches

| Couche | Concepts couverts | Détail |
|---|---|---|
| **1. Core tool (audit)** | — | Script Python + python-gitlab (livrable officiel, détaillé ci-dessus) — lecture seule sauf `specific_user_access` |
| **1.5. Fix des règles de conformité** ✅ **TERMINÉ** | Python, gestion d'erreurs, idempotence, contraintes de license API | Implémentée dans `audit_tool/fixes.py`, centralisant les 3 fonctions `fix_*`. Détails complets dans la section dédiée ci-dessous. |
| **2. Containerization** | Docker, Linux | Image Docker multi-stage, push vers un registry (GitLab Container Registry en local, ECR/ACR si cloud réel) |
| **3. Orchestration** | Kubernetes, Docker, Troubleshooting | Déploiement en CronJob Kubernetes (`kind` en local), ConfigMaps/Secrets pour le token GitLab, resource limits. Casser volontairement des configs pour pratiquer le debug |
| **4. Infra as code** | Terraform, VM, Networking, IAM, Storage, AWS/Azure | Terraform provisionne VPC/subnets, rôles IAM least-privilege, bucket S3/Blob pour les rapports, VM ou cluster managé |
| **5. CI/CD** | GitLab CI, GitHub Actions | GitLab CI pour build/test/deploy, mirror GitHub avec workflow Actions en parallèle — bon exercice comparatif |
| **6. Observability & security** | Monitoring, Security, HA, Cost optimization | Prometheus/Grafana, scan d'image (Trivy), network policies K8s, dashboard avec replicas + load balancer pour la HA, autoscaling (HPA) |
| **7. Stretch goal (optionnel)** | ML pipelines, GPU | Modèle scikit-learn (CPU suffit) prédisant les repos à risque de dérive de conformité à partir de l'historique des audits. Le GPU n'est **pas** un besoin naturel ici — à faire comme mini-exercice séparé si vraiment voulu (VM GPU free tier + `nvidia-smi`) |

### Couche 1.5 — Fix automatique des non-conformités (terminée)

**Prérequis à l'origine** : Couche 1 stable et validée par le maître de stage avant d'activer les fixs. Décision prise en cours de route : **avancer en parallèle** sans attendre la validation formelle, la Couche 1.5 ayant été développée et testée avant le retour officiel du maître de stage.

#### Architecture retenue

- Toutes les fonctions `fix_*` centralisées dans **`audit_tool/fixes.py`** (un seul fichier, plutôt qu'un `fix_*` par fichier de règle) — décision explicite pour garder une vue d'ensemble de toute la remédiation en un seul endroit
- Signature commune : `fix_*(project, result, dry_run=False, tier="free")`
- Convention de retour, en miroir de celle des `check_*` :
  ```python
  {
      "rule": "...",
      "project": "...",
      "action": "...",       # description de ce qui a été fait / serait fait
      "dry_run": True/False,
      "success": True/False,
      "details": "...",      # "OK" ou message d'erreur
  }
  ```
- Deux nouveaux flags CLI dans `main.py` :
  - `--fix` : active la remédiation (sans lui, comportement audit-only inchangé)
  - `--dry-run` : simule les corrections sans écrire dans GitLab (nécessite `--fix`)
- Dans `run_audit()`, après chaque `check_*` non conforme, le `fix_*` correspondant est appelé si `--fix` est actif ; les résultats de fix sont accumulés dans `all_results` au même titre que les checks (visibles dans les rapports CSV/JSON/HTML)
- Affichage console différencié : ✅/❌ pour les résultats de `check_*` (clé `compliant`), 🔧/⚠️ pour les résultats de `fix_*` (clé `success`)

#### Découverte majeure en cours de route : limite de license GitLab CE vs Premium/Ultimate

En testant `fix_protected_branches` avec une vraie modification `PATCH` en place (approche initialement choisie), le fix retournait `200 OK` mais **ne modifiait rien réellement** sur GitLab (vérifié dans l'UI). Investigation dans la doc officielle de l'API :

- Le endpoint `PATCH /projects/:id/protected_branches/:name` n'accepte les champs `allowed_to_push`/`allowed_to_merge` (les seuls qui permettent de changer les niveaux d'accès) que sur **GitLab Premium et Ultimate** — explicitement marqué ainsi dans la doc GitLab
- Sur GitLab **CE** (l'instance locale utilisée pour développer), ces champs sont silencieusement ignorés par le serveur, d'où le faux succès
- Le endpoint `PATCH` ne supporte **aucun** champ simple équivalent (`push_access_level`/`merge_access_level` au singulier) — ces champs n'existent que sur `POST` (création), pas sur `PATCH` (mise à jour)
- **Conséquence** : sur GitLab CE, il n'existe **aucun moyen supporté de modifier en place** les niveaux d'accès d'une branche déjà protégée. La seule option viable est **unprotect puis reprotect** (`DELETE` puis `POST`)
- Pour les **protected tags**, l'API n'a **jamais eu de endpoint `PATCH`**, quelle que soit la license (Free, Premium, ou Ultimate) — seulement `GET`/`POST`/`DELETE`. Donc `fix_protected_tags` utilise systématiquement delete+create, peu importe le tier.

**Correction de conception associée** : `EXPECTED_RULES` dans `protected_branches.py` définissait initialement `merge` comme un set à deux valeurs (`{DEVELOPER, MAINTAINER}`) pour représenter "Developers + Maintainers peuvent merger". Or la doc GitLab confirme qu'un rôle donné dans une protected branch **inclut déjà tous les rôles supérieurs** (sélectionner Developer donne accès à Developer, Maintainer, et Owner) — donc "Developers + Maintainers" se représente par **une seule entrée** `access_level=30`, pas deux. `EXPECTED_RULES` corrigé pour n'avoir qu'une seule valeur par champ (`push`/`merge`), cohérent avec ce que l'API renvoie réellement :
```python
EXPECTED_RULES = [
    {"pattern": "main", "push": {MAINTAINER}, "merge": {MAINTAINER}},
    {"pattern": "develop", "push": {MAINTAINER}, "merge": {DEVELOPER}},
    {"pattern": "release/*", "push": {MAINTAINER}, "merge": {DEVELOPER}},
]
```

#### Décision : deux implémentations selon la license GitLab (`--tier`)

Le maître de stage dispose d'une license GitLab **Entreprise (Premium/Ultimate)**, contrairement à l'instance de développement locale (CE gratuite). Plutôt que de se limiter à la stratégie CE, `fixes.py` implémente les deux stratégies et choisit dynamiquement via un paramètre `tier` (`"free"` par défaut, ou `"premium"`) :

- **`tier="free"`** (`_fix_protected_branches_free` en interne) : unprotect + reprotect avec `push_access_level`/`merge_access_level` (champs simples, compatibles CE)
- **`tier="premium"`** (`_fix_protected_branches_premium` en interne) : vrai `PATCH` avec diff des entrées existantes par `id` (récupère les `id` internes des `push_access_levels`/`merge_access_levels` actuels, construit un payload avec `_destroy: true` pour les entrées en trop et de nouvelles entrées pour celles qui manquent) — utilisable uniquement sur une instance Premium/Ultimate
- `fix_protected_tags` et `fix_pipeline_success` sont **identiques dans les deux tiers** (pas de PATCH disponible pour les tags peu importe la license ; `pipeline_success` est un simple attribut booléen non concerné par cette limite)
- Nouveau flag CLI `--tier free|premium` (défaut `free`) — Chouaib n'a rien à changer dans ses commandes habituelles ; le maître de stage ajoutera `--tier premium` pour tester sur son instance Entreprise

#### Bug de récursion infinie corrigé dans `main.py`

En intégrant l'appel à `generate_report()`, une ligne dupliquée `results = run_audit(args.url, args.token, args.user_id)` s'était retrouvée collée **à l'intérieur** de la définition de `run_audit()` elle-même (au lieu du bloc `if __name__ == "__main__":`), causant un appel récursif infini (`RecursionError` après ~900 appels empilés). Corrigé — un seul appel à `run_audit()`, correctement placé dans le bloc principal.

#### Tests de validation effectués

- ✅ Dry-run (`--fix --dry-run`, `tier=free`) : payloads corrects affichés pour les 3 branches (`main`, `develop`, `release/*`), aucune écriture réelle confirmée dans l'UI GitLab
- ✅ Exécution réelle (`--fix`, `tier=free`) : les 3 branches recréées avec les bons niveaux d'accès, confirmé visuellement dans **Settings → Repository → Protected branches** (`main` = Maintainers, `develop`/`release/*` = Developers + Maintainers, push = Maintainers partout)
- ✅ Re-audit après fix (sans `--fix`) : les 3 règles de branches passent à `✅` (cas positif validé, en plus du cas négatif déjà testé)
- ⏳ Mode `tier=premium` — code écrit et cohérent avec la doc API, mais pas encore testé sur une vraie instance Premium/Ultimate (à faire avec le maître de stage)

### Point de vigilance : sécurité des données bancaires

CIH Bank a des données de gouvernance interne (repos, règles de conformité) potentiellement sensibles. Avant de proposer une intégration AWS/Azure au maître de stage :

- **Ne jamais connecter l'audit réel aux vraies données bancaires vers un cloud public** sans validation sécurité/conformité (Loi 09-08 au Maroc notamment)
- **Séparer deux environnements** dans la proposition :
  1. L'audit réel reste 100% interne (GitLab CE + infra CIH, rien ne change)
  2. Une démo cloud-native tourne sur un compte AWS/Azure personnel, avec un GitLab de test et des données factices — pour prouver que l'architecture (Terraform, K8s, monitoring, CI/CD) fonctionne
- Argument à présenter : *"j'ai prototypé une version cloud-native sur un environnement de démo, voici comment on pourrait l'adapter en interne si ça vous intéresse"*

### Décisions prises (vision long-terme)

- **Accès cloud** : compte AWS/Azure free tier réel (pas de simulation locale uniquement)
- **Cadre du projet** : à proposer comme V2 officielle au maître de stage (avec la séparation démo/prod ci-dessus)
- **Point de départ recommandé** : Terraform + fondations AWS (plutôt que Docker/K8s, déjà en partie maîtrisés)

### Plan de démarrage — Semaines 1-2 : fondations AWS avec Terraform

- **IAM** : créer un user/role dédié avec permissions minimales (jamais utiliser le root account)
- **Networking** : VPC, subnet public/privé, security group
- **Storage** : bucket S3 pour les rapports d'audit
- **VM** : instance EC2 free tier (`t2.micro`) pour héberger le runner ou un test GitLab

#### ⚠️ Piège à coût identifié

Le control plane EKS (Kubernetes managé AWS) **n'est pas couvert par le free tier** (~$0.10/h en continu même sans charge). Recommandation : garder Kubernetes en local (`kind`) sur la VM EC2 plutôt que de payer un vrai cluster EKS — même apprentissage K8s, sans le coût surprise.

### Prochaines étapes possibles (après livraison de la Couche 1)

- [ ] Rédiger un draft de proposition (1 page) pour le maître de stage, avec le découpage réel/démo
- [ ] Provisionner les fondations Terraform (IAM, VPC, S3, EC2)
- [ ] Déployer `kind` sur l'EC2 et migrer le CronJob de l'audit dessus
- [ ] Mettre en place le mirror GitHub + workflow GitHub Actions en parallèle de GitLab CI
- [ ] Ajouter Prometheus/Grafana pour le monitoring des runs d'audit

## État d'avancement actuel (Couche 1)

- ✅ Architecture et structure de fichiers validées
- ✅ Scope des 5 règles clarifié avec le maître de stage
- ✅ Formats de sortie confirmés (CSV, JSON, HTML)
- ✅ `gitlab_client.py` terminé — `get_gitlab_connection()` et `get_filtered_projects(gl)` fonctionnels (401 initial résolu)
- ✅ `gitlab_client.py` enrichi — `resolve_user_id(gl, user_identifier)` ajouté : accepte ID numérique ou username, retourne toujours un ID numérique (ou `None` avec avertissement console si introuvable)
- ✅ `rules/protected_branches.py` — `check_protected_branches()` + stub `fix_protected_branches()` écrits, **corrigés pour respecter la convention `rule`/`project`/`details`**
- ✅ `rules/protected_tags.py` — détection dynamique du pattern de version (`pom.xml`/`package.json`), `check_protected_tags()` + stub `fix_protected_tags()` écrits, **corrigés pour respecter la convention `rule`/`project`/`details`**
- ✅ `rules/pipeline_success.py` — `check_pipeline_success()` + stub `fix_pipeline_success()` écrits (respectait déjà la convention)
- ✅ Convention de format des résultats d'audit alignée sur les 4 règles read-only (`rule`, `project`, `compliant`, `details`)
- ✅ Pattern d'orchestration `all_results` défini pour `main.py`
- ✅ `rules/specific_user_access.py` — `check_specific_user_access(project, user_id)` écrit (seule règle qui écrit dans GitLab : ajout en Developer si absent, ajustement du rôle si insuffisant, via `gitlab.const.DEVELOPER_ACCESS`) ; gère les erreurs GitLab (ex. `404 User Not Found`) sans faire planter le script ; stub `fix_specific_user_access()` volontairement vide (le check agit déjà directement en V1)
- ✅ `main.py` — orchestration réécrite avec `argparse` (`--url`, `--token` obligatoires, `--user-id` optionnel en `str`), `run_audit()` isolée dans une fonction, boucle projets + 4 règles → `all_results`, affichage console avec ✅/❌
- ✅ `main.py` — appel à `resolve_user_id()` ajouté dans `run_audit()` avant la boucle projets, pour convertir username → ID une seule fois par exécution
- ✅ **Test end-to-end réussi contre l'instance GitLab réelle** (`172.20.109.143:8929`) sur le repo `cih-internship/my_project` :
  - Les 4 règles read-only tournent sans crash et retournent des résultats cohérents et correctement formatés
  - Résultats obtenus sur ce repo de test (non conforme sur tous les points, comportement attendu) :
    - `protected_branches` : `main` protégée mais merge trop permissif (Developer trouvé, Maintainer attendu) ; `develop` et `release/*` non protégées du tout
    - `protected_tags` : aucun `pom.xml`/`package.json` détecté → non conforme par construction
    - `pipeline_must_succeed` : option désactivée
  - `specific_user_access` testé avec un username inexistant (`test1`) → `resolve_user_id` a correctement averti que l'utilisateur était introuvable, mais un `404 User Not Found` est quand même remonté par l'appel GitLab — **à vérifier** : la condition `if resolved_user_id:` dans `run_audit()` devrait empêcher l'appel à `check_specific_user_access` si la résolution échoue ; le contenu actuel de `run_audit()` n'a pas encore été revérifié après l'ajout de `resolve_user_id()`
- ✅ **Bug corrigé** : `run_audit()` testait `if specific_user_id:` (l'entrée brute) au lieu de `if resolved_user_id is not None:` (l'ID résolu), et passait `specific_user_id` au lieu de `resolved_user_id` à `check_specific_user_access()`. Causait un appel API inutile (`404 User Not Found`) même quand la résolution avait échoué. **Corrigé** — la condition et l'argument passé utilisent désormais `resolved_user_id`.
- ✅ **Test end-to-end de `specific_user_access` réussi avec un utilisateur réel** (`test1`, créé pour le test) : cas "ajout" validé — `✅ [specific_user_access] ... Utilisateur ajouté au projet avec le rôle Developer`.
- ✅ **Cas "ajustement de rôle" validé** : rôle de `test1` rétrogradé manuellement à Guest (10) sur `my_project` via l'UI GitLab, puis re-run du script → `✅ [specific_user_access] cih-internship/my_project — Rôle ajusté de 10 à Developer (30)`. Les deux comportements de la règle (ajout + ajustement) sont désormais confirmés end-to-end.
- ✅ `report.py` écrit et fonctionnel — trois fonctions `generate_csv_report()`, `generate_json_report()`, `generate_html_report()`, orchestrées par `generate_report()`. `try/except OSError` autour de chaque écriture fichier, `csv.DictWriter` avec colonnes dynamiques (union de toutes les clés présentes dans `all_results`, pour gérer les clés spécifiques à certaines règles comme `branch`/`pattern`/`project_type`), rapport HTML avec mise en forme ✅/❌ par ligne.
- ✅ **Organisation des rapports en dossiers horodatés** : chaque exécution de `generate_report()` crée automatiquement `reports/<YYYY-MM-DD_HH-MM-SS>/` (via `os.makedirs(..., exist_ok=True)`) et y place les 3 fichiers (`audit_report.csv/json/html`). Évite l'écrasement des rapports précédents et conserve un historique des runs.
- ✅ `.gitignore` mis à jour pour inclure `reports/` en plus de `.env`, `__pycache__/`, `*.pyc`
- ✅ **Bugs de connexion GitLab rencontrés et résolus pendant les tests** (à titre de référence) :
  - `502 GitLab is not responding` — conteneur Docker GitLab pas encore complètement démarré (démarrage lent typique de GitLab CE) ou arrêté ; vérifier avec `docker ps` côté WSL2
  - `403 Forbidden` sur `check_protected_branches` — le compte propriétaire du token n'avait pas le rôle Maintainer sur le projet testé (l'API `protectedbranches.list()` l'exige) ; résolu en vérifiant/ajustant le rôle dans **Members** du projet
  - ⚠️ **Point de vigilance sécurité** : un token GitLab (`glpat-...`) a été collé en clair dans une conversation pendant le débogage — **à révoquer et régénérer** si ce n'est pas déjà fait, ne jamais partager de token en clair même pour un environnement de test
- ⏳ Test de `specific_user_access` — cas "ajustement de rôle" avec le maître de stage, pas encore fait

### Tests `protected_tags` — en cours

**Repos de test importés depuis GitHub** (via `git clone --bare` + `git push --mirror`) pour disposer de vrais projets Maven/npm sans devoir écrire des fichiers minimaux à la main :
- `cih-internship/test-maven` (source : `pdurbin/maven-hello-world`) — `pom.xml` situé dans un sous-dossier `my-app/`, pas à la racine du repo
- `cih-internship/test-npm` (source : `IBM/node-hello-world`) — `package.json` à la racine

**⚠️ Bug détecté et corrigé — `detect_version_pattern` ne cherchait qu'à la racine du repo.**

La fonction utilisait `project.files.get(file_path="pom.xml", ref=default_branch)`, qui ne vérifie que la racine exacte. Résultat : `pom.xml` non détecté sur `test-maven` (fichier réel dans `my-app/pom.xml`) ni sur `simple-springboot-app`, alors que ces fichiers existent bel et bien dans les repos — confirmé visuellement dans l'UI GitLab et via `project.repository_tree(recursive=True)` en debug.

**Décision** : la détection doit chercher le fichier **n'importe où dans l'arborescence du repo**, pas seulement à la racine, pour refléter la réalité de vrais projets CIH à structure variable. `detect_version_pattern` réécrite pour utiliser `project.repository_tree(ref=default_branch, recursive=True, get_all=True)` et chercher `pom.xml`/`package.json` par nom de fichier dans l'ensemble des blobs retournés, plutôt que deux appels `files.get()` ciblés sur la racine.

```python
def detect_version_pattern(project):
    default_branch = project.default_branch or "main"
    try:
        tree = project.repository_tree(ref=default_branch, recursive=True, get_all=True)
    except Exception as e:
        return None, None

    filenames = {item["path"].split("/")[-1] for item in tree if item["type"] == "blob"}

    if "pom.xml" in filenames:
        return "*", "maven"
    if "package.json" in filenames:
        return "v*", "npm"
    return None, None
```

- Priorité Maven > npm conservée (si un repo contient les deux fichiers, `pom.xml` l'emporte) — comportement à revalider si un vrai cas CIH avec les deux fichiers se présente
- `get_all=True` nécessaire pour éviter la pagination par défaut de `python-gitlab` (20 résultats) sur les repos avec beaucoup de fichiers
- **Piège de debug rencontré** : après la correction du code, les anciens logs (`404 File Not Found` via `files.get()`) continuaient d'apparaître malgré la modification visible dans VS Code. Cause : OneDrive (dossier projet synchronisé, fichier marqué comme reparse point / "Files On-Demand") a empêché la sauvegarde de prendre effet correctement dans le fichier réellement lu par Python. Résolu en écrivant le fichier directement via PowerShell (`Set-Content`) après fermeture de l'onglet dans VS Code, contournant le comportement incohérent de l'éditeur avec OneDrive. **Point de vigilance à garder en tête pour la suite du projet** : en cas de comportement "le code ne semble pas s'appliquer" malgré une modification visible, vérifier en premier `python -c "import module; print(module.__file__)"` et `inspect.getsource(...)` pour confirmer ce que Python charge réellement, avant de suspecter la logique elle-même.

**Résultats de test après correction** :
- ✅ `test-npm` : `package.json` détecté à la racine → `pattern='v*'`, non conforme (attendu, aucun protected tag encore créé)
- ✅ `test-maven` : `pom.xml` détecté dans `my-app/` → `pattern='*'`, non conforme (attendu, aucun protected tag encore créé)
- ✅ `simple-springboot-app` : `pom.xml` détecté correctement → `pattern='*'`, non conforme (attendu)
- ✅ `my_project` : toujours "aucun fichier trouvé" — cohérent, ce repo n'a ni `pom.xml` ni `package.json`

**Prochaine étape immédiate** : créer manuellement un protected tag conforme (pattern `*`, "Allowed to create" = Owner uniquement) sur `test-maven` pour valider le cas `compliant: True`, puis tester `fix_protected_tags` (`--fix --dry-run` d'abord, puis exécution réelle).

## Gaps corrigés (session du 14/07/2026)

Les deux gaps flaggés en fin de session précédente sont désormais résolus :

- ✅ **Gestion des exceptions `403`/erreurs API GitLab dans la boucle d'audit** — auparavant, une exception non gérée (ex. `403` sur `check_protected_branches` faute de rôle Maintainer) faisait planter tout `run_audit()`, empêchant l'audit des projets suivants. Corrigé dans `main.py` : chaque appel `check_*` est maintenant entouré d'un `try/except gitlab.exceptions.GitlabError` individuel (pas un seul `try` autour de toute la boucle projet), via un helper `_gitlab_error_result(rule, project, error)` qui construit un dict conforme à la convention `rule`/`project`/`compliant`/`details` (`compliant: False`, `details` contenant le code et le message d'erreur GitLab). `except Exception` volontairement évité pour ne pas masquer de vrais bugs de code. Testé en rétrogradant temporairement le rôle du token sur un projet (→ `403` bien capturé, reporté dans les résultats, script continue sur les projets suivants).
- ✅ **Mismatch de clés dans le rapport HTML** (`generate_html_report` construit correctement les lignes pour les résultats de `fix_*`, qui utilisent `success`/`action` au lieu de `compliant`/`details`) — résolu.
- ✅ **Bug d'indentation dans `main.py`** repéré au passage : le bloc d'affichage console final (`print(f"\n=== {len(results)} résultats...")` + boucle `for r in results`) était par erreur en dehors du `if __name__ == "__main__":`, ce qui aurait provoqué un `NameError` si `main.py` était un jour importé plutôt qu'exécuté directement. Corrigé — bloc réintégré proprement dans `if __name__ == "__main__":`.

## Session du 20/07/2026 — Débogage pipeline CI/CD + validation `--fix` en conditions réelles

Contexte : reset complet du dépôt Git local (`~/my_project` sous WSL2) et re-push depuis 0 vers l'instance GitLab CE, suivi d'un débogage complet de la pipeline CI/CD jusqu'à obtention d'un run vert avec `--fix` réel.

### Bugs rencontrés et corrigés (ordre chronologique)

1. **`pyproject.toml` absent du dépôt** — `pip install .` échouait avec `Neither 'setup.py' nor 'pyproject.toml' found`. Cause : le fichier existait uniquement sur le chemin Windows/OneDrive (`C:\Users\arxbo\OneDrive\Bureau\Audit-script\`), jamais copié/committé dans le clone WSL2 séparé (`~/my_project`) utilisé pour les push. Récupéré via `find` sur le filesystem, copié, commité.
2. **Détour Git : commit perdu en detached HEAD** — le commit du fix `pyproject.toml` a été fait en detached HEAD, puis un `git rebase --abort` a réinitialisé `main` avant ce commit (commit orphelin). Récupéré via `git reflog` (repérage du hash `7a2c846`) + `git cherry-pick`, puis push réussi.
3. **`EXCLUDED_GROUP_PATH` non défini en CI** — `TypeError: unsupported operand type(s) for +: 'NoneType' and 'str'` dans `get_filtered_projects()`. Cause : cette variable n'existait que dans le `.env` local (gitignored), jamais définie comme variable CI/CD GitLab. **Corrigé** : ajoutée dans **Settings → CI/CD → Variables** du projet.
4. **Erreur de syntaxe CLI dans `.gitlab-ci.yml`** — `"$GITLAB_AUDIT_USER_ID"--fix` (espace manquant) faisait fusionner les deux arguments, argparse interprétait `--fix` comme faisant partie de la valeur de `--user-id`. Corrigé en ajoutant l'espace manquant.
5. **Token GitLab avec retour à la ligne parasite** — `ValueError: Invalid header value b'glpat-[MASKED]\n'` lors de `gl.auth()`. Cause : la variable CI/CD `GITLAB_AUDIT_TOKEN` contenait un `\n` final (probablement collé depuis une source avec saut de ligne automatique). Corrigé en resupprimant/re-collant proprement la valeur dans **Settings → CI/CD → Variables**.

### Résultat final — pipeline validée de bout en bout

Après correction des 5 points ci-dessus, run complet réussi avec `--fix` réel (pas seulement `--dry-run`) :
- `pip install .` → installation propre du package `audit-gitlab-cih` et de ses dépendances
- Audit des 4 projets (`test-npm`, `test-maven`, `simple-springboot-app`, `my_project`) → 21 résultats collectés (20 checks + 1 fix)
- Seule non-conformité restante : `protected_tags` sur `my_project` (pas de `pom.xml`/`package.json` → pattern de version indétectable). Comportement attendu et correct : `fix_protected_tags` refuse proprement l'action (`⚠️ aucune action — Impossible de corriger : aucun pattern de version détecté`) plutôt que de deviner ou planter — validation que la gestion des cas limites fonctionne comme prévu.
- Tous les autres checks (branches protégées, tags, pipeline success) déjà conformes sur les 4 projets, aucune régression introduite par le `--fix` réel
- Rapports CSV/JSON/HTML générés et uploadés comme artifacts de pipeline avec succès
- Test `specific_user_access` avec un `GITLAB_AUDIT_USER_ID` réel effectué séparément (validé, détail non re-décrit ici)

**Pipeline CI/CD end-to-end désormais fonctionnelle** : install → audit → fix réel → rapports → artifacts, testée en conditions réelles contre l'instance GitLab CE de développement.

## Session du 29/07/2026 — Refonte `specific_user_access` — tier-aware

### Point de départ : erreur de conception identifiée

L'implémentation précédente de `check_specific_user_access` faisait `tier="premium" → ne rien faire, compliant=True, "GitLab gère nativement"`. Cette formulation confondait deux mécanismes GitLab distincts :

- **L'appartenance à un projet** (`project.members.create()` / `member.access_level`) — API disponible sur **toutes** les licenses, y compris CE. Rien à voir avec Premium.
- **L'octroi d'accès push/merge à un utilisateur nommé sur une branche protégée**, indépendamment de son rôle projet — **ça**, c'est bien Premium/Ultimate-only (visible dans l'UI GitLab sous forme d'entrées « 1 rôle, 1 utilisateur » dans les colonnes *Allowed to merge* / *Allowed to push and merge* de Repository settings → Protected branches).

Conséquence concrète du bug : le court-circuit `tier="premium"` ne vérifiait strictement rien et renvoyait toujours `compliant: True`, y compris si l'utilisateur n'avait en réalité aucun accès. Un faux positif silencieux.

**Clarification du rôle de la règle** : `specific_user_access` existe comme **contournement CE** — élever le rôle projet d'un utilisateur est le seul levier disponible en Free/CE pour lui donner un accès push/merge sur une branche protégée, faute de pouvoir cibler un utilisateur individuellement. Sur Premium, ce contournement n'est plus nécessaire : on peut accorder l'accès directement au niveau de la branche, sans toucher au rôle projet.

### Décisions de conception prises (dans l'ordre)

1. **Portée des branches (Premium)** : passée en **paramètre appelant** (`branches`), plutôt que dérivée automatiquement de `EXPECTED_RULES` ou limitée à `main` — le script n'impose aucune hypothèse sur quelles branches doivent recevoir l'accès utilisateur spécifique.
2. **Forme de retour** : `check_specific_user_access` renvoie désormais **toujours une liste** (jamais un dict seul), pour éviter une branche conditionnelle dans `main.py` selon le tier. CE : un dict par utilisateur (`branch: None`). Premium : un dict par couple *(utilisateur, branche)*.
3. **Multi-utilisateurs** : `user_id` devient `user_ids` (liste), sur les deux tiers — CE boucle un ajustement de rôle par utilisateur, Premium regroupe tous les utilisateurs d'une même branche dans **un seul PATCH** (moins d'appels API).
4. **Type d'accès par branche (push / merge / both)** : après une première itération avec un flag global `--access-type` (un seul type pour tout l'appel), decision finale : **le type d'accès se choisit par branche**, pas globalement — `branches` devient un **dict** `{nom_branche: access_type}` plutôt qu'une simple liste de noms. Le type d'accès reste en revanche **uniforme entre tous les utilisateurs** sur une même branche (pas de type différent par utilisateur — jugé inutilement complexe pour le besoin actuel).

### Mécanique API retenue (Premium)

- Lecture de l'état actuel via `project.protectedbranches.get(branch_name)`, inspection des `push_access_levels`/`merge_access_levels` pour repérer les entrées `user_id` déjà présentes.
- Écriture via **`PATCH` additif** : seuls les utilisateurs manquants sont envoyés dans `allowed_to_push`/`allowed_to_merge`. Contrairement à `_fix_protected_branches_premium` (Couche 1.5, diff complet avec `_destroy: true` sur les entrées à retirer), ici on n'envoie **jamais** de `_destroy` — les entrées de rôle existantes sur la branche ne doivent pas être touchées, seul un ajout est souhaité.
- Si une branche n'est pas protégée du tout, tous les utilisateurs visés par cette branche sont reportés `compliant: False` avec un message explicite plutôt que de tenter une protection à la volée (hors scope de cette règle).

### Signature finale

```python
def check_specific_user_access(project, user_ids, tier="free", branches=None):
    """
    user_ids : liste d'IDs GitLab résolus (int)
    branches : dict {branch_name: access_type} — access_type dans {"push", "merge", "both"}
               Utilisé uniquement si tier="premium". Ignoré si tier="free".
               Exemple : {"main": "both", "develop": "merge", "release/*": "push"}
    """
```

`fix_specific_user_access` reste un stub vide (`pass`) — cohérent avec la Couche 1, cette règle écrit directement dans `check_*`, pas de séparation check/fix pour elle.

### Changements requis dans `main.py` (à reporter chez Chouaib — fichier non dans le contexte de la session)

- `--user-id` : le help text doit préciser qu'il accepte désormais une liste séparée par des virgules (`alice,bob`), résolue via un nouveau `resolve_user_ids()` dans `gitlab_client.py` (pluriel, boucle sur `resolve_user_id()` existant, log un avertissement par utilisateur introuvable sans faire échouer les autres).
- Nouveau flag `--user-branches`, format `"branch:access_type,branch:access_type"` (ex. `"main:both,develop:merge,release/*:push"`), parsé par une nouvelle fonction `parse_user_branches()` en dict.
- Site d'appel : `.append(result)` → `.extend(results)`, car la fonction renvoie toujours une liste maintenant.
- Nouveau champ `branch` dans les dicts retournés par cette règle (déjà `None` pour les autres règles read-only) — `report.py` devrait l'absorber automatiquement via l'union de clés déjà en place pour le CSV, **à revérifier visuellement** sur un run réel (colonne `branch` vide sur les lignes CE, remplie sur les lignes Premium).

### Exemples d'invocation (comportement cible)

```bash
# Free/CE — élévation de rôle pour deux utilisateurs, sur tous les projets audités
python main.py --url ... --token ... --user-id alice,bob --tier free

# Premium — accès différencié par branche, mêmes utilisateurs
python main.py --url ... --token ... \
  --user-id alice,bob \
  --tier premium \
  --user-branches "main:both,develop:merge,release/*:push"
```

### État

- ✅ Conception validée (portée branches en paramètre, retour toujours liste, multi-utilisateurs, type d'accès par branche)
- ✅ `rules/specific_user_access.py` réécrit (code final ci-dessus, en attente de collage dans le projet réel)
- ⏳ `gitlab_client.py` (`resolve_user_ids`) et `main.py` (flags, parsing, site d'appel) — modifications spécifiées mais pas encore appliquées, fichiers non fournis dans cette session
- ⏳ Retest end-to-end à refaire (CE d'abord, Premium ensuite avec le maître de stage — toujours conditionné à l'accès à son instance Entreprise)
- ⏳ Vérification visuelle de `report.py` (nouvelle colonne `branch`) — pas encore faite

## Prochaines étapes immédiates

- [x] Test de bout en bout complet de la pipeline CI/CD (Couche 1 + Couche 1.5, `--fix` réel, artifacts) — ✅ fait le 20/07/2026
- [ ] Dérouler la checklist de test complète à 11 catégories (mentionnée en fin de session précédente — détail à reconstituer/retrouver)
- [ ] Nettoyer les prints de debug restants dans `gitlab_client.py` (affichage URL/token chargés, hérités du diagnostic du 401 initial)
- [ ] Vérifier que les tokens utilisés pendant les tests ont bien été révoqués/régénérés après avoir été partagés en clair à plusieurs reprises (dont un nouveau partage en clair lors de la session du 14/07/2026)
- [ ] Présenter la Couche 1.5 au maître de stage pour validation formelle (développée en parallèle, sans attendre le go officiel sur la Couche 1)
- [ ] Envisager d'harmoniser l'invocation CI (`cd audit_tool && python main.py`) avec le pattern documenté `python -m audit_tool.main` depuis la racine, pour éviter que la pipeline exécute silencieusement la copie installée via `pip install .` (site-packages) plutôt que le code source local — actuellement sans impact car les deux sont synchronisés à chaque run, mais source de confusion potentielle si un futur changement de code n'est pas reflété en CI
- [ ] Appliquer la refonte `specific_user_access` dans le projet réel : coller le nouveau `rules/specific_user_access.py`, ajouter `resolve_user_ids()` dans `gitlab_client.py`, ajouter `--user-branches`/`parse_user_branches()` et adapter le site d'appel dans `main.py`
- [ ] Revérifier `report.py` (CSV/HTML) avec la nouvelle colonne `branch` sur un run réel

### Reporté

- [ ] Tester `--tier premium` sur l'instance GitLab Entreprise du maître de stage (mode `--fix` **et** la règle `specific_user_access` premium, en dry-run d'abord) — reporté à une session ultérieure avec le maître de stage
