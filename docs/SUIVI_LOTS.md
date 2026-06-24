# Suivi d'avancement — V1 « Observatoire Ecom Studio »

> Tableau de bord vivant du développement par lots. Mis à jour à chaque fin de lot.
> Réf. : [CAHIER_DES_CHARGES.md](CAHIER_DES_CHARGES.md) · [PLAN_DEVELOPPEMENT_V1.md](PLAN_DEVELOPPEMENT_V1.md)
>
> Cadence : **1 lot = 1 branche git = 1 incrément relisable**, puis **validation du PO** avant le lot suivant.
> Légende statut : ⬜ À faire · 🟦 En cours · ✅ Fait (validé PO) · ⏸️ En attente de validation

| Lot | Intitulé | Statut | Branche |
|---|---|---|---|
| L0 | Socle projet & conteneurisation | ✅ Fait (validé PO) | `lot/0` (mergé) |
| L1 | Auth, comptes & rôles | ✅ Fait (validé PO) | `lot/1` (mergé) |
| L2 | Cœur ML : worker async + gestion modèle | ✅ Fait (validé PO) | `lot/2` (mergé) |
| L3 | Ingestion & lancement de lot + suivi | ✅ Fait (validé PO) | `lot/3` (mergé) |
| L4 | Consultation résultats + exports (→ MVP) | ✅ Fait (validé PO) | `lot/4` (mergé) |
| L5 | Revue humaine & corrections | ✅ Fait (validé PO) | `lot/5` (mergé) |
| L6 | Tableaux de bord & KPI | ✅ Fait (validé PO) | `lot/6` (mergé) |
| L7 | Historique, audit, config & rétention (+ graphe thème×sentiment) | ✅ Fait (validé PO) | `lot/7` (mergé) |
| L8 | Durcissement, RGPD, perf, recette V1 | ✅ Fait (validé PO) | `lot/8` (mergé) |

> 🎉 **V1 complète (L0→L8) mergée sur `main` le 2026-06-18.** Seul reliquat DoD §11 #4 : mesurer un lot ~11k **< 1 h** au dépôt du modèle CamemBERT réel (chemin technique en place).

## Phase V2 — Couche design UI/UX
Réf. : [CHARTE_UI_V2.md](CHARTE_UI_V2.md) · [PLAN_V2_DESIGN.md](PLAN_V2_DESIGN.md). Choix validés : design-tokens CSS maison (zéro dépendance, offline), palette turquoise Cultura ajustable, refonte complète desktop-first. Garde-fou : **aucune régression** (build + `tsc` + recette V1 48/48 à chaque lot).

