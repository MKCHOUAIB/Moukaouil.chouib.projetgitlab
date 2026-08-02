# GovernX — Pipeline GitLab CI (Axe 1)

Ce dépôt contient le socle métier du pipeline GitLab CI pour l'automatisation de la création, du tagging et de l'audit des projets GitLab.

Une exécution du pipeline crée **un ou plusieurs projets** depuis le même template, dans le même groupe cible.

## Structure du projet

```text
governx-pipeline/
├── .gitlab-ci.yml              # Pipeline GitLab CI (3 stages, déclenchement manuel web)
├── README.md                   # Documentation du projet
├── ci/
│   ├── __init__.py
│   ├── requirements.txt        # Dépendances Python (requests, python-gitlab)
│   ├── requirements-dev.txt    # pytest
│   ├── create_project.py       # Stage 1 : template + mirror clone/push + renommage du manifeste
│   ├── configure_tags.py       # Stage 2 : Application des topics sur chaque projet
│   ├── audit_check.py          # Stage 3 : Audit + rapports (JSON/TXT/HTML) + contrôle conformité
│   └── lib/
│       ├── __init__.py
│       ├── gitlab_api.py       # Wrapper API REST GitLab v4 (arborescence, fichiers, commits)
│       └── projects.py         # Lecture de la liste des projets entre stages
├── audit_tool/
│   ├── manifest.py             # Slug, localisation et réécriture du champ identifiant du manifeste
│   ├── gitlab_client.py        # Connexion python-gitlab
│   ├── report_html.py          # Rendu HTML autonome du rapport d'audit
│   └── rules/                  # Règles d'audit (branches protégées, tags protégés, pipeline)
└── tests/                      # Suite pytest, sans dépendance réseau
```

## Variables CI/CD

### Variables de déclenchement (Formulaire "Run pipeline")

- `PROJECT_NAME` *(obligatoire)* : Nom du/des projet(s) à créer. **Plusieurs noms** peuvent être fournis, séparés par des virgules, des points-virgules ou des retours à la ligne — ex. `api-clients, api-contrats, Batch Nuit`. Tous sont créés depuis le même template, dans le même groupe.
- `PROJECT_TYPE` *(obligatoire)* : Type de projet (`backend` | `frontend` | `batch` | `dependencie`). Sert de topic pour la résolution du template.
- `GROUP_PATH` *(obligatoire)* : Chemin du groupe cible GitLab dans lequel créer le(s) projet(s).
- `TEMPLATE_VARIANT` *(optionnel)* : Nom ou identifiant de la variante pour désambiguïser en cas de multi-match.
- `MAX_PARALLEL_PROJECTS` *(optionnel, défaut: `4`)* : Nombre de projets traités simultanément (création, tagging, audit).
- `AUDIT_AUTO_FIX` *(optionnel, défaut: `no`)* : Active la correction automatique lors de l'audit (`yes`/`no`).
- `AUDIT_ACCEPT_NONCOMPLIANT` *(optionnel, défaut: `no`)* : Accepte un projet non-conforme sans bloquer le pipeline (`yes`/`no`).

### Variables de groupe GitLab (Infra / Secrètes)

- `TEMPLATE_GROUP_PATH` *(obligatoire)* : Chemin du groupe racine contenant tous les projets templates.
- `TEMPLATE_GITLAB_TOKEN` *(obligatoire)* : Token de lecture sur l'instance des templates (gitlab.com).
- `TEMPLATE_GITLAB_URL` *(optionnel, défaut: `https://gitlab.com`)* : Instance hébergeant les templates.
- `GITLAB_API_TOKEN` *(obligatoire)* : Token d'API GitLab de l'instance locale (droits API et push Git).
- `AUDIT_TIER` *(optionnel, défaut: `free`)* : `free` ou `premium`, sélectionne la stratégie de correction des branches protégées.
- `GITLAB_API_TIMEOUT` *(optionnel, défaut: `30`)* : Timeout en secondes des appels API.

## Comportement multi-projets

- Le template n'est **cloné qu'une seule fois** par exécution, puis poussé (`git push --mirror`) vers chaque nouveau projet.
- Création, tagging et audit sont exécutés **en parallèle** (`MAX_PARALLEL_PROJECTS`).
- Un échec sur un projet **n'interrompt pas** le traitement des autres : le lot est traité en entier, puis le stage sort en erreur en listant ce qui a échoué.
- Deux noms produisant le même slug (ex. `Mon Projet` et `mon-projet`) sont refusés **avant** toute création.

## Identité du projet et protected tags

Juste après le mirror push, le stage `create_project` aligne le champ identifiant du manifeste sur un slug kebab-case de `PROJECT_NAME` — `<artifactId>` racine du `pom.xml` (backend/batch/dependencie) ou `"name"` racine du `package.json` (frontend). « Simple SpringBoot App » donne `simple-springboot-app`. Le manifeste est cherché dans **toute** l'arborescence (pas seulement à la racine) et le changement est commité via l'API GitLab sur la branche par défaut réelle du projet.

`audit_check` en dérive ensuite le pattern de protected tag attendu : **`{artifactId}-*`** (ex. `simple-springboot-app-*`), en `create_access_level = 60` (Admin). La valeur est **relue depuis le manifeste** à chaque vérification et à chaque correction — jamais reprise du slug calculé au stage 1, les deux stages étant des jobs CI distincts.

Tout est **fail-closed** : aucun manifeste, plusieurs manifestes candidats (projet Maven multi-modules), deux stacks concurrents, champ identifiant absent ou illisible, ou branche par défaut indéterminée → erreur explicite, aucune valeur devinée.

## Tests

```bash
pip install -r ci/requirements.txt -r ci/requirements-dev.txt
python -m pytest tests/ -q
```

Aucune dépendance réseau ni instance GitLab : les règles sont testées contre des objets simulés.

### Variables transmises entre stages (artifact dotenv)

- `NEW_PROJECT_PATHS` : chemins complets des projets créés, séparés par des virgules. Source de vérité des stages 2 et 3.
- `NEW_PROJECT_COUNT` : nombre de projets créés.
- `NEW_PROJECT_PATH` / `NEW_PROJECT_HTTP_URL` : première entrée de la liste, conservées pour compatibilité mono-projet.

## Artifacts

| Fichier | Stage | Contenu |
| --- | --- | --- |
| `reports/created_projects.json` | create_project | Projets créés et échecs éventuels |
| `reports/audit_report.json` | audit_check | Rapport d'audit complet, exploitable par un outil tiers |
| `reports/audit_report.txt` | audit_check | Même rapport en texte brut |
| `reports/audit_report.html` | audit_check | Rapport consultable dans le navigateur (page autonome, exposée via *Rapport d'audit GovernX* sur la page du pipeline) |

Le rapport d'audit couvre tous les projets du lot : une vue d'ensemble puis une section par projet (vérifications et correctifs).
