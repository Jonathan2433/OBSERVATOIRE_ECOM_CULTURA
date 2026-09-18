# Spec V4 — Second moteur de classification « LM Studio » (LLM local)

> **Statut** : **implémentée et alignée Cultura 2026** (lots O1→O5, recette V4
> 67/67 ; contrat V2 livré le 18/09/2026, après le tag historique `v4.0`).
> **Principe directeur** : **strictement additive**, aucun impact sur l'app existante
> (analyste, contrats API, schéma DB, moteur CamemBERT) — gardée derrière `lmstudio.enabled`.

---

## 1. Contexte & objectif

L'app dispose aujourd'hui de deux moteurs :
- **`real`** — CamemBERT fine-tuné (ONNX int8), entraîné hors-ligne, validé.
- **`stub`** — classifieur heuristique torch-free (mode démonstration).

La V4 ajoute un **3ᵉ moteur** : un **LLM local servi par LM Studio**, appelé via son
**API compatible OpenAI**. L'administrateur peut **basculer** dessus comme sur n'importe
quelle version de modèle, via l'onglet **Administration → Modèles** déjà en place.

**Objectifs retenus** :
1. **Agilité taxonomie / zéro réentraînement** — classifier sur une taxonomie
   *injectée dans le prompt* : on fait évoluer la taxo sans relancer l'entraînement.
2. **Viser une meilleure qualité** sur les cas ambigus / thèmes rares.

**Non-objectifs** : remplacer CamemBERT (coexistence), atteindre la perf ONNX, ou exposer
le LLM aux utilisateurs (aucun changement côté analyste).

---

## 2. Principes directeurs & garde-fous (inchangés vs app actuelle)

- **100 % local / hors-ligne** : LM Studio tourne **sur le poste**. Le seul flux réseau
  est l'appel `worker → host.docker.internal:1234/v1` (boucle locale de l'hôte). Les
  données **ne quittent jamais la machine**. Le modèle est **chargé dans LM Studio** au
  préalable (téléchargé une fois) ; offline strict conservé partout ailleurs.
- **Anonymisation conservée EN AMONT** : le texte envoyé au LLM est le **texte déjà
  anonymisé** (spaCy : `[NOM]`, `[EMAIL]`, `[TEL]`, `[COMMANDE]`).
- **Jamais hors taxonomie** : sortie **contrainte par schéma JSON** (`response_format`)
  puis **revalidée** contre la taxonomie (couple niv1→niv2). Incohérence → repli + revue.
- **Pas de ré-entraînement, pas d'action métier, localhost only, RBAC, audit** :
  identiques. L'activation du moteur LM Studio est **tracée** (`model.activate`).

---

## 3. Vision fonctionnelle

### 3.1 Côté analyste — **aucun changement**
Mêmes écrans, colonnes, export, file de revue, `confidence`. Seul indice du moteur :
le champ **`model_label`** du lot (ex. `lmstudio:mon-modele` au lieu de
`camembert-20260618_153719`) — déjà affiché, utile pour comparer.

### 3.2 Côté admin — **Administration → Modèles**
- Le moteur LM Studio apparaît comme une **ligne de modèle** :
  - `Version` = `lmstudio:<modèle>` ; `Type` = `LM Studio (LLM)`.
  - `Disponible` = **oui** si LM Studio répond, le modèle est chargé et le référentiel
    configuré est lisible ; **non** (grisé) sinon.
  - Bouton **Activer** (endpoint existant `POST /api/models/{id}/activate`).
- Bouton **Re-scanner** = **test de connexion** (relance la détection : ping `/v1/models`).
- Le changement de moteur n'affecte que les **nouveaux** lots.

---

## 4. Architecture technique

### 4.1 Point d'intégration (confirmé sur le code)
| Élément | Fichier | Rôle |
|---|---|---|
| Dispatch moteur | `app/worker/classifiers.py` `get_predictor()` | `kind=="real"`→CamemBERT, `"lmstudio"`→**nouveau**, sinon stub |
| Interface commune | `Stub/Verbatim/LMStudioPredictor` | `anonymizer, cleaner, batch_size, signal_thresholds, sentiment_labels, predict_cleaned_batch()` |
| Résolution actif | `model_registry.py` `get_active()` | lit `ModelVersion` actif en DB |
| Détection/sync | `model_registry.py` `sync_registry()` + `_detect_lmstudio()` | au démarrage worker / Re-scanner |
| ORM | `app/common/models/model_version.py` | `kind String(10)` accepte `"lmstudio"` |
| Activation | `routes_models.py` | endpoint admin, **réutilisé tel quel** |

