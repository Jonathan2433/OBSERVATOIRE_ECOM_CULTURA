# Spec V4 — Second moteur de classification « Ollama » (LLM local)

> **Statut** : **implémentée** (lots O1→O5, recette V4 50/50, tag `v4.0`).
> **Principe directeur** : **strictement additive**, aucun impact sur l'app existante
> (analyste, contrats API, schéma DB, moteur CamemBERT) — gardée derrière `ollama.enabled`.

---

## 1. Contexte & objectif

L'app dispose aujourd'hui de deux moteurs :
- **`real`** — CamemBERT fine-tuné (ONNX int8), entraîné hors-ligne, validé.
- **`stub`** — classifieur heuristique torch-free (mode démonstration).

La V4 ajoute un **3ᵉ moteur** : un **LLM local servi par Ollama**, appelé en HTTP.
L'administrateur peut **basculer** dessus comme sur n'importe quelle version de modèle,
via l'onglet **Administration → Modèles** déjà en place.

**Objectifs retenus (arbitrage utilisateur)** :
1. **Agilité taxonomie / zéro réentraînement** — classifier sur une taxonomie
   *injectée dans le prompt* : on peut faire évoluer la taxo sans relancer 5h
   d'entraînement CamemBERT.
2. **Viser une meilleure qualité** sur les cas ambigus / thèmes rares.

**Non-objectifs** : remplacer CamemBERT (les deux coexistent), atteindre la perf
ONNX, ou exposer le LLM aux utilisateurs (aucun changement côté analyste).

---

## 2. Principes directeurs & garde-fous (inchangés vs app actuelle)

- **100 % local / hors-ligne** : Ollama tourne **sur le poste**. Le seul flux réseau
  est l'appel `worker → host.docker.internal:11434` (boucle locale de l'hôte). Les
  données **ne quittent jamais la machine**. `HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE`
  restent à `1` ; le modèle Ollama est **pré-téléchargé** (`ollama pull`) avant
  passage hors-ligne.
- **Anonymisation conservée EN AMONT** : le texte envoyé au LLM est le **texte déjà
  anonymisé** (spaCy : `[NOM]`, `[EMAIL]`, `[TEL]`, `[COMMANDE]`). On ne change pas
  ce pré-traitement — c'est l'`anonymizer`/`cleaner` partagé par tous les prédicteurs.
- **Jamais hors taxonomie** : la sortie du LLM est **contrainte par schéma JSON** puis
  **revalidée** contre la taxonomie (couple niv1→niv2). Toute incohérence → repli + revue.
- **Pas de ré-entraînement, pas d'action métier, localhost only, RBAC, audit** :
  identiques. L'activation du moteur Ollama est **tracée** (`model.activate`).

---

## 3. Vision fonctionnelle

### 3.1 Côté analyste — **aucun changement**
Mêmes écrans, mêmes colonnes, même export, même file de revue, même `confidence`.
Le seul indice du moteur utilisé reste le champ **`model_label`** du lot
(ex. `ollama:qwen2.5:7b` au lieu de `camembert-20260618_153719`) — déjà affiché dans
l'historique des lots, utile pour comparer.

