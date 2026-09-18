# Observatoire Ecom Studio — application

Application conteneurisée de classification et de pilotage des verbatims clients
Cultura. Réutilise le moteur ML du POC (`../src`).

**Documentation** :
[Cahier des charges](../docs/CAHIER_DES_CHARGES.md) ·
[Plan de développement](../docs/PLAN_DEVELOPPEMENT_V1.md) ·
[Suivi des lots](../docs/SUIVI_LOTS.md) ·
[Guide utilisateur](../docs/GUIDE_UTILISATEUR.md) ·
[Exploitation](../docs/EXPLOITATION.md) ·
[Recette V1](../docs/RECETTE_V1.md) ·
[Passation](../docs/PASSATION.md) ·
[Couche de décision](../docs/COUCHE_DECISION.md) ·
[Migration satisfaction répondant](../docs/MIGRATION_SATISFACTION_REPONDANT.md)

## Services (docker-compose)
| Service | Rôle | Exposition |
|---|---|---|
| `web` | nginx : sert le front React + proxy `/api` | **127.0.0.1:8080** uniquement |
| `api` | FastAPI (auth, orchestration, KPI) | interne |
| `worker` | RQ : exécute le pipeline ML (CamemBERT, LM Studio, Claude, stub) | interne |
| `db` | PostgreSQL (local) | interne |
| `redis` | file de jobs | interne |

> Seul `web` est publié, et uniquement sur localhost. Aucune donnée ne sort du poste.

## Lancement (sur le poste, Docker Desktop démarré)
```bash
cd cultura-verbatim-classifier
cp .env.example .env          # puis éditer POSTGRES_PASSWORD et SECRET_KEY
# générer une clé : python -c "import secrets; print(secrets.token_urlsafe(48))"
docker compose up --build
```
Puis ouvrir **http://localhost:8080** : la page d'accueil affiche l'état de l'API,
de la base et de Redis.

## Modèles
Déposer les artefacts entraînés (CLI) dans `data/models/` : ils sont montés en
**lecture seule** dans le worker **et dans l'api** (`/data/models`). La
sélection/activation de version se fait dans l'UI admin (menu *Modèles*) — voir
[Exploitation §4](../docs/EXPLOITATION.md).

**Plusieurs modèles CamemBERT coexistent.** Chacun est décrit par un profil
(`config/config.yaml → moteurs_camembert`) portant son référentiel, ses seuils et
sa couche de décision. Un modèle doit **embarquer son référentiel** à sa racine
(`<racine>/taxonomy.json`) : c'est lui que l'API sert aux listes de la revue
humaine, et la seule forme qui suive le modèle dans les conteneurs.

Activer un moteur n'en supprime aucun ; le retour arrière est une resélection.

## Restitution métier

La satisfaction est agrégée dans `survey_responses` à raison d'une voix par
répondant, en conservant l'échelle native de chaque source. Le tableau de bord
affiche les quatre sources attendues, y compris une source non reçue, et distingue
`Ancien`, `Nouveau` et `Statut client non disponible` pour MDTC. Le classement des
sous-thèmes porte uniquement sur les champs textuels ouverts ; les questions
fermées n'y sont pas intégrées implicitement.

Dans les graphiques **thème × sentiment**, l'ordre d'affichage sert directement
la priorisation métier : volume négatif décroissant, puis volume total
décroissant et libellé alphabétique en cas d'égalité. Le tri s'applique au jeu de
données affiché et compte le thème principal comme le second thème.

## État d'avancement
Voir [../docs/SUIVI_LOTS.md](../docs/SUIVI_LOTS.md). **V1→V5 livrées**, V6 (revue et
exports consolidés) incluse. Modèle **Cultura 2026** recetté et mis à disposition dans
le sélecteur ; bascule du modèle par défaut non effectuée (décision humaine).

Recettes automatisées :

| Applicatives (torch-free) | Modèle (environnement ML) |
|---|---|
| `recette_v1.py` → 89 OK · `recette_v3.py` → 13 OK | `recette_l1a_chargeur.py` → dépend de spaCy et des fichiers réels |
| `recette_v4.py` → 50 OK · `recette_v5.py` → 112 OK | `recette_l2_protocole.py` → 15 OK |
| `recette_v6.py` → 26 OK · `test_satisfaction_respondents.py` → 10 OK | `recette_couche_decision.py` → 46 OK |

## Dépannage

| Symptôme | Cause | Solution |
|---|---|---|
| `password authentication failed for user "oes"` + `Skipping initialization`, l'`api` redémarre en boucle | `POSTGRES_PASSWORD` du `.env` ne correspond plus à celui gravé dans le volume `pgdata` lors du **premier** démarrage (Postgres ne ré-applique pas le mot de passe sur un volume existant). Survient typiquement après un `cp .env.example .env` qui réécrit le mot de passe. | Réinitialiser le volume : `docker compose down -v && docker compose up --build`. **Attention** : `-v` efface la base (comptes, lots, résultats). |
| L'`api` redémarre quelques fois au lancement puis se stabilise | la base n'était pas encore prête | normal (les healthchecks gèrent l'attente) |
| `http://localhost:8080` ne répond pas alors que les conteneurs sont « Up » | Docker n'a pas rétabli la publication de port ni le réseau après un redémarrage : le conteneur `web` tourne **sans réseau attaché**. Vérifier avec `docker inspect observatoire-ecom-studio-web-1 --format '{{json .NetworkSettings.Networks}}'` — un objet vide confirme | `docker compose up -d` (recrée les conteneurs concernés). Les données ne sont pas affectées |
| Un moteur CamemBERT n'apparaît pas dans le sélecteur | Profil absent de `moteurs_camembert`, racine hors de `data/models`, ou sous-modèle manquant | Le journal du worker au démarrage dit lequel est ignoré et pourquoi |

> ⚠️ **Important** : une fois en production avec des données, **ne changez pas** `POSTGRES_PASSWORD` sans procédure (sinon `down -v` détruirait les données). Fixez-le une fois pour toutes dans `.env`.

## Validation sans daemon
```bash
docker compose config -q          # syntaxe compose
find app -name '*.py' | xargs python3 -m py_compile   # syntaxe Python
```

## Recette V1 (hors ligne, sans Docker)
```bash
python3 -m venv .venv_validate && .venv_validate/bin/python -m pip install --upgrade pip
.venv_validate/bin/python -m pip install --prefer-binary fastapi httpx sqlalchemy \
  "pydantic>=2" pydantic-settings argon2-cffi PyJWT python-multipart pandas numpy openpyxl pyyaml redis rq
.venv_validate/bin/python app/tests/recette_v1.py     # -> 89 OK · 0 ÉCHEC
```
Détail de la couverture (garde-fous §10 + DoD §11) : [../docs/RECETTE_V1.md](../docs/RECETTE_V1.md).