### 4.2 Ce que la V4 ajoute (et **rien d'autre**)
1. **`LMStudioPredictor`** (`app/worker/lmstudio_predictor.py`) — torch-free, client
   **`urllib`** (stdlib). Même interface que les deux autres prédicteurs.
2. **Dispatch** : `if kind == "lmstudio": return LMStudioPredictor(cfg)`.
3. **Détection** : `_detect_lmstudio(cfg)` (ping `/v1/models` + présence du modèle et
   du référentiel déclaré ; versions de prompt/contrat publiées dans le registre).
4. **Config** : bloc `lmstudio:` dans `config.yaml` (+ surcharge env `config_worker.py`).
5. **Compose** : `extra_hosts: ["host.docker.internal:host-gateway"]` sur `worker`.

**Aucune** modif de : schéma DB, routes API, sérialisation des résultats, front analyste,
moteurs CamemBERT/stub.

### 4.3 Hébergement LM Studio (natif sur le Mac, GPU Metal)
- LM Studio installé **sur l'hôte** (GPU Metal), serveur local OpenAI-compatible activé.
- Le `worker` l'appelle via `http://host.docker.internal:1234/v1`.
- **Dépendance hors-conteneur** : documentée pour la transmission (§10).

```
┌─────────────── Docker (compose) ───────────────┐        ┌─ Hôte macOS ──┐
│ web · api · worker · db · redis                 │  HTTP  │  LM Studio    │
│   worker → host.docker.internal:1234/v1  ───────┼───────▶│ (Metal GPU,   │
└─────────────────────────────────────────────────┘        │  OpenAI API)  │
        (boucle locale — la donnée ne quitte pas la machine) └───────────────┘
```

---

## 5. Le moteur LLM en détail

### 5.1 Pipeline d'un verbatim (`LMStudioPredictor.predict_cleaned_batch`)
1. Texte **déjà anonymisé + nettoyé** (étapes amont inchangées).
2. Construction du **prompt** = consignes + **taxonomie injectée** + verbatim + satisfaction.
3. Appel **LM Studio** `POST /v1/chat/completions` avec :
   - `model` = `cfg.lmstudio.model`, `temperature` = `0.1`, `stream=false`
   - `response_format` = `{type:"json_schema", json_schema:{name, schema}}` (sortie structurée).
4. **Parse** (`choices[0].message.content` → JSON) **+ validation** (schéma + taxonomie).
5. **Garde-fous** déterministes (§6) → `confidence_globale` + `revue_humaine_requise`.
6. Renvoie le dict au **format identique** à `build_output()` (mêmes colonnes).

### 5.2 Prompt (versionné `lmstudio.prompt_version`)

Le prompt courant est **`v2-cultura-2026`**. Il injecte le référentiel embarqué
11 thèmes / 59 sous-thèmes et impose le contrat métier du moteur CamemBERT Cultura :

- un thème par défaut ; un second uniquement si le texte porte explicitement deux
  sujets distincts — une hésitation entre catégories proches n'est pas un bi-thème ;
- un sentiment unique par verbatim, recopié sur les deux thèmes ;
- si un avis mêle positif et négatif, conservation du ou des thèmes négatifs ;
- note de satisfaction normalisée sur 1–4 utilisée comme contexte auxiliaire ;
- confiance basse pour un texte court ou ambigu, trois signaux et JSON seul.

La branche `v1` reste implémentée pour la reproductibilité des lots historiques et
pour Claude, dont le contrat n'est pas modifié par cette évolution LM Studio.

### 5.3 Sortie structurée (`response_format` JSON schema)
```json
{ "themes": [ {"niv1":"…","niv2":"…","sentiment":"Négatif|Neutre|Positif","confidence":0.0} ],
  "signaux": {"rupture":false,"churn":false,"insatisfaction_forte":false} }
```
`themes` : 1 à 2 ; `confidence_globale` = confiance du thème principal.

### 5.4 Validation & repli (jamais hors taxonomie)
- **Appariement tolérant** : libellés LLM normalisés (casse + accents + espaces) et
  appariés aux libellés **canoniques** de la taxonomie — un thème correct mais mal
  capitalisé/accentué est **récupéré** (réécrit au canonique), sans jamais « deviner ».
- `niv1` introuvable **ou** `niv2` non-enfant de `niv1` → couple canonique de repli
  **`Général / Autre`** + **revue forcée**. *Pas de remap deviné.*
- JSON hors-forme → repli + revue, au plafond de confiance le plus bas (§6).
- **Dé-doublonnage** : couples identiques fusionnés.

