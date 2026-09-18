# Observatoire Ecom Studio — Cultura Verbatim Classifier

Application interne de **classification et de pilotage des verbatims clients** de
cultura.com. Pour chaque verbatim (sources **MDTC** et **Mopinion**, ~11 000/mois),
le moteur produit : une **classification thématique hiérarchique** (niv.1 + niv.2,
contrainte par un référentiel), un **sentiment**, trois **signaux** (rupture client,
churn, insatisfaction forte), un **score de confiance** et un **routage vers la revue
humaine**. Le tout **100 % local, hors-ligne, sans GPU**.

Les tableaux de bord séparent explicitement les **notes déclarées** (une voix par
répondant, échelle native conservée) de l'**analyse automatique des réponses
textuelles ouvertes**. Une source attendue mais non reçue reste visible et n'est
jamais transformée en zéro mesuré.

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
        │                                              │  CamemBERT (PyTorch)
        ▼                                              ▼
   build React (Vite)                  volumes : models (RO) · uploads · output
                          Aucun trafic réseau sortant (offline strict)
```

- **`web`** : nginx, sert le build React et proxifie `/api` (en-têtes de sécurité, CSP).
- **`api`** : FastAPI/uvicorn — auth, RBAC, orchestration des lots, KPI, admin. **Sans torch** (démarrage léger).
- **`worker`** : RQ — exécute le pipeline ML lourd (réutilise le moteur `src/` du POC).
- **`db`** : PostgreSQL (utilisateurs, lots, réponses de questionnaire,
  **résultats anonymisés**, corrections, audit, config).
- **`redis`** : file de jobs.
- Package partagé **`app/common`** (engine SQLAlchemy + modèles ORM) importé par `api` **et** `worker` → schéma unique, pas de duplication.
- Tant qu'aucun modèle CamemBERT n'est déposé, un **classifieur stub** (heuristique, sans torch) rend l'app démontrable de bout en bout.
- **Plusieurs modèles CamemBERT coexistent** dans le sélecteur : chacun porte son
  référentiel, son seuil et sa couche de décision (profils `moteurs_camembert`).
  Un nouveau modèle s'**ajoute**, il ne remplace pas le précédent — le retour arrière
  est une simple resélection. Cf. [`docs/COUCHE_DECISION.md`](docs/COUCHE_DECISION.md) §8.

> ⚠️ **ONNX int8 n'est pas utilisé pour l'inférence** (`onnx.use_for_inference: false`).
> Mesuré : les modèles servis via ONNX ne s'accordent avec PyTorch que sur 55 % / 13 % /
> 74 % des argmax selon la tâche, pour un débit **3,3× plus lent** sur cette machine.
> Les artefacts sont conservés mais inertes ; les réactiver exige une requalification
> sur le matériel cible.

## 3. Pile technique

| Couche | Technologies |
|---|---|
| Front | React 18 + TypeScript + Vite ; **design system maison** (tokens CSS, 0 dépendance UI) |
| API | FastAPI, uvicorn, SQLAlchemy 2, Alembic, argon2, JWT (cookie httpOnly) |
| Worker / ML | RQ + Redis ; **CamemBERT** (HuggingFace Transformers, backend **PyTorch**), scikit-learn **1.6.1 épinglé** (signaux — cf. §6), spaCy (NER d'anonymisation). ONNX Runtime présent mais **désactivé** à l'inférence |
| Données | PostgreSQL 16, openpyxl (Excel) |
| Infra | Docker Compose (5 services), nginx, offline strict |

## 4. Structure du dépôt

```
cultura-verbatim-classifier/
├── src/                    # Moteur ML du POC (réutilisé par le worker)
│   ├── preprocessing/      # loader Excel, nettoyage, anonymisation (PII)
│   ├── modeling/           # architecture, export ONNX int8
│   ├── training/           # prepare_dataset, train_{classifier,sentiment,signals}
│   ├── inference/          # predictor (build_output) + decision.py (couche de décision)
│   └── utils/              # config, taxonomie, profils de moteurs (moteurs.py)
├── app/
│   ├── api/                # service FastAPI (routes, core, migrations Alembic)
│   ├── worker/             # service RQ (tâches, registre de modèles, classifieurs)
│   ├── common/             # package partagé : DB + modèles ORM + rétention
│   ├── web/                # front React/TS (ui/ design system, pages, styles)
│   └── tests/              # recettes V1→V6, L1a, L2, couche de décision
├── scripts/                # setup_models, run_training, validate_pipeline,
│                           # make_demo_data, package_app, restore_app
│                           # — refonte : entrainer_cultura, evaluer_cultura,
│                           #   ablation_leviers, calibrer_regle_source,
│                           #   courbe_seuil, publier_eval_report
├── config/config.yaml      # hyperparamètres, seuils, profils de moteurs, couche de
│                           # décision, cibles métier (source unique — aucun nombre
│                           # magique dans le code)
├── data/                   # raw (entrée), models (RO), processed, output, uploads
├── docs/                   # cahier des charges, plans, guides, recettes, passation
└── docker-compose.yml
```

## 5. Démarrage rapide (Docker)

**Prérequis** : [Docker Desktop](https://www.docker.com/products/docker-desktop/)
(allouer ≥ 8 Go RAM / 4 cœurs) et `git`. Aucune connexion réseau requise après le
premier `build`.

```bash
git clone <URL_DU_DEPOT>.git
cd cultura-verbatim-classifier
cp .env.example .env          # PUIS éditer .env (voir ci-dessous) ⚠️ obligatoire
docker compose up --build     # 1re fois : build des images (quelques minutes)
```
→ Ouvrir **http://localhost:8080** (exposé **uniquement** sur `127.0.0.1`).

### À éditer dans `.env` avant le 1er démarrage
| Variable | Rôle |
|---|---|
| `POSTGRES_PASSWORD` | Mot de passe de la base — **à figer une fois** (le changer après coup oblige à réinitialiser le volume). |
| `SECRET_KEY` | Clé de signature des sessions. Générer : `python -c "import secrets; print(secrets.token_urlsafe(48))"`. |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | **Compte administrateur initial** (≥ 12 caractères), créé automatiquement au 1er démarrage. |

### Connexion
Se connecter avec `ADMIN_USERNAME` / `ADMIN_PASSWORD`. L'admin peut ensuite créer
d'autres comptes (Analyste / Admin) dans **Utilisateurs** et changer son mot de passe
dans **Mon compte**.

### Quel moteur de classification ?
Le sélecteur (*Administration → Modèles*) liste tous les moteurs présents. Ils
**coexistent** : en activer un n'en supprime aucun.

| Moteur | Ce qu'il apporte | Activable en production |
|---|---|---|
| **stub** (heuristique) | aucun modèle requis — valide l'installation et l'interface | oui, mode démonstration |
| **CamemBERT** *(un par modèle déposé)* | la qualité ; chaque modèle porte son référentiel et ses seuils | oui |
| **LM Studio** (LLM local, V4) | second moteur, ou raffineur en cascade | oui, si `LMSTUDIO_ENABLED=true` |
| **Claude** (API, V5) | référence de qualité et juge de comparaison | **non** — refus serveur (offline strict) |

Aucun modèle entraîné n'est livré dans le dépôt : à l'installation l'app tourne en
**mode démonstration**. Entraîner et déposer un CamemBERT : §6 et
[`docs/GUIDE_ENTRAINEMENT.md`](docs/GUIDE_ENTRAINEMENT.md). LM Studio :
[`docs/EXPLOITATION.md`](docs/EXPLOITATION.md) §4 bis.

Arrêt : `Ctrl+C` puis `docker compose down` (les données persistent). Détails et dépannage :
[`docs/EXPLOITATION.md`](docs/EXPLOITATION.md). Guide utilisateur :
[`docs/GUIDE_UTILISATEUR.md`](docs/GUIDE_UTILISATEUR.md). **Transmission via GitHub** :
[`docs/TRANSMISSION_GITHUB.md`](docs/TRANSMISSION_GITHUB.md).

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
et `data/processed/eval_report.json`. Dépôt → `docker compose restart worker`
→ activation dans l'UI (Administration → Modèles). Détail complet :
[`docs/GUIDE_ENTRAINEMENT.md`](docs/GUIDE_ENTRAINEMENT.md).

**Deux règles pour qu'un modèle déposé soit exploitable :**

1. **Il embarque son référentiel** — `<racine>/taxonomy.json`. C'est ce fichier qui
   alimente les listes de la revue humaine. Sans lui, la revue proposerait le
   référentiel d'un autre modèle, dont les libellés peuvent n'avoir aucun rapport.
2. **Il est déclaré comme profil** dans `config.yaml → moteurs_camembert`, avec sa
   racine sous `data/models` (seul répertoire monté dans les conteneurs) et ses
   écarts au réglage global (seuils, couche de décision).

> ⚠️ **`scikit-learn` est épinglé** (`==1.6.1`). Les détecteurs de signaux sont des
> pipelines sérialisés avec joblib : les recharger sous une autre version fait dire à
> scikit-learn lui-même *« might lead to breaking code or invalid results »*. Relever
> cette borne **exige de réentraîner les détecteurs**.

**Refonte Cultura 2026** — chaîne dédiée, protocole sans fuite, découpage gelé :

```bash
python scripts/entrainer_cultura.py       # préparation + entraînement
python scripts/evaluer_cultura.py         # évaluation sur le jeu de test gelé
python scripts/ablation_leviers.py --split val   # apport de chaque levier de décision
```

Validation **sans torch** (stub) et jeu de démo synthétique :
```bash
python scripts/make_demo_data.py
python scripts/validate_pipeline.py --mdtc data/demo/mdtc_demo.xlsx --mopinion data/demo/mopinion_demo.xlsx
```

## 7. Données & RGPD

- **Anonymisation PII en tête de pipeline** (e-mails, téléphones, n° de commande, noms via NER) → marqueurs `[EMAIL]`, `[TEL]`, `[COMMANDE]`, `[NOM]`.
- **Liste blanche à l'ingestion** (D-18) : sur un export au format Cultura 2026, seules les colonnes **déclarées** sont lues. Les colonnes `Commande`, `Client`, `User Agent` et les captures d'écran des exports réels n'entrent donc ni en base ni dans l'export enrichi — elles ne sont pas anonymisées, elles ne sont pas lues.
- La base ne stocke **que le texte anonymisé** (`verbatim_analyse`) ; jamais le brut.
- La table `survey_responses` conserve une ligne par réponse source ayant produit
  au moins un verbatim : clé répondant opaque, source, date métier, note native et
  statut client normalisé. Elle évite de surpondérer les réponses Mopinion
  multi-champs. Voir la [note de migration](docs/MIGRATION_SATISFACTION_REPONDANT.md).
- **Rétention** configurable (défaut 13 mois) + **purge** auto (démarrage worker) et manuelle (admin).
- **Classes contraintes** : toute prédiction respecte la hiérarchie du référentiel **du modèle qui l'a produite** (un niv.2 appartient à un seul niv.1). Chaque modèle embarque le sien (`<racine>/taxonomy.json`) ; la revue humaine sert **celui du lot relu**, pas celui du moteur actif du moment.

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

**Recettes applicatives** — torch-free (SQLite, classifieur stub), hors ligne :

```bash
python app/tests/recette_v1.py   # conformité applicative + KPI répondant      -> 89 OK
python app/tests/recette_v3.py   # V3 : annulation, reprise, ops, mot de passe -> 13 OK
python app/tests/recette_v4.py   # V4 : moteur LM Studio                       -> 50 OK
python app/tests/recette_v5.py   # V5 : cascade, comparaison, juge Claude      -> 112 OK
python app/tests/recette_v6.py   # V6 : revue, export, cohérence des totaux    -> 26 OK
python app/tests/test_satisfaction_respondents.py  # KPI répondant ciblés       -> 10 OK
```

**Recettes du modèle** — nécessitent l'environnement ML (`requirements.txt`) :

```bash
python app/tests/recette_l1a_chargeur.py     # chargeur Cultura ; spaCy requis pour la recette réelle
python app/tests/recette_l2_protocole.py     # découpage sans fuite, plafonnement -> 15 OK
python app/tests/recette_couche_decision.py  # leviers, coexistence des moteurs   -> 46 OK
```

Sans le modèle spaCy français, L1a valide les garde-fous disponibles puis ignore
explicitement le chargement réel (`3 OK · 0 ÉCHEC · 1 SKIP` lors de la dernière
exécution locale). Aucun mode dégradé silencieux n'est accepté.

La recette de la couche de décision porte l'invariant central : **ce que
`build_output` décide en production est exactement ce que l'évaluation rejoue**.

Front : `cd app/web && npx tsc --noEmit && npm run build`.

## 11. Documentation

Tout est dans [`docs/`](docs/). Point d'entrée : **[`docs/PASSATION.md`](docs/PASSATION.md)**.
Cahier des charges, plans (V1/V2/V3), guides (utilisateur, entraînement, exploitation,
transmission), charte UI, recettes, suivi des lots.

### Modèle Cultura 2026 (refonte)

| Document | Objet |
|---|---|
| [`CADRAGE_NOUVEAU_MODELE.md`](docs/CADRAGE_NOUVEAU_MODELE.md) | cahier des charges de la refonte |
| [`SPEC_CHARGEUR.md`](docs/SPEC_CHARGEUR.md) · [`RAPPORT_L1a_CHARGEUR.md`](docs/RAPPORT_L1a_CHARGEUR.md) | ingestion de la livraison Cultura |
| [`RAPPORT_L2_BASELINE.md`](docs/RAPPORT_L2_BASELINE.md) | protocole sans fuite, baseline du modèle V1 |
| [`RAPPORT_L6_REENTRAINEMENT.md`](docs/RAPPORT_L6_REENTRAINEMENT.md) | réentraînement, trois itérations |
| **[`COUCHE_DECISION.md`](docs/COUCHE_DECISION.md)** | **les trois leviers de décision : ce qu'ils font, ce qu'ils rapportent** |
| [`OPTIMISATION_SANS_CULTURA.md`](docs/OPTIMISATION_SANS_CULTURA.md) | campagne d'optimisation, pistes écartées *(chiffres du §1 corrigés par le précédent)* |
| [`RECETTE_NOUVEAU_MODELE.md`](docs/RECETTE_NOUVEAU_MODELE.md) | recette L9, critères d'acceptation, activation |
| [`MIGRATION_SATISFACTION_REPONDANT.md`](docs/MIGRATION_SATISFACTION_REPONDANT.md) | migrations 0011/0012, déploiement et traitement des lots historiques |

## 12. Versions

- **V1** — application fonctionnelle (auth, ingestion, traitement async, résultats/exports, revue, dashboards, admin/RGPD).
- **V2** — couche design UI/UX (design system turquoise Cultura, navigation latérale, vue lot à onglets).
- **V3** (`v3.0`) — « POC avancée » : moteur ML prouvé, transmission avec historique, robustesse (annulation/reprise), exploitation, passation.
- **V4** (`v4.0`) — second moteur **LM Studio** (LLM local, API compatible OpenAI), sélectionnable côté admin, additif et désactivé par défaut. Voir [`docs/SPEC_V4_LMSTUDIO.md`](docs/SPEC_V4_LMSTUDIO.md).
- **V5** (`v5.0`) — **multi-moteur** : cascade proposeur/raffineur, page de comparaison de moteurs sur échantillon, moteur **Claude** en comparaison/test uniquement (jamais activable en production). Voir [`docs/SPEC_V5_MULTI_MOTEUR.md`](docs/SPEC_V5_MULTI_MOTEUR.md).
- **V6** — revue humaine et exports consolidés (cohérence des totaux liste/export).
- **Modèle Cultura 2026** (septembre 2026) — refonte complète du moteur sur le
  référentiel Cultura (11 thèmes / 59 sous-thèmes) : chargeur dédié, protocole
  d'évaluation **sans fuite**, réentraînement, **couche de décision** à trois leviers.
  Recette technique et métier prononcées ; **mise à disposition additive** (le modèle V1
  reste sélectionnable). Voir le tableau du §11.
- **Restitution métier — septembre 2026** — satisfaction calculée à la maille
  répondant, quatre sources attendues toujours visibles, statuts MDTC explicites,
  comparaison sur période métier et classement limité aux questions ouvertes.
- **Priorisation des irritants — septembre 2026** — les graphiques thème × sentiment
  du lot et du tableau de bord global classent les thèmes par **nombre absolu de
  verbatims négatifs décroissant**, puis par volume total et par libellé en cas
  d'égalité. Les volumes et les segments affichés ne sont pas modifiés.

**Reste à faire.** Bascule du modèle par défaut (décision humaine, tracée à l'audit) ·
mesure d'un lot ~11k **< 1 h** en conditions réelles (DoD §11) · atelier de
référentiel L3 côté Cultura (recouvrements de libellés) · validation par Cultura de
la table de correspondance des libellés de satisfaction MDTC (hypothèse eXalt) ·
mapping métier des questions fermées si leur restitution est retenue. Trajectoire : V1.1 (SSO
Entra ID, serveur multi-utilisateur), V2 (MLOps depuis l'UI).

---

*Projet interne Cultura / eXalt — usage confidentiel.*
