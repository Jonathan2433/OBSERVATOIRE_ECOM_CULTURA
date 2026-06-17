# Observatoire Ecom Studio — application (V1)

Application conteneurisée de classification et de pilotage des verbatims clients
Cultura. Réutilise le moteur ML du POC (`../src`). Voir
[../docs/CAHIER_DES_CHARGES.md](../docs/CAHIER_DES_CHARGES.md) et
[../docs/PLAN_DEVELOPPEMENT_V1.md](../docs/PLAN_DEVELOPPEMENT_V1.md).

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
version se fera dans l'UI admin (lot L7).

## État d'avancement
Voir [../docs/SUIVI_LOTS.md](../docs/SUIVI_LOTS.md). Lot courant : **L0 — socle & conteneurisation**.

## Validation sans daemon
```bash
docker compose config -q          # syntaxe compose
find app -name '*.py' | xargs python3 -m py_compile   # syntaxe Python
```
