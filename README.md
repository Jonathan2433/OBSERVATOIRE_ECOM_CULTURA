# Observatoire Ecom Studio — Cultura Verbatim Classifier

Application interne de **classification et de pilotage des verbatims clients** de
cultura.com. Pour chaque verbatim (sources **MDTC** et **Mopinion**, ~11 000/mois),
le moteur produit : une **classification thématique hiérarchique** (niv.1 + niv.2,
contrainte par un référentiel), un **sentiment**, trois **signaux** (rupture client,
churn, insatisfaction forte), un **score de confiance** et un **routage vers la revue
humaine**. Le tout **100 % local, hors-ligne, sans GPU**.

> 🔒 **Confidentialité by design** : anonymisation des PII **avant** tout traitement,
> base **sans donnée brute**, exposition **localhost uniquement**, aucune sortie réseau.

---

## 1. Sommaire

- [2. Architecture](#2-architecture)
- [3. Pile technique](#3-pile-technique)
- [4. Structure du dépôt](#4-structure-du-dépôt)
- [5. Démarrage rapide (Docker)](#5-démarrage-rapide-docker)
- [6. Le moteur ML (entraînement)](#6-le-moteur-ml-entraînement)
- [7. Données & RGPD](#7-données--rgpd)
- [8. Sécurité](#8-sécurité)
- [9. Transmission / sauvegarde](#9-transmission--sauvegarde)
- [10. Tests & recettes](#10-tests--recettes)
- [11. Documentation](#11-documentation)
- [12. Versions](#12-versions)

---

## 2. Architecture

Mono-poste, conteneurisé (Docker Desktop, `linux/arm64`). Seul le service `web` est
exposé, **uniquement sur `127.0.0.1`**.

```
 navigateur (localhost:8080)
        │
        ▼
 [web] nginx ── sert le front React + proxy /api ──┐
        │                                          ▼
        │                                   [api] FastAPI (sans torch)
        │                                     │      │
        │                          enqueue RQ │      └──▶ [db] PostgreSQL
        │                                     ▼
        │                            [redis] ◀── [worker] RQ + moteur ML (src/)
        │                                              │  CamemBERT / ONNX int8
        ▼                                              ▼
   build React (Vite)                  volumes : models (RO) · uploads · output
                          Aucun trafic réseau sortant (offline strict)
```

- **`web`** : nginx, sert le build React et proxifie `/api` (en-têtes de sécurité, CSP).
- **`api`** : FastAPI/uvicorn — auth, RBAC, orchestration des lots, KPI, admin. **Sans torch** (démarrage léger).
- **`worker`** : RQ — exécute le pipeline ML lourd (réutilise le moteur `src/` du POC).
- **`db`** : PostgreSQL (utilisateurs, lots, **résultats anonymisés**, corrections, audit, config).
- **`redis`** : file de jobs.
- Package partagé **`app/common`** (engine SQLAlchemy + modèles ORM) importé par `api` **et** `worker` → schéma unique, pas de duplication.
- Tant qu'aucun modèle CamemBERT n'est déposé, un **classifieur stub** (heuristique, sans torch) rend l'app démontrable de bout en bout.

## 3. Pile technique

| Couche | Technologies |
|---|---|
| Front | React 18 + TypeScript + Vite ; **design system maison** (tokens CSS, 0 dépendance UI) |
| API | FastAPI, uvicorn, SQLAlchemy 2, Alembic, argon2, JWT (cookie httpOnly) |
| Worker / ML | RQ + Redis ; **CamemBERT** (HuggingFace Transformers), **ONNX Runtime int8** (optimum), scikit-learn (signaux), spaCy (NER d'anonymisation) |
| Données | PostgreSQL 16, openpyxl (Excel) |
| Infra | Docker Compose (5 services), nginx, offline strict |

## 4. Structure du dépôt

```
cultura-verbatim-classifier/
├── src/                    # Moteur ML du POC (réutilisé par le worker)
│   ├── preprocessing/      # loader Excel, nettoyage, anonymisation (PII)
│   ├── modeling/           # architecture, export ONNX int8
│   ├── training/           # prepare_dataset, train_{classifier,sentiment,signals}
│   ├── inference/          # predictor (build_output = logique de décision pure)
│   └── utils/              # config, taxonomie (hiérarchie contrainte)
├── app/
│   ├── api/                # service FastAPI (routes, core, migrations Alembic)
│   ├── worker/             # service RQ (tâches, registre de modèles, classifieurs)
│   ├── common/             # package partagé : DB + modèles ORM + rétention
│   ├── web/                # front React/TS (ui/ design system, pages, styles)
│   └── tests/              # recettes V1 / V3 (torch-free, SQLite)
├── scripts/                # setup_models, run_training, validate_pipeline,
│                           # make_demo_data, package_app, restore_app
├── config/config.yaml      # hyperparamètres, seuils, mapping colonnes (source unique)
├── data/                   # raw (entrée), models (RO), processed, output, uploads
├── docs/                   # cahier des charges, plans, guides, recettes, passation
└── docker-compose.yml
```

## 5. Démarrage rapide (Docker)

```bash
cp .env.example .env          # éditer SECRET_KEY, ADMIN_PASSWORD, POSTGRES_PASSWORD
docker compose up --build
```
→ **http://localhost:8080** (admin initial créé depuis `.env`). Détails et dépannage :
[`docs/EXPLOITATION.md`](docs/EXPLOITATION.md). Guide utilisateur :
[`docs/GUIDE_UTILISATEUR.md`](docs/GUIDE_UTILISATEUR.md).

## 6. Le moteur ML (entraînement)

L'entraînement est une opération **CLI maîtrisée** (jamais automatique en prod),
nécessitant l'environnement ML complet (`pip install -r requirements.txt`) et internet
**une seule fois** (téléchargement de `camembert-base`).

```bash
python scripts/setup_models.py            # 1 fois, avec internet (modèles de base en local)
python scripts/run_training.py --smoke    # validation rapide de la chaîne (minutes)
python scripts/run_training.py            # entraînement réel (CPU, plusieurs heures)
```
Produit `data/models/{classifier_niv1,classifier_niv2,sentiment,signals}/<version>/`
(+ ONNX int8) et `data/processed/eval_report.json`. Dépôt → `docker compose restart worker`
→ activation dans l'UI (Administration → Modèles). Détail complet :
[`docs/GUIDE_ENTRAINEMENT.md`](docs/GUIDE_ENTRAINEMENT.md).

Validation **sans torch** (stub) et jeu de démo synthétique :
```bash
python scripts/make_demo_data.py
python scripts/validate_pipeline.py --mdtc data/demo/mdtc_demo.xlsx --mopinion data/demo/mopinion_demo.xlsx
```

## 7. Données & RGPD

- **Anonymisation PII en tête de pipeline** (e-mails, téléphones, n° de commande, noms via NER) → marqueurs `[EMAIL]`, `[TEL]`, `[COMMANDE]`, `[NOM]`.
- La base ne stocke **que le texte anonymisé** (`verbatim_analyse`) ; jamais le brut.
- **Rétention** configurable (défaut 13 mois) + **purge** auto (démarrage worker) et manuelle (admin).
- **Classes contraintes** : toute prédiction respecte la hiérarchie de `taxonomy_cultura_poc.json` (un niv.2 appartient à un seul niv.1).

## 8. Sécurité

- Mots de passe **argon2** ; session **cookie httpOnly** ; **anti-bruteforce** (verrouillage après 5 échecs).
- **RBAC appliqué côté API** (rôles Analyste / Admin), pas seulement dans l'UI.
- **CORS** verrouillé localhost ; en-têtes nginx (CSP stricte, `X-Frame-Options: DENY`, `nosniff`).
- Secrets hors dépôt (`.env` gitignoré) ; modèles montés **lecture seule**.

## 9. Transmission / sauvegarde

Déplacer l'app **hors-ligne** vers un autre poste **en conservant l'historique** :
```bash
bash scripts/package_app.sh    # bundle : images + dump PostgreSQL + volumes + manifeste
# sur la cible : bash restore_app.sh (restaure + vérifie l'intégrité)
```
Voir [`docs/TRANSMISSION.md`](docs/TRANSMISSION.md).

## 10. Tests & recettes

Recettes **torch-free** (SQLite, classifieur stub), reproductibles hors ligne :
```bash
python app/tests/recette_v1.py   # conformité V1 (garde-fous §10 + DoD §11) -> 48/48
python app/tests/recette_v3.py   # ajouts V3 (annulation, reprise, ops, mot de passe) -> 13/13
```
Front : `cd app/web && npx tsc --noEmit && npm run build`.

## 11. Documentation

Tout est dans [`docs/`](docs/). Point d'entrée : **[`docs/PASSATION.md`](docs/PASSATION.md)**.
Cahier des charges, plans (V1/V2/V3), guides (utilisateur, entraînement, exploitation,
transmission), charte UI, recettes, suivi des lots.

## 12. Versions

- **V1** — application fonctionnelle (auth, ingestion, traitement async, résultats/exports, revue, dashboards, admin/RGPD).
- **V2** — couche design UI/UX (design system turquoise Cultura, navigation latérale, vue lot à onglets).
- **V3** (`v3.0`) — « POC avancée » : moteur ML prouvé, transmission avec historique, robustesse (annulation/reprise), exploitation, passation.
- **Reste** : run d'entraînement réel + mesure d'un lot ~11k **< 1 h** (DoD §11). Trajectoire : V1.1 (SSO Entra ID, serveur multi-utilisateur), V2 (MLOps depuis l'UI).

---

*Projet interne Cultura / eXalt — usage confidentiel.*
