# Spec V5 — Orchestration multi-moteurs, moteur Claude (API) & comparaison jugée

> **Statut** : projet de cahier des charges (à valider PO).
> **Principe directeur** : **additive et conditionnelle**. La V5 enrichit l'app de
> trois capacités (moteur Claude *de comparaison*, orchestration **en cascade** de
> deux moteurs, page **comparaison jugée**) **sans dégrader la posture offline de
> production** ni casser les moteurs/contrats existants. Tout est gardé derrière des
> drapeaux ; un poste qui ne configure rien se comporte exactement comme en V4.

Réf. : [CAHIER_DES_CHARGES.md](CAHIER_DES_CHARGES.md) (garde-fous §10, DoD §11),
[SPEC_V4_LMSTUDIO.md](SPEC_V4_LMSTUDIO.md). Cadence inchangée : **1 lot = 1 branche
`v5/N-nom` = 1 porte de validation PO**, merge `--no-ff`.

---

## 0. Décisions validées (ADR-lite, en amont de la rédaction)

| # | Sujet | Décision | Justification |
|---|---|---|---|
| V5-D1 | **Statut du moteur Claude** | Claude (API) est un moteur de **comparaison/test UNIQUEMENT** ; **jamais** sélectionnable pour un run de production. | Préserve le garde-fou §10 #1 (offline strict) sur tout traitement réel : aucune donnée client ne sort lors d'un run de prod. |
| V5-D2 | **Clé API** | `ANTHROPIC_API_KEY` lue depuis `.env` **uniquement** ; jamais en base, jamais saisie en UI. | Cohérent §10 #9 (secrets hors dépôt/base) et avec la gestion des autres secrets. |
| V5-D3 | **Rétention Anthropic** | On **documente** que les verbatims (anonymisés) transitent ; la souscription **Zero Data Retention** est à la charge du client. | POC : pas de garantie contractuelle embarquée ; transparence dans EXPLOITATION/TRANSMISSION. |
| V5-D4 | **Mode d'enchaînement** | **Cascade / raffinement** : le moteur 2 reçoit la sortie du moteur 1 et la valide/corrige. | Plus riche que deux passes indépendantes ; correspond au besoin « repasse par un LLM ». |
| V5-D5 | **Arbitrage cascade** | En cas de **désaccord** entre moteur 1 et moteur 2 → **revue humaine forcée** ; la sortie du moteur 2 (raffineur) fait foi. | Le 2ᵉ moteur arbitre, mais tout désaccord est signalé à l'humain. |
| V5-D6 | **Critère de désaccord** | Mesuré sur **`theme1_niv1`** uniquement (grand thème). | Simple, lisible, robuste ; évite de sur-déclencher la revue sur des nuances de niv.2/sentiment. |
| V5-D7 | **Chaîne optionnelle** | Par défaut **1 seul moteur** (comportement V4 inchangé) ; la chaîne est **opt-in** à la création du lot. | Zéro régression ; rétrocompatibilité des lots et des recettes. |
| V5-D8 | **Données comparées** | Un **échantillon tiré d'un lot déjà traité** (`done`), rejoué par 2-3 moteurs. | Réutilise le texte **déjà anonymisé+nettoyé** (`results.verbatim_analyse`) → rien de neuf à anonymiser. |
| V5-D9 | **Base du juge** | **Sans vérité terrain** : Claude tranche en **pairwise** « quelle classification est la plus pertinente ». | Le LLM-juge apporte de la valeur là où il n'y a pas d'étalon ; pas de gold requis. |
| V5-D10 | **Volume du juge** | Échantillon **plafonné, configurable (défaut 50)**. | Maîtrise du coût/latence des appels Claude. |
| V5-D11 | **Anti-biais du juge** | Juge **aveuglé** (libellés « A » / « B » sans nom de moteur) + **permutation aléatoire** de l'ordre. | Atténue le biais d'auto-évaluation (Claude jugeant Claude) et le biais de position. |
| V5-D12 | **Sans clé Claude** | Page comparaison en **mode dégradé** : métriques d'accord objectives, sans verdict du juge. | L'app reste utile hors-ligne ; le juge est un complément, pas un prérequis. |
| V5-D13 | **Contenu page comparaison** | Taux d'accord inter-moteurs · win-rate (juge) · distribution de confiance · latence/coût · exemples de désaccords commentés. | Couvre l'objectif « différences de perf entre moteurs ». |
| V5-D14 | **Déploiement client** | Si le projet est livré au client, **LM Studio y est installé** → la cascade de production (raffineur LLM) est toujours disponible. | Lève la dépendance hôte de la cascade ; le raffineur prod reste local (offline). |
| V5-D15 | **Client Claude** | Claude via **API native Anthropic** (`/v1/messages`, sortie structurée par *tool use*), **pas** de routage par LM Studio ni de réutilisation du bloc `lmstudio`. | Mécanisme propre ; découplage clair des deux moteurs LLM. |
| V5-D16 | **RBAC comparaison** | **Lancer** un run de comparaison = **admin uniquement** ; consulter = analyste+. | Gouvernance coût + égress. |

