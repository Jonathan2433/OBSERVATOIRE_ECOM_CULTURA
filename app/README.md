# Observatoire Ecom Studio — application (V1)

Application conteneurisée de classification et de pilotage des verbatims clients
Cultura. Réutilise le moteur ML du POC (`../src`).

**Documentation** :
[Cahier des charges](../docs/CAHIER_DES_CHARGES.md) ·
[Plan de développement](../docs/PLAN_DEVELOPPEMENT_V1.md) ·
[Suivi des lots](../docs/SUIVI_LOTS.md) ·
[Guide utilisateur](../docs/GUIDE_UTILISATEUR.md) ·
[Exploitation](../docs/EXPLOITATION.md) ·
[Recette V1](../docs/RECETTE_V1.md)

## Services (docker-compose)
| Service | Rôle | Exposition |
|---|---|---|
| `web` | nginx : sert le front React + proxy `/api` | **127.0.0.1:8080** uniquement |
| `api` | FastAPI (auth, orchestration, KPI) | interne |
| `worker` | RQ : exécute le pipeline ML (CamemBERT) | interne |
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
**lecture seule** dans le worker (`/data/models`). La sélection/activation de
version se fait dans l'UI admin (menu *Modèles*) — voir [Exploitation §4](../docs/EXPLOITATION.md).

## État d'avancement
Voir [../docs/SUIVI_LOTS.md](../docs/SUIVI_LOTS.md). **V1 complète (L0→L8)** : lots L0→L7 validés ; **L8 (durcissement, RGPD, perf, recette + doc)** en attente de validation PO. Recette automatisée : `python app/tests/recette_v1.py` → 48/48.

## Dépannage

| Symptôme | Cause | Solution |
|---|---|---|
| `password authentication failed for user "oes"` + `Skipping initialization`, l'`api` redémarre en boucle | `POSTGRES_PASSWORD` du `.env` ne correspond plus à celui gravé dans le volume `pgdata` lors du **premier** démarrage (Postgres ne ré-applique pas le mot de passe sur un volume existant). Survient typiquement après un `cp .env.example .env` qui réécrit le mot de passe. | Réinitialiser le volume : `docker compose down -v && docker compose up --build`. **Attention** : `-v` efface la base (comptes, lots, résultats). |
| L'`api` redémarre quelques fois au lancement puis se stabilise | la base n'était pas encore prête | normal (les healthchecks gèrent l'attente) |

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
.venv_validate/bin/python app/tests/recette_v1.py     # -> 48/48 OK
```
Détail de la couverture (garde-fous §10 + DoD §11) : [../docs/RECETTE_V1.md](../docs/RECETTE_V1.md).