| Lot | Intitulé | Statut | Branche |
|---|---|---|---|
| D0 | Fondations : tokens, reset/global, primitives, vitrine `/design` | ✅ Fait (validé PO) | `design/0` (mergé) |
| D1 | AppShell (sidebar + topbar + fil d'Ariane) + Connexion + Accueil | ✅ Fait (validé PO) | `design/1` (mergé) |
| D2 | Lots & ingestion (liste, FileDropzone, détail/progression) | ✅ Fait (validé PO) | `design/2` (mergé) |
| D3 | Résultats & exports (filtres chips, Table, Drawer) | ✅ Fait (validé PO) | `design/3` (mergé) |
| D4 | Revue humaine (mode focus + raccourcis) | ✅ Fait (validé PO) | `design/4` (mergé) |
| D5 | Tableaux de bord & dataviz (StatCards, charts, alertes seuils) | ✅ Fait (validé PO) | `design/5` (mergé) |
| D6 | Vue lot **à onglets** (TdB/Résultats/Revue intégrés) + Administration (Tabs, Dialog purge, comptes) | ✅ Fait (validé PO) | `design/6` (mergé) |
| D7 | Finition, accessibilité AA & recette UI | ✅ Fait (validé PO) | `design/7` (mergé) |

> 🎨 **V2 (couche design) complète (D0→D7) mergée sur `main` le 2026-06-18.** Design-tokens turquoise Cultura (1 fichier), 13 composants `src/ui/` + AppShell + onglets ; toutes les pages habillées + vue lot à onglets. Aucune dépendance runtime ajoutée (offline strict). Recette V1 **48/48** (zéro régression).

## Phase V3 — Finalisation « POC avancée »
Réf. : [PLAN_V3.md](PLAN_V3.md). Périmètre validé : moteur ML CamemBERT prouvé de bout en bout, transmission conteneurisée avec historique, robustesse des traitements, exploitation & passation. Garde-fous : offline strict, 0 PII, taxonomie, recette V1 48/48 à chaque lot.

| Lot | Intitulé | Statut | Branche |
|---|---|---|---|
| T1 | Chaîne ML fiabilisée + smoke test + jeu de démo + guide entraînement | ✅ Fait (validé PO) | `v3/1` (mergé) |
| T2 | Run réel CamemBERT + perf 11k<1h (jalon PO) | ⬜ | — |
| P1 | Transmission : packaging & restauration avec historique | ✅ Fait (validé PO) | `v3/2` (mergé) |
| R1 | Robustesse traitements (annulation, reprise des jobs) | ✅ Fait (validé PO) | `v3/3` (mergé) |
| X1 | Exploitation (KPI ops) & changement de mot de passe | ✅ Fait (validé PO) | `v3/4` (mergé) |
| F1 | Dossier de passation + recette V3 + tag v3.0 | ✅ Fait (validé PO) | `v3/5` (mergé, tag `v3.0`) |

### Évolutions post-v3.0
| Lot | Intitulé | Statut | Branche |
|---|---|---|---|
| AIDE | Page « Comment ça marche » (vivante + essai interactif) + info-bulles contextuelles | ✅ Fait (validé PO) | `feat/aide-metier` (mergé) |

> 🏁 **V3 « POC avancée » mergée sur `main` (tag `v3.0`).** Chaîne ML prouvée (smoke), transmission hors-ligne avec historique, robustesse (annulation/reprise), exploitation (KPI ops + mot de passe), dossier de passation. Recettes : V1 **48/48**, V3 **13/13**. **Seul reste DoD §11 #4** : run réel CamemBERT (T2) + mesure lot 11k < 1 h (action data, à valider ensemble).

---

## L0 — Socle projet & conteneurisation ✅ (validé PO le 2026-06-17 — accueil affiché, DB/Redis OK)

**Objectif** : fondations techniques + lever le risque image worker arm64 (torch/onnx).

Critères d'acceptation :
- [x] Arborescence `app/` (api / worker / web) + moteur `src/` réutilisable
- [x] `docker-compose.yml` (web, api, worker, db Postgres, redis) + `.env.example`
- [x] `docker compose config` valide (syntaxe) — vérifié
- [x] API FastAPI : `/health` + `/api/health` + config + logging structuré
- [x] Squelette web React/TS (Vite) appelant `/api/health`
- [x] Worker RQ qui démarre et se connecte à Redis (code + bootstrap)
- [x] Base Postgres + Alembic configuré (migration baseline `0001`)
- [x] Exposition **localhost uniquement**, aucun accès réseau sortant au runtime (par conception)
- [ ] **À exécuter sur le poste (daemon Docker requis)** : `docker compose up --build` → page d'accueil + DB/Redis « OK ». *Valide aussi le build de l'image worker arm64 (torch/onnx) — risque technique #1.*

**Reste pour clore L0** : lancer `docker compose up --build` sur le laptop cible et confirmer l'écran d'accueil (composants OK). Ensuite → validation PO → merge.

---

## L1 — Auth, comptes & rôles ✅ (validé PO le 2026-06-17)

**Objectif** : sécuriser l'accès, poser le RBAC (Analyste / Admin).

Critères d'acceptation :
- [x] Table `users` (Alembic `0002`) ; mots de passe hachés (**argon2**)
- [x] Connexion / déconnexion (JWT en cookie **httpOnly**) ; session expirante (8h)
- [x] `GET /api/auth/me` ; RBAC **côté API** (dépendances `get_current_user` / `require_admin`)
- [x] Admin : créer / désactiver / réactiver, réinitialiser mot de passe, changer le rôle
- [x] Anti-bruteforce (verrouillage temporaire après 5 échecs)
- [x] Admin initial créé au démarrage si aucun utilisateur (via `.env`)
- [x] Front : page de connexion, shell authentifié, page admin « Utilisateurs », déconnexion
- [x] Garde-fous : pas d'auto-désactivation, dernier admin protégé ; non-authentifié bloqué ; Analyste bloqué sur écrans admin

**Validation automatisée** : test d'intégration FastAPI/SQLite **11/11 OK** (login, RBAC, garde-fous, validation mot de passe) ; front **type-check TS strict + build Vite OK**.
**Reste pour clore L1** : `docker compose up --build` sur le poste → se connecter (admin du `.env`) → créer un analyste → vérifier les accès. Puis validation PO → merge.

## L2 — Cœur ML : worker async + gestion modèle ✅ (validé PO le 2026-06-17)

**Objectif** : industrialiser le moteur du POC en traitement asynchrone tracé.

Critères d'acceptation :
- [x] Package partagé `common` (DB + modèles ORM) importé par `api` ET `worker`
- [x] Tables `batches`, `results` (texte **anonymisé** uniquement), `model_versions` (Alembic 0003)
- [x] Registre de modèles : découverte stub + modèle réel dans `/data/models`, activation (admin)
- [x] Tâche worker : lot Excel -> anonymisation -> nettoyage -> inférence -> résultats en base
- [x] Progression incrémentale (n traités/total) + gestion d'erreur **par verbatim**
- [x] Traçabilité **lot ↔ version de modèle** ; un seul job lourd concurrent (1 worker)
- [x] Mode **stub** (heuristique, sans torch) si aucun modèle réel -> app démontrable avant entraînement
- [x] Endpoints : `POST/GET /api/batches`, `GET /api/batches/{id}` (+ `/progress`), `GET /api/models`, `POST /api/models/{id}/activate`, `POST /api/models/rescan`
- [x] Aucun verbatim non anonymisé en base (seul `verbatim_analyse` est stocké)

**Validation automatisée** : test E2E FastAPI/SQLite **14/14 OK** (upload → traitement worker → 30 résultats persistés, hiérarchie taxonomie respectée, colonnes d'origine, progression, registre stub actif).
**Reste pour clore L2** : sur le poste, `docker compose down -v && docker compose up --build` (rebuild après refactor `common` + nouvelles deps API), vérifier que le worker synchronise le registre et que `GET /api/models` répond. (L'UI de lancement des lots arrive au L3.)

**Décision (D7)** : L2 embarque un **classifieur stub** (mots-clés) activé tant qu'aucun modèle CamemBERT n'est déposé/activé, afin de rendre l'app démontrable de bout en bout sans attendre l'entraînement (~2-4h). Le modèle réel se branche via le registre.
## L3 — Ingestion & lancement de lot + suivi ✅ (validé PO le 2026-06-17)

**Objectif** : permettre au métier de charger les fichiers et lancer/suivre un lot.

Critères d'acceptation :
- [x] Écran « Lots » : liste des lots (statut, progression, modèle, volumétrie)
- [x] Formulaire « Nouveau lot » : upload MDTC + Mopinion (l'un ou l'autre), label, seuil de revue
- [x] Lancement -> création du lot via l'API -> traitement asynchrone
- [x] Suivi : barre de progression (polling) jusqu'à « terminé », puis résumé du lot
- [x] Diagnostic clair en cas d'échec (message d'erreur du lot affiché)
- [x] Navigation : lien « Lots » dans l'en-tête + raccourci sur l'accueil

**Validation** : front **type-check TS strict + build Vite OK**. Endpoints back-end couverts par le test E2E L2 (14/14).
**Reste pour clore L2+L3** : rebuild sur le poste, puis dans l'UI : Lots → Nouveau lot → déposer `data/raw/mdtc_poc.xlsx` (et/ou mopinion) → suivre la progression → voir le résumé (mode stub).

## L4 — Consultation résultats + exports ✅ (validé PO le 2026-06-17, jalon MVP)
> Bug remonté à la recette : le filtre « Thème 1 » faisait une égalité exacte (mot partiel -> 0 résultat). **Corrigé en L5** (ilike « contient » sur niv.1 + niv.2).

**Objectif** : exploiter les résultats d'un lot (consultation, export) + test à la volée.

Critères d'acceptation :
- [x] Tableau des résultats paginé, **filtrable** (thème niv.1, sentiment, signaux, revue) + recherche texte
- [x] Colonnes utiles affichées (thèmes+scores, sentiment, signaux, confiance, statut revue)
- [x] Export **CSV** et **XLSX** conformes au format POC (colonnes d'origine + colonnes modèle)
- [x] **Test à la volée** : saisir un verbatim -> prédiction immédiate (via worker, modèle actif)
- [x] Affichage systématique du score de confiance et du statut (auto / revue)

**Validation automatisée** : test E2E FastAPI/SQLite **15/15 OK** (résultats filtrés/paginés, recherche, export CSV [origine+modèle, conforme POC] & XLSX, test à la volée). Front type-check TS strict + build Vite OK.
**Reste pour clore L4 (= MVP)** : sur le poste, après un lot terminé : Lots → (lot) → « Consulter les résultats » → filtrer, exporter CSV/XLSX ; et « Test à la volée » dans le menu.
## L5 — Revue humaine & corrections ✅ (validé PO le 2026-06-17)

**Objectif** : boucle qualité humaine (corriger les cas incertains) + correctif filtre.

Critères d'acceptation :
- [x] **Correctif L4** : filtre « Thème » en « contient » (ilike) sur niv.1 ET niv.2
- [x] File de revue : verbatims `revue_requise` non revus, triés par confiance croissante
- [x] Correction dans l'UI : niv.1/niv.2 **contraints par la taxonomie**, sentiment, signaux
- [x] Actions « Valider » (accepter tel quel) / « Corriger & valider » -> sort de la file
- [x] Corrections **historisées** (qui/quand/ancienne->nouvelle) ; résultat marqué corrigé/revu
- [x] Export du jeu « **corrections validées** » (pour ré-entraînement CLI)
- [x] `GET /api/taxonomy` pour alimenter les listes contraintes

**Validation automatisée** : test E2E FastAPI/SQLite **13/13 OK** (correctif filtre, file triée, correction valide/invalide [400 hiérarchie], historisation, valider-tel-quel, export corrections).
**Reste pour clore L5** : sur le poste, après un lot : détail du lot → « Revue humaine (N) » → corriger/valider quelques verbatims (listes niv.2 limitées au niv.1 choisi) → exporter les corrections ; et vérifier que le filtre « Thème (contient…) » marche dans Résultats.
## L6 — Tableaux de bord & KPI ✅ (validé PO le 2026-06-17)

**Objectif** : pilotage (KPI modèle, résultats du lot, volumétrie & tendances).

Critères d'acceptation :
- [x] KPI **résultats du lot** : distribution thèmes niv.1, sous-thèmes, sentiments, signaux, taux de revue, durée, sources
- [x] KPI **modèle** : métriques de la version active (F1 niv.1/niv.2, accuracy, rappel rupture) ou note « stub »
- [x] **Volumétrie & tendances** : évolution par lot (volume, taux de revue, signaux) + top thèmes global
- [x] Visualisations barres (composant `BarList`, sans dépendance lourde)
- [x] Endpoints : `GET /api/batches/{id}/kpi`, `GET /api/kpi/volumetry`, `GET /api/kpi/model`

**Validation automatisée** : test E2E FastAPI/SQLite **11/11 OK**. Front type-check TS strict + build Vite OK.
**Reste pour clore L6** : sur le poste, après un lot : détail → « Tableau de bord » (barres thèmes/sentiments, signaux) ; menu « Tableaux de bord » (modèle actif + volumétrie globale).
## L7 — Historique, audit, config & rétention ✅ (validé PO le 2026-06-18)

**Objectif** : traçabilité (audit), administration (config, rétention RGPD) + graphe demandé.

Critères d'acceptation :
- [x] **Graphe thème × sentiment × volumétrie** (barres empilées par sentiment) — lot + global
- [x] **Journal d'audit** (admin) : connexions, lancements, corrections, activations modèle, config, purge
- [x] **Configuration** (admin) : seuil de revue par défaut, durée de rétention (mois)
- [x] **Rétention/purge RGPD** : purge des lots au-delà de la rétention (manuelle + au démarrage worker) + suppression fichiers
- [x] Migration 0005 (audit_log, app_config)
- [x] Endpoints : `GET /api/audit`, `GET/PATCH /api/config`, `POST /api/admin/purge`

**Validation automatisée** : test E2E FastAPI/SQLite **14/14 OK** (crosstab lot+global, config get/patch/validation, purge, audit des actions clés, RBAC analyste→403).
**Validation PO le 2026-06-18** : stack reconstruite (`down -v` + `up --build`, migration 0005 appliquée), traitement de lot, page Administration et graphe thème×sentiment validés sur le poste.
## L8 — Durcissement, RGPD, perf, recette V1 ✅ (validé PO le 2026-06-18 — V1 complète)

**Objectif** : clore la V1 — sécurité, conformité RGPD/offline, performance, recette §11, documentation.

Critères d'acceptation :
- [x] **Durcissement nginx** : en-têtes de sécurité (CSP stricte, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, COOP), `server_tokens off`.
- [x] **Vérif sécurité** (déjà en place, confirmé) : anti-bruteforce (429 après 5 échecs), RBAC côté API, CORS localhost, cookie httpOnly, `.env` gitignoré.
- [x] **Vérif RGPD/offline** : anonymisation avant stockage (aucune PII en base), offline strict (`HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE`), modèles `:ro`, `web` sur `127.0.0.1` seul.
- [x] **Perf** : chemin 11k < 1 h en place (ONNX int8, worker chaud, `batch_size_inference` réglable, un seul job lourd) — mesure finale au dépôt du modèle réel.
- [x] **Recette automatisée** : `app/tests/recette_v1.py` (hors ligne, SQLite, stub) — **48/48 OK**, couvre garde-fous §10 + cœur DoD §11, E2E pipeline inclus.
- [x] **Documentation** : `GUIDE_UTILISATEUR.md`, `EXPLOITATION.md` (install, secrets, **sauvegarde/restauration**, dépôt/activation modèle, dépannage), `RECETTE_V1.md` (checklist DoD + garde-fous).

**Validation automatisée** : recette **48/48 OK** (`.venv_validate`), `docker compose config` valide. *(L8 ne modifie que `nginx.conf` côté front — aucun source TS touché.)*
**Reste pour clore L8 (recette PO sur poste)** : DoD #4 — mesurer un lot ~11k **< 1 h** une fois le modèle CamemBERT réel déposé (seul critère dépendant du modèle entraîné ; chemin technique vérifié).

---

## V4 — Second moteur « LM Studio » (LLM local) ✅ *(développé, recette 50/50)*

**Objectif** : ajouter un moteur de classification alternatif (LLM local via LM Studio,
API compatible OpenAI), sélectionnable côté admin, **sans rien changer** à l'app actuelle
(analyste, API, schéma DB, moteurs CamemBERT/stub). Spec : [SPEC_V4_LMSTUDIO.md](SPEC_V4_LMSTUDIO.md).

| Lot | Contenu | État |
|---|---|---|
| **O1** | Adaptateur `LMStudioPredictor` (interface commune, client `urllib`), dispatch `kind="lmstudio"`, `MODEL_KIND_LMSTUDIO`, bloc config `lmstudio:`, surcharge env, `extra_hosts` compose | ✅ |
| **O2** | Prompt versionné + injection taxo + `response_format` JSON schema + **matching tolérant** (casse/accents) + repli sentinelle `Autre / Non classé` + garde-fous (2 plafonds, conflit de sentiment, dé-doublonnage) | ✅ |
| **O3** | `_detect_lmstudio` (ping `/v1/models` + présence modèle), sync registre, `available` dynamique, onglet **Modèles** (badge, motif d'indisponibilité, Re-scanner = test de connexion) | ✅ |
| **O4** | Concurrence bornée (`max_parallel`, pool de threads, ordre préservé), retries transitoires, **fail-fast / échec propre** si LM Studio down, annulation coopérative respectée | ✅ |
| **O5** | Doc (EXPLOITATION §4 bis, TRANSMISSION, guide), recette V4, tag `v4.0` | ✅ |

**Garde-fous tenus** : `enabled: false` par défaut (app inchangée sans LM Studio) ; **0 migration
DB, 0 nouvelle route API, 0 changement front analyste/CamemBERT/stub** ; anonymisation amont
conservée ; jamais hors taxonomie (revalidation + repli) ; aucun flux hors machine.

**Validation automatisée** : `app/tests/recette_v4.py` **50/50 OK** (LM Studio mocké, torch-free),
non-régression **V1 48/48** + **V3 13/13**, `tsc`/build front OK, `docker compose config` OK.
**Reste (recette PO sur poste)** : installer LM Studio, charger un modèle + démarrer le serveur
local, activer le moteur, traiter un lot et juger la qualité/latence vs CamemBERT (SLA détendue).

---

## V5 — Multi-moteurs, Claude (comparaison), cascade & juge 🚧 *(en cours)*

**Objectif** : enrichir l'app de trois capacités **additives et conditionnelles** — moteur
**Claude** (API, comparaison/test **uniquement**, jamais en prod), orchestration **en cascade**
(proposeur → raffineur LLM) et **page Comparaison jugée** — **sans dégrader l'offline strict de
production**. `refiner_label = NULL` ⇒ pipeline V4 strictement inchangé.
Spec : [SPEC_V5_MULTI_MOTEUR.md](SPEC_V5_MULTI_MOTEUR.md) (fichier `SPEC_V5_MULTI_MOTEUR_1.md`).

| Lot | Contenu | État | Branche |
|---|---|---|---|
| **C1** | Refactor `llm_common` (verrou) : extraction iso-comportement des fonctions pures depuis `lmstudio_predictor` (prompt proposeur, `map_llm_response`, garde-fous, normalisation), **ré-exports** pour rétrocompat, **mode prompt raffineur** (`build_refiner_prompt`) + signature `refine_cleaned_batch(cleaned, satisfactions, proposals)` | ✅ Développé — **en attente validation PO** | `v5/1-llm-common` |
| **C2** | Moteur Claude (`claude_predictor.py`, client `/v1/messages` stdlib + tool use, proposeur+raffineur revalidés), `kind="claude"` dans `get_predictor`, `MODEL_KIND_CLAUDE`, `_detect_claude` + sync (jamais auto-activé), **refus d'activation 400** (`routes_models`), bloc config `claude:` + env `ANTHROPIC_API_KEY`/`CLAUDE_*`, sélecteur moteur *Test à la volée* (`/predict` `model_id`), ligne « comparaison uniquement » dans Modèles | ✅ Développé — **en attente validation PO** | `v5/2-moteur-claude` |
| **C3** | Cascade prod : migration `0006` (`engine_predictions` + `batches.refiner_label`/`chain_disagreements`), cascade dans `process_batch_job` (proposeur → raffineur LLM, `merge_cascade`, 2 prédictions tracées), désaccord `theme1_niv1` → revue forcée, `resolve_refiner` (LLM local seul ; Claude/CamemBERT/stub refusés), `model_label` enrichi « ▶ », UI création (sélecteur raffineur) + détail (badge cascade, désaccords) | ✅ Développé — **en attente validation PO** | `v5/3-cascade` |
| **C4** | Comparaison objective : migration `0007` (`comparison_runs` + FK `engine_predictions.comparison_run_id`), `comparison.py` (échantillon graine + métriques pures), `run_comparison_job` (replay 2-3 moteurs sur `verbatim_analyse`, rôle `compare`), endpoints (`POST /batches/{id}/comparisons` admin, `GET /comparisons[...]`, export CSV), **page Comparaison** (accord/confiance/latence/sentiment, mode dégradé sans juge) | ✅ Développé — **en attente validation PO** | `v5/4-comparaison` |
| **C5** | Juge Claude aveuglé + permuté, `judge_verdicts`, win-rate + exemples commentés | ⬜ À faire | — |
| **C6** | Doc (EXPLOITATION/TRANSMISSION/guide), `recette_v5` consolidée, tag `v5.0` | ⬜ À faire | — |

**Garde-fous tenus (C1)** : comportement `lmstudio` **strictement identique** (transport HTTP
inchangé, fonctions pures déplacées sans modification) ; aucun moteur/route/migration touché ;
`refine_cleaned_batch` revalide par `map_llm_response` (**jamais hors taxonomie**).

**Garde-fous tenus (C2)** : offline strict de PROD intact — Claude **refusé à l'activation** (400)
et jamais auto-activé → ne peut pas devenir le modèle d'un lot ; clé `ANTHROPIC_API_KEY` en `.env`
uniquement (jamais base/UI/config) ; sortie Claude revalidée par `map_llm_response` (**jamais hors
taxonomie**) ; `temperature` non envoyée (Opus 4.7+/Fable) ; échec propre (ClaudeError, pas de repli
silencieux) ; aucune dépendance ajoutée (stdlib `urllib`) ; moteurs `real`/`stub`/`lmstudio` inchangés.

**Garde-fous tenus (C3)** : **`refiner_label = NULL` ⇒ pipeline V4 strictement inchangé** (branche
mono-moteur intacte, aucune écriture `engine_predictions`) ; raffineur = **LM Studio uniquement**
(Claude exclu offline, CamemBERT/stub exclus faute de `refine_cleaned_batch`) — refus à la création
**et** au démarrage du job ; sortie raffineur revalidée par `map_llm_response` (**jamais hors taxo**) ;
migration **additive** (colonnes nullable, table neuve) ; anonymisation amont inchangée.

**Validation automatisée (C1+C2)** : `app/tests/recette_v5.py` **52/52 OK** (Claude/LLM mockés,
torch-free ; refus d'activation testé via TestClient) ; non-régression **V1 48/48 · V3 13/13 · V4 50/50** ;
`tsc --noEmit` OK ; `docker compose config` OK.

**Validation automatisée (C1+C2+C3)** : `app/tests/recette_v5.py` **71/71 OK** (cascade testée de bout
en bout en process, moteurs mockés) ; **migration 0006 appliquée en réel** (Postgres : `alembic_version
= 0006…`, table `engine_predictions` + colonnes `batches` vérifiées) ; non-régression **V1 48/48 · V3
13/13 · V4 50/50** ; `tsc --noEmit` OK ; `docker compose config` OK.

**Garde-fous tenus (C4)** : replay sur **`results.verbatim_analyse`** (déjà anonymisé → aucune nouvelle
anonymisation) ; **lancer = admin** (RBAC), consulter = analyste+ ; Claude utilisable comme moteur de
**comparaison** seulement (jamais en prod) ; échantillon **plafonné 200** ; migration additive ;
**juge non inclus** (mode dégradé, arrive en C5) ; recettes V1/V3/V4 inchangées.

**Validation automatisée (C1+C2+C3+C4)** : `app/tests/recette_v5.py` **95/95 OK** (métriques pures +
`run_comparison_job` end-to-end mocké + routes via TestClient) ; **migration 0007 appliquée en réel**
(Postgres : `alembic_version = 0007…`, table `comparison_runs` + FK vérifiées) ; **run de comparaison
réel** stub vs CamemBERT (n=50 : accord 20 %, 40 divergences, latence 0,05 vs 307 ms/verbatim) ;
non-régression **V1 48/48 · V3 13/13 · V4 50/50** ; `tsc --noEmit` OK ; `docker compose config` OK.

---

## Journal de décisions (ADR-lite)

| # | Date | Décision | Justification |
|---|---|---|---|
| D1 | 2026-06-17 | Stack V1 : FastAPI + React/TS + worker RQ + PostgreSQL + Redis, conteneurisée | Choix PO ; archi découplée portable vers un serveur ultérieurement |
| D2 | 2026-06-17 | PostgreSQL **100 % local** (aucun port exposé hors localhost) | Contrainte RGPD « no data egress » |
| D3 | 2026-06-17 | Nom de l'app : « Observatoire Ecom Studio » | Choix PO |
| D4 | 2026-06-17 | Dév. par Claude Code (agent unique) ; **pas de backlog formel**, suivi léger + commits par lot + portes de validation | Pas d'équipe humaine à coordonner ; valeur = continuité inter-sessions + visibilité PO + DoD |
| D5 | 2026-06-17 | Service `web` = nginx multi-stage (build React + sert le statique + proxy `/api`) au lieu de 2 services proxy+frontend | Moins de conteneurs sur un laptop, même résultat |
| D6 | 2026-06-17 | `api` reste **léger (sans torch)** ; tout le ML est dans le `worker` | Démarrage rapide de l'API, séparation des responsabilités, image API petite |
| D7 | 2026-06-17 | Package partagé `common` (DB + modèles ORM) + classifieur **stub** activé tant qu'aucun modèle réel n'est déposé | `api` et `worker` partagent le schéma sans duplication ; l'app est démontrable avant l'entraînement CamemBERT |
| D8 | 2026-06-18 | Recette V1 = **script unique** `app/tests/recette_v1.py` (SQLite + stub, hors ligne), exécuté en venv de recette ; non embarqué dans les images | Reproductible et torch-free ; le code étant réparti api/worker, un venv de recette couvre les deux couches d'un coup (48/48) ; les sections skippent proprement selon l'environnement |
| D9 | 2026-06-19 | V4 : moteur LM Studio branché sur l'unique point `get_predictor` (3ᵉ `kind`), **additif**, derrière `lmstudio.enabled=false` | « Ne touche à rien » : 0 migration, 0 route, 0 changement analyste ; l'app reste identique sans LM Studio |
| D10 | 2026-06-19 | LM Studio **natif sur l'hôte** (GPU Metal, API compatible OpenAI `/v1`), worker via `host.docker.internal:1234/v1` ; client en **stdlib `urllib`** | Perf Metal ; zéro dépendance ajoutée ; boucle locale → RGPD/offline préservés. *(NB : choix initial Ollama corrigé en LM Studio — adaptateur générique, bascule à faible coût.)* |
| D11 | 2026-06-19 | Confiance **auto-déclarée** par le LLM mais **durcie** par garde-fous déterministes (matching tolérant, 2 plafonds, repli `Autre / Non classé`, conflit de sentiment) | Pas de multi-échantillonnage (coûteux) ; routage revue fiable malgré une confiance LLM non calibrée ; jamais hors taxonomie |
| D12 | 2026-06-19 | SLA perf **détendue** + **échec propre** si LM Studio down (pas de repli silencieux) | LLM = 1 appel/verbatim (lent) assumé ; ne pas fausser la comparaison de qualité par un repli caché |
| D13 | 2026-06-23 | V5/C1 : logique de décision LLM extraite en `app/worker/llm_common.py` (pur, torch-free) **partagée** par les moteurs LLM ; transport HTTP **propre à chaque moteur** ; `lmstudio_predictor` **ré-exporte** les symboles déplacés (verrou anti-régression) | Préparer le moteur Claude (C2) sans dupliquer prompt/validation/garde-fous ; iso-comportement LM Studio garanti par `recette_v4` 50/50 + parité d'objet `op.X is llm_common.X` testée en `recette_v5` |
| D14 | 2026-06-23 | V5/C1 : raffineur = relecture de la proposition du moteur 1 (`build_refiner_prompt`), sortie **revalidée par `map_llm_response`** ; signature `refine_cleaned_batch(cleaned, satisfactions, proposals)` conforme SPEC_V5 §4.1 | Cascade (V5-D4) : le 2ᵉ moteur valide/corrige ; réutiliser le garde-fou taxo existant plutôt qu'un nouveau ; signature alignée sur la spec pour C3 |
| D15 | 2026-06-23 | V5/C2 : client Claude en **stdlib `urllib`** (et non le SDK `anthropic`), API Messages `/v1/messages` + **tool use forcé** ; `temperature` non envoyée | Cohérence avec le moteur LM Studio de référence (V4-D10), **zéro dépendance ajoutée**, `recette_v5` sans dépendance/torch-free ; `temperature`/`top_p` sont rejetés (400) par Opus 4.7+/Fable. La skill `claude-api` recommande le SDK : bascule possible si le PO le souhaite (ajout `anthropic` au worker + venv recette) |
| D16 | 2026-06-23 | V5/C2 : modèle Claude par défaut `claude-opus-4-8` ; détection **offline** (`available` = clé présente, sans ping réseau) ; refus d'activation **400** côté serveur + jamais auto-activé | Claude = classifieur LLM de référence (qualité) pour la comparaison ; ne jamais contacter Anthropic hors test/comparaison explicite ; garde-fou offline strict de prod (V5-D1) appliqué au niveau API |
| D17 | 2026-06-24 | V5/C3 : cascade branchée **en parallèle** du pipeline V4 dans `process_batch_job` (branche `if refiner_predictor is None: …V4… else: …cascade…`) ; la sortie raffineur fait foi, désaccord `theme1_niv1` → revue forcée (`merge_cascade`) ; les **2** prédictions tracées dans `engine_predictions` (rôles proposer/refiner, rattachées au `result`) | Garantit `refiner_label=NULL ⇒ V4 strictement identique` (chemin éprouvé non modifié) ; traçabilité d'audit/analyse sans nouvelle colonne sur `results` (réutilise `revue_requise`) |
| D18 | 2026-06-24 | V5/C3 : `engine_predictions.comparison_run_id` créée **nullable sans FK** en 0006 ; latence stockée en **moyenne par verbatim sur le chunk** (proposeur/raffineur séparés) | La table `comparison_runs` arrive en C4 (FK ajoutée alors) → migration C3 autonome ; pas de mesure par-verbatim disponible sans surcoût, l'approximation chunk suffit pour comparer les moteurs |
| D19 | 2026-06-24 | V5/C4 : métriques de comparaison isolées en fonctions **pures** (`worker/comparison.py`) ; le replay rejoue `verbatim_analyse` **sans satisfaction** (best-effort depuis `original_columns`, sinon None) | Testabilité (recette torch-free) + risque §14 assumé (satisfaction non stockée en colonne) ; n'affecte pas la prod, écart documenté |
| D20 | 2026-06-24 | V5/C4 : page Comparaison = **onglet du lot** (`/lots/:id/comparaison`) ; juge affiché en **mode dégradé** (EmptyState « lot C5 ») ; bornes (défaut 50 / max 200) en dur dans la route API (pas d'import du worker) | Réutilise le shell de détail de lot et ses composants (BarList/StackedSentimentBar) ; l'API n'importe pas le code worker (images séparées) ; juge = C5 |