### 3.2 Côté admin — **Administration → Modèles**
- Le moteur Ollama apparaît comme une **ligne de modèle** supplémentaire :
  - `Version` = `ollama:<modèle>` (ex. `ollama:qwen2.5:7b`)
  - `Type` = `ollama`
  - `Disponible` = **oui** si le service Ollama répond *et* le modèle est présent ;
    **non** (grisé) sinon, avec l'info au survol.
  - `État` = `actif` si sélectionné.
  - Bouton **Activer** (réutilise l'endpoint existant `POST /api/models/{id}/activate`).
- Bouton **Re-scanner** existant : relance la détection (ping Ollama + liste des modèles).
- Le **changement de moteur n'affecte que les NOUVEAUX lots** ; les lots passés
  conservent leur `model_label` et leurs résultats (même règle que le seuil de revue).

> Choisir *quel* modèle Ollama (qwen, llama, mistral…) se fait en **config**
> (`config.yaml` → `ollama.model`) au déploiement, en V4.0. Le rendre éditable à chaud
> dans l'UI est une évolution possible (hors périmètre V4 initial).

---

## 4. Architecture technique

### 4.1 Point d'intégration (confirmé sur le code)
| Élément | Fichier | Rôle |
|---|---|---|
| Dispatch moteur | `app/worker/classifiers.py:107` `get_predictor()` | `kind=="real"`→CamemBERT, `"ollama"`→**nouveau**, sinon stub |
| Interface commune | `StubPredictor` / `VerbatimPredictor` | `anonymizer, cleaner, batch_size, signal_thresholds, sentiment_labels, predict_cleaned_batch()` |
| Résolution actif | `app/worker/model_registry.py:91` `get_active()` | lit `ModelVersion` actif en DB |
| Détection/sync | `model_registry.py:62` `sync_registry()` + `_detect_real()` | au démarrage worker |
| ORM | `app/common/models/model_version.py` | `kind String(10)`, `label`, `path`, `metrics`, `is_active`, `available` |
| Activation | `app/api/.../routes_models.py:23` | endpoint admin, **réutilisé tel quel** |
| `model_label` | `app/worker/tasks.py:151` | posé au démarrage du lot |

### 4.2 Ce que la V4 ajoute (et **rien d'autre**)
1. **`OllamaPredictor`** (nouveau module `app/worker/ollama_predictor.py`) — torch-free,
   ne dépend que de `httpx`. Expose **la même interface** que les deux autres
   prédicteurs. Construit directement le dict résultat (mêmes clés que `build_output`).
2. **Dispatch** : une branche dans `get_predictor()` : `if kind == "ollama": return OllamaPredictor(cfg)`.
3. **Détection** : `_detect_ollama(cfg)` dans `model_registry.py` (ping + présence du
   modèle) → enregistre/maj une `ModelVersion(kind="ollama", label="ollama:<model>")`.
4. **Config** : un bloc `ollama:` dans `config.yaml` (+ surcharge env dans `config_worker.py`).
5. **Compose** : `extra_hosts: ["host.docker.internal:host-gateway"]` sur le service
   `worker` pour joindre Ollama sur l'hôte (Docker Desktop le fournit déjà sur Mac,
   on l'explicite pour la portabilité).

**Aucune** modification de : schéma DB (le `kind` rentre dans `String(10)`), routes API,
sérialisation des résultats, front analyste, moteur CamemBERT, moteur stub.

### 4.3 Hébergement Ollama (arbitrage : **natif sur le Mac, GPU Metal**)
- Ollama est installé **sur l'hôte** (pas dans Docker → bénéficie du **GPU Metal**,
  bien plus rapide que CPU-in-Docker).
- Le `worker` l'appelle via `http://host.docker.internal:11434`.
- **Dépendance hors-conteneur** : à documenter pour la transmission (voir §10).

```
┌─────────────── Docker (compose) ───────────────┐        ┌─ Hôte macOS ─┐
│ web · api · worker · db · redis                 │  HTTP  │   Ollama     │
│   worker → host.docker.internal:11434  ─────────┼───────▶│  (Metal GPU) │
└─────────────────────────────────────────────────┘        └──────────────┘
        (boucle locale — la donnée ne quitte pas la machine)
```

---

## 5. Le moteur LLM en détail

### 5.1 Pipeline d'un verbatim (dans `OllamaPredictor.predict_cleaned_batch`)
1. Texte **déjà anonymisé + nettoyé** (étapes partagées en amont, inchangées).
2. Construction du **prompt** = consignes + **taxonomie injectée** (niv1 → liste niv2)
   + le verbatim + score de satisfaction éventuel.
3. Appel **Ollama** `POST /api/chat` avec :
   - `model` = `cfg.ollama.model`
   - `format` = **schéma JSON** (sortie structurée — voir §5.3)
   - `options.temperature` = `0.1`, `options.num_ctx` = `cfg.ollama.num_ctx`
   - `stream=false`
4. **Parse + validation** du JSON (schéma + taxonomie).
5. **Garde-fous** déterministes (§6) → `confidence_globale` + `revue_humaine_requise`.
6. Renvoie le dict au **format identique** à `build_output()` (clés `theme1_niv1`,
   `theme1_niv2`, `theme1_sentiment`, `theme1_score_confiance`, `theme2_*`,
   `signal_rupture_client`, `signal_churn`, `signal_insatisfaction_forte`,
   `confidence_globale`, `revue_humaine_requise`, `nb_themes`, `verbatim_analysé`).

### 5.2 Prompt (structure, versionnée `ollama.prompt_version`)
- **Rôle** : « classifieur de verbatims e-commerce Cultura ».
- **Consignes dures** :
  - Choisir **1 à 2 thèmes** parmi la taxonomie fournie, **uniquement** des couples
    `niv1`/`niv2` valides (liste exhaustive injectée).
  - Sentiment ∈ `{Négatif, Neutre, Positif}`.
  - 3 signaux booléens : `rupture`, `churn`, `insatisfaction_forte`.
  - `confidence` ∈ [0,1] par thème (auto-évaluation honnête, basse si hésitation).
  - **Interdiction** d'inventer un thème ; si rien ne colle → thème de repli
    désigné (ex. `Autre / Non classé`) avec `confidence` basse.
  - Répondre **uniquement** en JSON conforme au schéma.