> Le repli V2 appartient au référentiel Cultura 2026. La sentinelle historique
> `Autre / Non classé` n'est conservée que pour le contrat V1.

---

## 6. Score de confiance & garde-fous (auto-déclarée, durcie)

La confiance auto-déclarée par le LLM **n'est pas calibrée** ; on la conserve comme base
mais on la **plafonne** par des règles déterministes pour fiabiliser le routage en revue :

```
confidence_globale = confidence_déclarée
revue = confidence_globale < seuil_revue(batch)

# Garde-fous qui FORCENT la revue (et plafonnent la confiance) :
- couple niv1/niv2 hors taxo (après normalisation) → repli, revue, conf ≤ 0.40
- réponse JSON hors-forme                          → repli, revue, conf ≤ 0.30
- sentiment hors {Négatif,Neutre,Positif}          → Neutre + revue
- contrat V2, sentiments divergents avec Négatif   → thèmes négatifs seuls + revue
- contrat V2, divergence sans Négatif              → sentiment du thème 1 + revue
```
Tout est paramétré dans `config.yaml → lmstudio.guardrails`.

---

## 7. Performance & robustesse (SLA détendue assumée)

- **Pas d'objectif 11k < 1h** : 1 appel LLM/verbatim → traitement **long** assumé
  (l'UI ne bloque pas, barre de progression existante).
- **Concurrence bornée** : pool de threads `lmstudio.max_parallel` (défaut 4).
- **Timeouts + retries** par appel (`timeout_s`, `retries`).
- **Annulation coopérative** : check « lot annulé » par chunk (R1/V3) respecté.
- **Échec propre** : si LM Studio est injoignable, la 1ʳᵉ erreur **fait échouer le lot**
  (statut *failed* + message) — **aucun** repli silencieux vers CamemBERT.

---

## 8. Offline / RGPD / sécurité
Donnée **anonymisée avant** l'appel ; **rien ne sort de la machine** ; seul flux réseau
worker = boucle locale vers LM Studio ; modèle chargé localement ; activation tracée ;
RBAC admin pour basculer de moteur.

---

## 9. Configuration (bloc `config.yaml`)
```yaml
lmstudio:
  enabled: false                 # V4 désactivée par défaut → app inchangée
  base_url: "http://host.docker.internal:1234/v1"
  model: "local-model"           # id du modèle chargé (cf. GET /v1/models)
  taxonomy: "data/models/cultura_2026/taxonomy.json"
  temperature: 0.1
  timeout_s: 120
  max_parallel: 4
  retries: 2
  prompt_version: "v2-cultura-2026"
  contract_version: "cultura_2026"
  fallback_theme: "Général"
  fallback_niv2: "Autre"
  guardrails:
    repli_confidence_max: 0.40
    invalid_json_confidence_max: 0.30
    review_on_sentiment_conflict: true
```
Surcharge env (`config_worker.py`) : `LMSTUDIO_ENABLED`, `LMSTUDIO_BASE_URL`, `LMSTUDIO_MODEL`.

---

## 10. Transmission / exploitation
- `EXPLOITATION.md` §4 bis : installer LM Studio, charger le modèle, activer le serveur
  local, activer le moteur, perf/SLA, désactivation.
- `TRANSMISSION.md` : **dépendance hôte** (LM Studio + modèle chargé) hors bundle Docker.
- Moteur **`enabled: false` par défaut** → un poste sans LM Studio fonctionne comme avant.

---

## 11. Découpage en lots (réalisé)
| Lot | Contenu | État |
|---|---|---|
| **O1** | Adaptateur `LMStudioPredictor` + dispatch + config + compose | ✅ |
| **O2** | Prompts V1/V2 versionnés + schéma + matching tolérant + repli + garde-fous | ✅ |
| **O3** | `_detect_lmstudio` (`/v1/models`) + sync + onglet Modèles | ✅ |
| **O4** | Concurrence bornée + retries + fail-fast | ✅ |
| **O5** | Alignement Cultura 2026, registre/référentiel API, doc et recette V4 | ✅ |

**Validation** : `app/tests/recette_v4.py` **67/67** et `recette_v5.py` **115/115**
(LM Studio mocké, torch-free). La recette couvre prompts proposeur/raffineur, taxonomie
11/59, repli canonique, D-26 et référentiel servi à la revue.

---

## 12. Engagement « ne touche à rien »
- DB : **0 migration** (`kind` rentre dans `String(10)`).
- API : **0 nouvelle route** (activation/détection réutilisent l'existant).
- Front analyste : **0 changement**. Moteurs `real`/`stub` : **0 changement**.
- Tout est gardé derrière `lmstudio.enabled` (défaut `false`).