---

## 1. Contexte & objectifs

L'app dispose de trois moteurs (V4) : **`real`** (CamemBERT ONNX), **`stub`**
(heuristique), **`lmstudio`** (LLM local). La V5 ajoute :

1. **Un 4ᵉ moteur `claude`** (API Anthropic) — **uniquement** pour le test à la volée
   et la comparaison. Objectif : disposer d'un classifieur LLM de référence (qualité)
   pour étalonner les autres, sans engager l'app à un usage réseau en production.
2. **Une orchestration en cascade** de deux moteurs en production
   (proposeur → raffineur LLM) avec arbitrage par revue humaine sur désaccord.
3. **Une page « Comparaison »** qui rejoue un échantillon d'un lot à travers plusieurs
   moteurs, mesure leurs écarts, et — si une clé Claude est configurée — fait **juger**
   les divergences par Claude (prompt de juge).

**Non-objectifs** : remplacer CamemBERT/LM Studio ; faire de Claude un moteur de
production ; supprimer l'offline strict (il reste vrai pour tout run réel).

---

## 2. Principes directeurs & garde-fous

- **Offline strict de production préservé** (§10 #1) : un run de lot ne peut utiliser
  que des moteurs **éligibles production** (`real`, `stub`, `lmstudio`). `claude` en est
  **exclu** côté serveur (refus à l'activation et à la création de lot).
- **Anonymisation amont conservée** (§10 #2) : la comparaison rejoue le champ
  **`results.verbatim_analyse`** (texte **déjà anonymisé et nettoyé**). Aucun texte brut
  n'atteint Claude. En cascade, le raffineur LLM reçoit lui aussi du texte déjà anonymisé.
- **Jamais hors taxonomie** (§10 #3) : les sorties des moteurs LLM (`lmstudio`, `claude`)
  passent par la **même revalidation taxonomie + repli** que la V4 (`map_llm_response`).
- **Secrets hors dépôt/base** (§10 #9) : `ANTHROPIC_API_KEY` en `.env` uniquement.
- **RBAC, audit, localhost, pas d'action métier** : inchangés. **Lancer** une comparaison
  = **action admin** (gouvernance coût + égress) ; consulter les résultats = analyste+.
- **Caveat réseau explicite** : l'unique flux sortant possible est
  `worker → api.anthropic.com`, **et seulement** lors d'un test/comparaison utilisant
  Claude. Documenté dans EXPLOITATION/TRANSMISSION et **tracé à l'audit**.

---

## 3. Vision fonctionnelle

### 3.1 Moteur Claude (comparaison/test)
- Apparaît dans **Administration → Modèles** comme une ligne `claude:<modèle>`,
  `Type = Claude (API, comparaison)`. **Disponible** ssi `ANTHROPIC_API_KEY` est présente.
- **Pas de bouton « Activer »** (refus serveur si tentative) : un bandeau indique
  « moteur de comparaison uniquement — non utilisable en production ».
- Utilisable dans **Test à la volée** (sélecteur de moteur) et dans la **page Comparaison**.

### 3.2 Orchestration en cascade (production)
- À la **création d'un lot**, option « **Chaîner un 2ᵉ moteur (raffineur)** » :
  - Moteur 1 (proposeur) : `real` / `stub` / `lmstudio`.
  - Moteur 2 (raffineur) : un moteur **LLM** (`lmstudio` en production). *(Claude exclu.)*
- Le raffineur reçoit, pour chaque verbatim : le texte + la **proposition** du moteur 1
  (niv.1/niv.2, sentiment, signaux, confiance) et **valide ou corrige**.
- **Sortie persistée** = sortie du raffineur. **Si `theme1_niv1` diffère** entre les deux
  → `revue_humaine_requise = vrai` (forcée) + drapeau de désaccord.
- Les **deux** prédictions sont conservées (table `engine_predictions`) pour audit/analyse.
- Le `model_label` du lot reflète la chaîne, ex. `camembert-… ▶ lmstudio:mistral`.

### 3.3 Page « Comparaison »
- Lancée depuis un lot **terminé** : « Comparer les moteurs sur cet échantillon ».
- Paramètres : **moteurs à comparer** (2-3), **taille d'échantillon** (défaut 50),
  graine (reproductibilité), activation du **juge** (si clé présente).
- Le système **tire un échantillon** des résultats du lot, **rejoue** chaque moteur sur
  `verbatim_analyse`, stocke les prédictions, calcule les métriques, et — si juge actif —
  fait **juger** les paires divergentes par Claude.
- **Affichage** (V5-D13) :
  - **Taux d'accord** inter-moteurs sur `theme1_niv1` (matrice, objectif, sans juge) ;
  - **Win-rate** par moteur (verdicts du juge) ;
  - **Distribution de confiance** par moteur ;
  - **Latence / coût** par moteur (ms/verbatim, nb d'appels) ;
  - **Exemples de désaccords commentés** par le juge (verbatim + classifs A/B + verdict + justification).
- **Mode dégradé** (sans clé Claude) : tout s'affiche **sauf** win-rate et commentaires du juge.

---

## 4. Architecture technique

### 4.1 Points d'intégration (confirmés sur le code existant)
| Élément | Fichier | Évolution V5 |
|---|---|---|
| Dispatch moteur | `app/worker/classifiers.py` `get_predictor()` | + branche `kind == "claude"` → `ClaudePredictor` |
| Interface commune | `*/predictor.py` | + méthode `refine_cleaned_batch(cleaned, sats, proposals)` (LLM uniquement) |
| Détection/sync | `app/worker/model_registry.py` | + `_detect_claude(cfg)` (clé présente ? ping léger optionnel) |
| Activation | `app/api/app/api/routes_models.py` | **refus** si `kind == "claude"` (comparaison uniquement) |
| Config worker | `app/worker/config_worker.py` | + bloc `claude:` + surcharge env `ANTHROPIC_API_KEY` |
| Tâches worker | `app/worker/tasks.py` | + cascade dans `process_batch_job` ; + `run_comparison_job` |
| ORM | `app/common/models/` | + `engine_predictions`, `comparison_runs`, `judge_verdicts` ; + colonnes `batches` |
| Migration | `app/api/migrations/versions/0006_*` | nouvelles tables + colonnes |

### 4.2 Nouveaux modules
1. **`app/worker/llm_common.py`** *(refactor)* — fonctions **pures** extraites de
   `lmstudio_predictor` et **partagées** par les moteurs LLM : construction de prompt
   (modes *proposeur* et *raffineur*), `map_llm_response` (validation taxo + repli +
   garde-fous), helpers de normalisation. Le **transport HTTP reste propre à chaque
   moteur** (OpenAI-compatible pour LM Studio, Messages API pour Claude) ; seule la
   **logique de décision** est mutualisée. **Contrainte : `lmstudio_predictor` doit
   conserver un comportement identique (recette V4 50/50 inchangée).**
2. **`app/worker/claude_predictor.py`** — `ClaudePredictor` (interface compatible),
   client HTTP Anthropic (`/v1/messages`), modes proposeur + raffineur, **et** les
   fonctions de **juge** (`judge_pairwise`, aveuglement + permutation).
3. **`app/worker/comparison.py`** — orchestration d'un run de comparaison
   (échantillonnage, replay, métriques d'accord, latences), indépendant du juge.

### 4.3 Schéma de données (migration `0006`)
- **`engine_predictions`** — une ligne = prédiction d'un moteur pour un verbatim.
  `(id, batch_id, comparison_run_id?, result_id?, row_index, engine_label, role
  ['proposer'|'refiner'|'compare'], theme1_niv1, theme1_niv2, theme1_sentiment,
  confidence_globale, signals…, latency_ms, created_at)`.
  Sert **à la fois** à la cascade (proposeur+raffineur) et à la comparaison.
- **`comparison_runs`** — `(id, batch_id, created_by, created_at, status, engine_labels
  JSON, sample_size, seed, judge_enabled, metrics JSON, error_message)`.
- **`judge_verdicts`** — `(id, comparison_run_id, result_id, engine_a, engine_b, winner
  ['a'|'b'|'tie'], rationale, created_at)` (engine_a/b = libellés réels ; l'aveuglement
  est appliqué seulement *à l'appel*, pas au stockage).
- **`batches`** — + `refiner_label` (nullable ; null = lot mono-moteur, legacy) ;
  + `chain_disagreements` (compteur, nullable). `results` : on **réutilise**
  `revue_requise` (forcée sur désaccord) ; pas de nouvelle colonne nécessaire.

> Note rétrocompat : `refiner_label = NULL` ⇒ pipeline V4 strictement inchangé.

### 4.4 API (nouveaux endpoints)
- `POST /api/batches` — accepte un champ optionnel `refiner_label` (cascade).
- `POST /api/batches/{id}/comparisons` *(admin)* — crée un run
  (engines, sample_size, seed, judge).
- `GET /api/comparisons` · `GET /api/comparisons/{id}` (statut + métriques) ·
  `GET /api/comparisons/{id}/verdicts` (paginé) · `GET /api/comparisons/{id}/export`.
- `GET /api/models` — inclut la ligne `claude` (available = clé présente) ;
  `POST /api/models/{id}/activate` **refuse** `kind == "claude"` (400).

### 4.5 Front (React/TS, design system existant)
- **Création de lot** : bloc optionnel « Raffinement (2ᵉ moteur) » (sélecteur LLM).
- **Détail lot** : badge « cascade », compteur de désaccords, `model_label` enrichi.
- **Nouvelle page `Comparaison`** (route `/lots/:id/comparaison` ou onglet du lot) :
  formulaire de lancement + tableaux/graphes (réutilise `BarList`,
  `StackedSentimentBar`, `StatCard`, `Table`, `Drawer`).
- **Administration → Modèles** : ligne Claude (type, disponibilité, badge « comparaison
  uniquement », **pas** de bouton Activer).

### 4.6 Réseau / Compose
- Le **worker** doit pouvoir joindre `api.anthropic.com` **uniquement** lors d'un appel
  Claude. À documenter (le client peut restreindre l'égress du worker à ce seul domaine).
- `ANTHROPIC_API_KEY` injectée dans l'environnement du worker via `.env`
  (`ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}`), absente = moteur Claude indisponible.

---

## 5. Le moteur Claude en détail

- **Client natif Anthropic** : appel `POST https://api.anthropic.com/v1/messages` (format
  Messages d'Anthropic — **aucun** routage via LM Studio), modèle configurable
  (`claude.model`). **Sortie JSON contrainte par *tool use*** (outil à `input_schema`
  imposé + `tool_choice` forcé) : mécanisme distinct du `response_format` de LM Studio,
  mais **la forme de sortie et la revalidation taxonomie sont identiques** (mutualisées
  via `llm_common`). `temperature` basse.
- **Modes** : *proposeur* (même prompt que LM Studio, taxonomie injectée) et *raffineur*
  (prompt « voici une proposition {…}, valide ou corrige strictement dans la taxonomie »).
- **Validation** : sortie revalidée par `map_llm_response` (taxo + repli + garde-fous V4).
- **Robustesse** : timeouts + retries, **échec propre** (pas de repli silencieux),
  concurrence bornée (réutilise le pool de threads V4). Indisponible si pas de clé.
- **Garde-fou serveur** : non activable comme modèle de lot (refus à l'activation et au
  démarrage de job).

---

## 6. La cascade en détail (production)

1. À la création, `refiner_label` est posé (LLM). `process_batch_job` détecte la chaîne.
2. Pour chaque chunk : moteur 1 produit ses prédictions (comme aujourd'hui).
3. Moteur 2 (`refine_cleaned_batch`) reçoit `(texte, proposition_du_moteur_1)` et renvoie
   une prédiction validée/corrigée.
4. **Persistance** : la prédiction du moteur 2 alimente `results` (sortie qui fait foi) ;
   les **deux** prédictions vont dans `engine_predictions` (rôles `proposer`/`refiner`).
5. **Désaccord** : si `theme1_niv1(moteur1) != theme1_niv1(moteur2)` → `revue_requise = vrai`
   (forcée) + incrément `chain_disagreements`.
6. **Annulation coopérative** (R1/V3) et progression : inchangées (le coût ≈ 2× appels si
   le moteur 2 est LM Studio → granularité de commit ajustée comme pour LM Studio).

> Contrainte forte : **le raffineur DOIT être un moteur LLM**. Le dispatch refuse une
> chaîne dont le moteur 2 est `real`/`stub` (ils n'implémentent pas `refine_cleaned_batch`).

---

## 7. La comparaison + juge en détail

### 7.1 Run de comparaison (`run_comparison_job`)
1. Tire `sample_size` résultats du lot (`seed` pour reproductibilité).
2. Pour chaque moteur sélectionné : `predict_cleaned_batch(verbatim_analyse, satisfaction)`
   — `satisfaction` récupérée depuis `results.original_columns` si disponible.
3. Stocke les prédictions dans `engine_predictions` (rôle `compare`) + latences.
4. Calcule les **métriques objectives** : matrice d'accord `theme1_niv1`, distributions de
   confiance, latence/coût par moteur.
5. Si **juge actif** : pour chaque verbatim où deux moteurs **diffèrent** sur `theme1_niv1`,
   appelle `judge_pairwise` ; agrège en **win-rate** par moteur ; conserve N exemples
   commentés. Sinon → mode dégradé (étapes 1-4 seulement).

### 7.2 Prompt de juge (aveuglé)
- Entrée : verbatim + **Classification A** + **Classification B** (libellés neutres, ordre
  permuté aléatoirement, **aucune mention du moteur**).
- Sortie JSON contrainte : `{ "winner": "A"|"B"|"tie", "rationale": "…court…" }`.
- Le mapping A/B → moteur réel est **reconstruit côté serveur** après l'appel (la
  permutation est connue du worker, pas du juge).

### 7.3 Maîtrise du coût
- Échantillon plafonné (défaut 50, configurable, borne dure raisonnable ex. 200).
- Juge appelé **seulement** sur les paires divergentes (pas sur les accords).
- Run **asynchrone** (job RQ), progression + annulation comme un lot.

---

## 8. Confidentialité / RGPD / sécurité

- **Production = offline strict** : Claude exclu des runs ; cascade prod = LM Studio (local).
- **Comparaison/test** : seul moment où des données **anonymisées** peuvent transiter vers
  Anthropic, **si et seulement si** la clé est configurée et l'admin lance un run avec juge
  ou avec le moteur Claude. **Tracé à l'audit** (`comparison.run`, moteurs, n verbatims).
- **Anonymisation** garantie en amont (on n'envoie que `verbatim_analyse`).
- **Clé** en `.env` ; **caveat ZDR** documenté (souscription à la charge du client).
- **RBAC** : **lancement** d'un run de comparaison = **admin uniquement** ; consultation = analyste+.
- **Transmission** : `ANTHROPIC_API_KEY` **hors bundle** (comme les autres secrets) ;
  un poste cible sans clé fonctionne en mode dégradé.

---

## 9. Configuration (bloc `config.yaml`)
```yaml
claude:
  enabled: false                 # V5 désactivée par défaut → app inchangée
  model: "claude-…"              # modèle de comparaison (id API)
  base_url: "https://api.anthropic.com"
  temperature: 0.1
  timeout_s: 60
  max_parallel: 4
  retries: 2
  prompt_version: "v1"
  # clé via .env (ANTHROPIC_API_KEY) — JAMAIS ici

orchestration:
  cascade_enabled: false         # autorise la sélection d'un raffineur à la création de lot
  disagreement_field: "theme1_niv1"   # champ d'arbitrage (V5-D6)

comparison:
  default_sample_size: 50
  max_sample_size: 200
  judge_enabled: true            # ignoré si pas de clé Claude (mode dégradé)
```
Surcharge env : `ANTHROPIC_API_KEY`, `CLAUDE_ENABLED`, `CLAUDE_MODEL`.

---

## 10. Performance & robustesse
- Comparaison/juge **asynchrones** (RQ), progression + annulation coopérative (R1/V3).
- Échec propre des appels Claude/LM Studio (timeouts/retries) → run/lot `failed` net.
- Cascade : coût ≈ 2× le moteur le plus lent ; **pas d'objectif 11k < 1 h** quand un LLM
  est dans la chaîne (SLA détendue, comme V4).

---

## 11. Engagement « ne touche pas à la prod offline »
- Moteurs `real`/`stub`/`lmstudio` et front analyste : **inchangés** hors options opt-in.
- `refiner_label = NULL` ⇒ pipeline V4 strictement identique.
- Claude **jamais** dans un run de prod (refus serveur).
- Recettes **V1 48/48, V3 13/13, V4 50/50** restent vertes à chaque lot.

---

## 12. Découpage en lots

| Lot | Intitulé | Contenu clé | Dépend de |
|---|---|---|---|
| **C1** | Refactor LLM commun | Extraire `llm_common` (prompt proposeur, `map_llm_response`, garde-fous) depuis `lmstudio_predictor` **sans régression V4** ; ajouter le **mode prompt « raffineur »** + signature `refine_cleaned_batch`. | — |
| **C2** | Moteur Claude (comparaison) | `ClaudePredictor` (client `/v1/messages`, proposeur+raffineur), `kind="claude"`, `_detect_claude`, sync registre, **refus d'activation**, bloc config + `ANTHROPIC_API_KEY`, sélecteur dans *Test à la volée*, ligne « comparaison uniquement » dans Modèles. | C1 |
| **C3** | Orchestration cascade (prod) | Migration `0006` (`engine_predictions`, `batches.refiner_label`, `chain_disagreements`) ; cascade dans `process_batch_job` (raffineur LLM) ; désaccord `theme1_niv1` → revue forcée + traçabilité ; UI création de lot + détail. | C1 |
| **C4** | Comparaison (objective) | `comparison_runs` ; `run_comparison_job` (échantillonnage, replay multi-moteurs, métriques d'accord/confiance/latence) ; endpoints ; **page Comparaison** (mode dégradé sans juge). | C3 |
| **C5** | Juge Claude | `judge_pairwise` aveuglé + permuté ; `judge_verdicts` ; win-rate + exemples commentés ; intégration page ; **mode dégradé** propre sans clé. | C2, C4 |
| **C6** | Doc, sécurité & recette V5 | EXPLOITATION (clé, égress, caveat ZDR), TRANSMISSION (clé hors bundle), GUIDE_UTILISATEUR (page comparaison), `recette_v5.py` (Claude mocké, torch-free) ; tag `v5.0`. | tous |

Chemin critique : **C1 → C2 → C3 → C4 → C5 → C6** (C2 ∥ C3 possibles après C1).

---

## 13. Definition of Done — V5

- [ ] Moteur Claude **disponible si clé**, utilisable en *test à la volée* et comparaison,
      **non activable** en production (refus serveur vérifié).
- [ ] Cascade opt-in : proposeur → raffineur LLM ; désaccord `theme1_niv1` → revue forcée ;
      deux prédictions tracées ; `refiner_label=NULL` ⇒ comportement V4 identique.
- [ ] Page Comparaison : accord inter-moteurs, win-rate (juge), confiance, latence/coût,
      exemples commentés ; **mode dégradé** fonctionnel sans clé.
- [ ] Juge **aveuglé + permuté** ; appels limités aux divergences ; échantillon plafonné.
- [ ] Garde-fous : offline strict **en production** intact ; anonymisation amont ; jamais
      hors taxonomie ; clé hors base/dépôt ; égress documenté + tracé audit.
- [ ] **Aucune régression** : `recette_v1` 48/48, `recette_v3` 13/13, `recette_v4` 50/50,
      `recette_v5` vert ; `tsc`/build front OK ; `docker compose config` OK.

---

## 14. Risques & points de vigilance

| Risque | Impact | Mitigation |
|---|---|---|
| **Fuite de la posture offline** par un usage Claude en prod | Conformité RGPD | Refus serveur (Claude non activable, exclu des jobs de lot) + tests de recette dédiés. |
| **Biais d'auto-évaluation** du juge (Claude juge Claude) | Comparaison faussée | Aveuglement + permutation (V5-D11) ; afficher clairement « juge = Claude » ; ne pas survendre le verdict. |
| **Coût API** non maîtrisé | Budget | Échantillon plafonné, juge sur divergences seules, run admin-only, traçé. |
| **Régression du moteur LM Studio** lors du refactor `llm_common` | Casse V4 | Extraction iso-comportement + `recette_v4` 50/50 obligatoire au lot C1. |
| **Satisfaction absente** au replay (non stockée en colonne) | Sentiment dégradé en comparaison | Récupérer depuis `original_columns` ; sinon documenter l'écart (n'affecte pas la prod). |
| **Égress worker** bloqué chez le client | Comparaison/juge KO | Documenter le domaine `api.anthropic.com` à autoriser ; mode dégradé sinon. |

---

*Projet interne Cultura / eXalt — usage confidentiel. Document de travail V5 (à valider).*
