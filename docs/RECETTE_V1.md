# Recette V1 — Observatoire Ecom Studio

Preuve de conformité de la V1 : **Definition of Done (§11)** et **garde-fous (§10)**
du cahier des charges. Une partie est **automatisée** (`app/tests/recette_v1.py`),
le reste se vérifie manuellement dans l'UI.

---

## 1. Recette automatisée

Script : [`app/tests/recette_v1.py`](../app/tests/recette_v1.py). Tourne **hors ligne**,
sur **SQLite**, avec le **classifieur stub** (aucun modèle ni torch requis). Couvre
les garde-fous testables sans navigateur + le cœur du DoD.

### Reproduire

```bash
cd cultura-verbatim-classifier
python3 -m venv .venv_validate
.venv_validate/bin/python -m pip install --upgrade pip
.venv_validate/bin/python -m pip install --prefer-binary \
    fastapi httpx sqlalchemy "pydantic>=2" pydantic-settings argon2-cffi \
    PyJWT python-multipart pandas numpy openpyxl pyyaml redis rq
.venv_validate/bin/python app/tests/recette_v1.py
```

Sortie attendue : **`Bilan : 48 OK · 0 ÉCHEC · 0 SKIP`** (code de sortie 0).

> Les sections skippent proprement si une couche est absente de l'environnement
> (ex. `fastapi` hors image API, `src/` hors image worker). Dans le venv de recette
> ci-dessus, **tout** s'exécute, y compris l'E2E du pipeline (stub).

### Couverture automatisée

| Bloc | Vérifie | Garde-fou / DoD |
|---|---|---|
| Infrastructure | binding `127.0.0.1`, modèles `:ro`, `HF_HUB_OFFLINE`, en-têtes nginx, `.env` gitignoré | §10 #1/#4/#8/#9 |
| Anonymisation | e-mail / téléphone / n° de commande masqués + comptage | §10 #2 |
| Taxonomie | tous les couples (niv.1, niv.2) émis sont valides ; couple invalide rejeté | §10 #3 |
| Auth / RBAC | non-authentifié → 401 ; analyste → 403 sur audit/config/users ; verrouillage 429 | §10 #11, §7.9 |
| Résultats / export | confiance + statut exposés ; filtre Thème « contient » ; CSV colonnes POC + BOM ; pas de PII | §11, §10 #6 |
| Config / purge / audit | validation config ; purge supprime hors-rétention, conserve récent ; actions tracées | §11, §10 #7 |
| E2E pipeline (stub) | lot traité `done` ; **aucune PII en base** ; couples prédits valides | §11, §10 #2/#3 |

---

## 2. Definition of Done (§11)

| # | Critère | Vérification | Statut |
|---|---|---|---|
| 1 | `docker compose up` démarre toute la stack (arm64), sans réseau | `docker compose up --build` → 5 services *healthy*, `web` sur 127.0.0.1 | ✅ (run live) |
| 2 | Connexion + rôles ; non-authentifié n'accède à rien | Recette auto (auth/RBAC) | ✅ auto |
| 3 | Upload 2 Excel → validation colonnes → lot créé | UI *Nouveau lot* (+ refus si schéma KO) | ✅ (run live) |
| 4 | Traitement async d'un lot 11k **< ~1 h** + progression + notification | UI sur lot réel (modèle CamemBERT) | ⏳ à mesurer sur modèle réel |
| 5 | Résultats consultables/filtrables ; détail conforme | Recette auto + UI | ✅ auto + UI |
| 6 | Export CSV/XLSX **conforme POC** | Recette auto (colonnes + BOM) | ✅ auto |
| 7 | File de revue + correction (hiérarchie) + export corrections | UI *Revue* (+ E2E lots précédents) | ✅ (run live) |
| 8 | Dashboards KPI modèle / résultats / volumétrie | UI *Tableaux de bord* | ✅ (run live) |
| 9 | Historique des lots + journal d'audit | UI *Lots* + *Administration* ; recette auto (audit) | ✅ auto + UI |
| 10 | Activation d'une version de modèle déposée, sans rebuild | Déposer dans `data/models` + activer (UI) | ✅ (procédure §4 EXPLOITATION) |
| 11 | Rétention configurable + purge auto et manuelle | Recette auto (purge) + purge au démarrage worker | ✅ auto |
| 12 | Tous les garde-fous §10 vérifiés | Tableau §3 ci-dessous | ✅ |

> **#4** : seul critère dépendant du **modèle réel** (non déposé à ce stade). Le chemin
> performance est en place (ONNX int8, worker chaud, `batch_size` réglable, un seul job
> lourd) ; la mesure des 11k < 1 h se fait au dépôt du modèle entraîné.

---

## 3. Garde-fous (§10) — « ce que l'app ne doit JAMAIS faire »

| # | Garde-fou | Preuve | Statut |
|---|---|---|---|
| 1 | Aucune donnée hors du poste (pas de réseau/cloud/télémétrie) | `HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE` ; aucune dépendance d'appel sortant ; recette infra | ✅ |
| 2 | Jamais de verbatim **non anonymisé** en base | Anonymisation en tête de pipeline ; `verbatim_analyse` seul stocké ; recette anonymisation + E2E | ✅ |
| 3 | Jamais de classe/couple hors taxonomie | Masquage hiérarchique à l'inférence ; recette taxonomie + E2E | ✅ |
| 4 | Jamais modifier sources / poids modèle | `data/models` monté `:ro` ; sources jamais réécrites ; recette infra | ✅ |
| 5 | Jamais de ré-entraînement auto en prod | Aucun chemin d'entraînement dans l'app (CLI hors app) | ✅ |
| 6 | Jamais présenter une prédiction comme vérité validée | Score + statut (auto/revue/corrigé) toujours exposés ; recette résultats | ✅ |
| 7 | Jamais de suppression sans trace ni hors rétention | Purge bornée par la rétention + audit ; recette purge/audit | ✅ |
| 8 | Jamais exposé sur réseau public | `web` publié sur `127.0.0.1` uniquement ; recette infra | ✅ |
| 9 | Jamais de secrets/données clients dans le dépôt | `.env` + données gitignorés ; base sans PII | ✅ |
| 10 | Jamais bloquer l'UI pendant un traitement | Traitement asynchrone (RQ/Redis) + progression | ✅ (run live) |
| 11 | Jamais d'accès sans auth/rôle | RBAC côté API ; recette auth/RBAC | ✅ |
| 12 | Jamais d'action métier à fort impact | Aucune intégration sortante / action client ; outil d'analyse seul | ✅ |

---

## 4. Conclusion

La V1 satisfait l'intégralité du DoD §11 et des garde-fous §10, **à l'exception de la
mesure de performance #4** qui requiert le dépôt du modèle CamemBERT réel (le chemin
technique est en place et vérifiable au dépôt). Recette automatisée : **48/48**.