### 5.3 Sortie structurée (schéma JSON contraint par Ollama `format`)
```json
{
  "themes": [
    {"niv1": "string", "niv2": "string", "sentiment": "Négatif|Neutre|Positif",
     "confidence": 0.0}
  ],
  "signaux": {"rupture": false, "churn": false, "insatisfaction_forte": false}
}
```
- `themes` : 1 à 2 éléments. `confidence_globale` = confiance du thème principal
  (ou moyenne pondérée — à figer en O2).

### 5.4 Validation & repli (jamais hors taxonomie)
- **Appariement tolérant** (O2) : les libellés renvoyés par le LLM sont normalisés
  (casse + accents + espaces) et appariés aux libellés **canoniques** de la taxonomie.
  Un thème correct mais mal capitalisé/accentué est ainsi **récupéré** (et réécrit au
  libellé canonique) — sans jamais « deviner » : seul un libellé EXISTANT est accepté.
- `niv1` introuvable **ou** `niv2` non-enfant de `niv1` (même après normalisation) →
  **sentinelle de repli** `Autre / Non classé` (décision a) + **revue forcée** (décision c).
  *Pas de remap deviné* (choix utilisateur).
- JSON non parsable / hors-forme → repli + **revue forcée**, au plafond de confiance
  le plus bas (cf. §6) + log d'incident.
- **Dé-doublonnage** : deux thèmes de couple identique sont fusionnés (1 seul thème).

---

## 6. Score de confiance & garde-fous (arbitrage : **auto-déclarée**, durcie)

La confiance auto-déclarée par un LLM **n'est pas calibrée**. On la conserve comme base
mais on la **plafonne** par des règles déterministes pour que le routage vers la revue
reste fiable :

```
confidence_globale = confidence_déclarée
revue = confidence_globale < seuil_revue(batch)

# Garde-fous qui FORCENT la revue (et plafonnent la confiance) :
- couple niv1/niv2 remappé ou repli            → revue = True, confidence ≤ 0.40
- JSON invalide / réponse hors schéma          → revue = True, confidence ≤ 0.30
- thème = "Autre / Non classé"                 → revue = True
- 2 thèmes en désaccord de sentiment fort      → revue = True (optionnel, à figer O2)
```

> Ainsi le choix « auto-déclarée » est tenable **sans** multi-échantillonnage (coûteux) :
> on fait confiance au LLM quand il est cohérent, on bascule en revue dès qu'il sort
> du cadre. Tout cela est **paramétré** dans `config.yaml` (`ollama.guardrails`).

---

## 7. Performance & robustesse (SLA détendue assumée)

- **Pas d'objectif 11k < 1h** pour ce moteur. Le traitement LLM est **long** et assumé
  comme tel (lot lancé puis laissé tourner ; l'UI ne bloque pas, barre de progression
  existante).
- **Concurrence bornée** : le worker envoie les appels Ollama via un **pool borné**
  (`ollama.max_parallel`, défaut 4) pour saturer le GPU sans l'écrouler. Ollama gère
  le parallélisme côté serveur (`OLLAMA_NUM_PARALLEL`).
- **Timeouts + retries** par appel (`ollama.timeout_s`, retry à T=0).
- **Annulation coopérative** : le check « lot annulé » par chunk (déjà en place R1/V3)
  est respecté — on n'envoie plus d'appels après annulation.
- **Repli automatique** : si Ollama est injoignable au démarrage du lot, le moteur est
  marqué `available=false` ; comportement à figer en O4 (échec propre du lot avec
  message clair **ou** repli explicite vers le modèle CamemBERT actif — *décision O4*).
- **Estimation** affichée à l'admin : durée moyenne par verbatim mesurée → ETA du lot.

---

## 8. Offline / RGPD / sécurité

- Donnée **anonymisée avant** l'appel LLM ; **rien ne sort de la machine**.
- Le seul flux réseau du worker autorisé = la boucle locale vers Ollama. Tout le reste
  reste offline strict.
- Modèle Ollama **pré-pull** documenté ; aucune télémétrie.
- Activation tracée (audit), RBAC admin pour basculer de moteur.

---

## 9. Configuration (nouveau bloc `config.yaml`)

```yaml
ollama:
  enabled: false                 # V4 désactivée par défaut → app inchangée
  base_url: "http://host.docker.internal:11434"
  model: "qwen2.5:7b"            # modèle pré-pull, bon FR + sortie structurée
  temperature: 0.1
  num_ctx: 8192                  # doit contenir taxo + verbatim
  timeout_s: 120
  max_parallel: 4
  retries: 2
  prompt_version: "v1"
  fallback_theme: "Autre / Non classé"
  guardrails:
    repli_confidence_max: 0.40
    invalid_json_confidence_max: 0.30
```
Surcharge env dans `config_worker.py` (`OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_ENABLED`).

---

## 10. Transmission / exploitation

- `docs/EXPLOITATION.md` : section **« Moteur Ollama (option) »** — installer Ollama
  natif, `ollama pull <model>`, vérifier `http://localhost:11434`, activer le moteur.
- `docs/TRANSMISSION.md` : signaler la **dépendance hôte** (Ollama + modèle pull) qui
  n'est **pas** dans le bundle Docker ; checklist d'installation sur le poste cible.
- Le moteur reste **`enabled: false` par défaut** → un poste sans Ollama fonctionne
  exactement comme aujourd'hui.

---

## 11. Découpage en lots de développement

| Lot | Contenu | DoD / porte de validation |
|---|---|---|
| **O1 — Adaptateur** | `OllamaPredictor` (interface commune), branche `get_predictor`, bloc config, `extra_hosts` compose | Lot traité de bout en bout avec un **Ollama mocké** ; format de sortie identique au stub/réel ; `kind="ollama"` dispatché |
| **O2 — Prompt & sortie** | Prompt versionné + injection taxo + schéma JSON `format` + validation/repli + garde-fous confiance (§6) | Sur jeux de cas mockés : couples toujours valides, repli + revue forcée sur incohérence, confiance plafonnée |
| **O3 — Registre & activation** | `_detect_ollama` (ping + modèle présent), sync au démarrage, `available` dynamique, affichage onglet Modèles, **test de connexion** | Le moteur apparaît, activable/désactivable ; grisé si Ollama down ; activation tracée |
| **O4 — Concurrence & robustesse** | Pool borné, timeouts/retries, annulation coopérative, **politique de repli si Ollama down** (décision : échec propre vs repli CamemBERT) | Lot annulable ; Ollama coupé → comportement défini et testé ; pas de fuite de threads |
| **O5 — Doc & recette** | Recette V4 (Ollama mocké), maj `EXPLOITATION.md` / `TRANSMISSION.md` / `GUIDE_UTILISATEUR.md`, `SUIVI_LOTS.md` | Recette V4 verte ; docs à jour ; tag `v4.0` |

> Cadence identique aux V2/V3 : **un lot, une validation**, branche par lot, merge `--no-ff`.

---

## 12. Recette / validation

- **Torch-free**, dans `.venv_validate` : **mock du endpoint Ollama** (httpx) renvoyant
  des JSON canoniques. On teste : mapping des clés, validation taxo + repli, garde-fous
  confiance, dispatch `kind="ollama"`, détection `available`.
- **Smoke manuel** (utilisateur) : Ollama réel + petit lot, vérif qualité/latence et
  comparaison côte-à-côte avec un lot CamemBERT (même fichier).

---

## 13. Risques & limites (à assumer explicitement)

| Risque | Mitigation |
|---|---|
| Confiance LLM non calibrée → revue mal ciblée | Garde-fous déterministes §6 ; smoke de calibration sur échantillon |
| Latence élevée sur gros lot | SLA détendue assumée ; pool borné ; ETA affichée |
| Hallucination de thème | Schéma JSON + revalidation taxo + repli forcé en revue |
| Qualité FR variable selon modèle | Modèle configurable ; benchmark vs CamemBERT sur même lot |
| Taxo trop grande pour `num_ctx` | `num_ctx` configurable ; taxo compacte (niv1→niv2) ; sinon modèle à plus grand contexte |
| Dépendance hôte (Ollama) non conteneurisée | Documentée ; `enabled:false` par défaut ; app intacte sans Ollama |

---

## 14. Engagement « ne touche à rien »

- DB : **0 migration** (`kind` rentre dans `String(10)`).
- API : **0 nouvelle route** (activation réutilise l'existant ; détection côté worker).
- Front analyste : **0 changement**.
- Moteurs `real`/`stub` : **0 changement**.
- Tout est gardé derrière `ollama.enabled` (défaut `false`).
