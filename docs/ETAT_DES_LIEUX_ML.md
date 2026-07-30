# État des lieux — Méthodologie & code du moteur ML actuel

> **Objet du document.** Décrire de manière factuelle et exhaustive **comment le modèle de
> machine learning actuel est construit, entraîné, évalué et exploité** dans l'application
> *Observatoire Ecom Studio — Cultura Verbatim Classifier*, afin de servir de **socle de
> référence** au cadrage du **nouveau modèle** demandé par Cultura (nouveaux fichiers,
> nouveaux comportements attendus).
>
> **Public visé.** Product Owner, data scientist, agent de développement.
> **Statut du code décrit.** `main` @ `95cddf8` (V1 → V5 mergées).
> **Version du document.** 1.0 — 30 juillet 2026.

---

## Sommaire

1. [Résumé exécutif](#1-résumé-exécutif)
2. [Ce que le modèle produit — le contrat de sortie](#2-ce-que-le-modèle-produit--le-contrat-de-sortie)
3. [Données d'entrée](#3-données-dentrée)
4. [La taxonomie — source de vérité](#4-la-taxonomie--source-de-vérité)
5. [Chaîne de préparation des données](#5-chaîne-de-préparation-des-données)
6. [Architecture des modèles](#6-architecture-des-modèles)
7. [Procédure d'entraînement](#7-procédure-dentraînement)
8. [Logique d'inférence et de décision](#8-logique-dinférence-et-de-décision)
9. [Évaluation — méthodologie et résultats mesurés](#9-évaluation--méthodologie-et-résultats-mesurés)
10. [Multi-moteur : CamemBERT, stub, LLM locaux, Claude](#10-multi-moteur--camembert-stub-llm-locaux-claude)
11. [Contrat d'intégration applicatif (annexe app)](#11-contrat-dintégration-applicatif-annexe-app)
12. [Configuration — inventaire des paramètres](#12-configuration--inventaire-des-paramètres)
13. [Limites, dettes et angles morts du modèle actuel](#13-limites-dettes-et-angles-morts-du-modèle-actuel)
14. [Points de décision pour le nouveau modèle](#14-points-de-décision-pour-le-nouveau-modèle)
15. [Cartographie des fichiers](#15-cartographie-des-fichiers)

---

## 1. Résumé exécutif

L'application classe les verbatims clients de cultura.com (~11 000/mois, sources **MDTC** et
**Mopinion**) et produit pour chaque verbatim : 1 à 2 **thèmes hiérarchiques** (niveau 1 +
niveau 2), un **sentiment**, trois **signaux** métier booléens, un **score de confiance** et
un **drapeau de revue humaine**. Tout tourne **en local, hors ligne, sur CPU**.

Le moteur actuel n'est **pas un modèle unique** mais un **assemblage de 4 modèles + une couche
de règles déterministes** :

| # | Composant | Technique | Sortie |
|---|-----------|-----------|--------|
| 1 | Classifieur niveau 1 | CamemBERT fine-tuné, **multi-label** (20 sigmoïdes, BCE) | probas des 20 thèmes |
| 2 | Classifieur niveau 2 | CamemBERT fine-tuné, **multi-classes** (67 softmax, CE) | probas des 67 sous-thèmes |
| 3 | Sentiment | CamemBERT fine-tuné, **3 classes** (softmax, CE) | Négatif / Neutre / Positif |
| 4 | Signaux (×3) | **LogReg scikit-learn sur embeddings CamemBERT gelés** | 3 probas binaires |
| 5 | Couche de décision | Python/numpy pur (`build_output`) | seuils, masquage hiérarchique, règles métier, confiance, routage revue |

Trois choix structurants expliquent la forme actuelle :

- **Contrainte hiérarchique appliquée à l'inférence, pas à l'entraînement.** Le modèle niv.2
  est entraîné à plat sur les 67 sous-thèmes ; au moment de prédire, les logits sont
  **masqués** pour ne conserver que les enfants du niv.1 retenu. Conséquence : **zéro couple
  (niv.1, niv.2) hors référentiel possible**, par construction.
- **Aucune tête custom.** Le score de satisfaction est injecté en **préfixe textuel**
  (`"[SATISFACTION 3/10] <verbatim>"`) plutôt que concaténé à l'embedding `[CLS]`, pour rester
  sur des architectures HuggingFace standard **exportables en ONNX int8** (contrainte CPU).
- **Signaux traités hors fine-tuning.** `signal_rupture_client` ne compte que **0,41 % de
  positifs** (29 / 7 000) : un fine-tuning complet sur-apprendrait. D'où la LogReg pondérée sur
  embeddings figés, avec **seuil calibré pour le rappel** (priorité métier : ne jamais rater
  une rupture).

**Verdict de performance mesurée** (jeu de test, `data/processed/eval_report.json`) :
le niveau 2 est excellent (F1-macro 0,891), le **niveau 1 est le point faible**
(F1-macro **0,564** vs cible cahier des charges **≥ 0,70**) et le **sentiment est faible**
(accuracy 0,641, F1-macro 0,605 — classe *Neutre* à 0,36). Les signaux `churn` et
`insatisfaction` sont corrects (F1 ≈ 0,85) mais **quasi redondants entre eux** ; la `rupture`
n'est pas mesurable de façon fiable (1 seul positif dans le test).

---

## 2. Ce que le modèle produit — le contrat de sortie

Défini par `OUTPUT_COLUMNS` dans `src/inference/predictor.py`. **Ce contrat est le point
d'ancrage de toute l'application** (base, exports CSV/XLSX, front, revue humaine, dashboards,
tous les moteurs alternatifs) : le modifier a un coût de propagation important.

| Colonne | Type | Sémantique |
|---|---|---|
| `verbatim_analysé` | texte | verbatim **anonymisé + nettoyé** (jamais le brut) |
| `nb_themes` | 0–2 | nombre de thèmes retenus (0 = verbatim vide/non exploitable) |
| `theme1_niv1` | libellé taxo | thème principal niveau 1 |
| `theme1_niv2` | libellé taxo | sous-thème, **toujours enfant** de `theme1_niv1` |
| `theme1_sentiment` | Négatif/Neutre/Positif | sentiment (au niveau du verbatim, recopié sur le thème) |
| `theme1_score_confiance` | 0–1 | probabilité sigmoïde du niv.1 principal |
| `theme2_*` | idem | second thème, présent uniquement si `nb_themes == 2` |
| `signal_rupture_client` | bool | client déclare rompre la relation |
| `signal_churn` | bool | risque d'attrition |
| `signal_insatisfaction_forte` | bool | insatisfaction majeure |
| `confidence_globale` | 0–1 | **moyenne arithmétique** de (`niv1_conf`, `niv2_conf`, `sentiment_conf`) du thème 1 |
| `revue_humaine_requise` | bool | `confidence_globale < thresholds.revue_humaine` |

Le CSV/XLSX livré au métier = **toutes les colonnes d'origine du fichier source + ces
colonnes enrichies**, encodage UTF-8 avec BOM.

**Points d'attention structurels du contrat actuel :**

- Le plafond est **dur à 2 thèmes** (`thresholds.max_themes: 2`). Un verbatim mentionnant
  3 sujets perd de l'information.
- Le sentiment est **unique par verbatim** et recopié sur les 2 thèmes. Un verbatim
  « livraison catastrophique mais super produit » ne peut pas porter deux sentiments
  divergents (limite assumée : il faudrait une annotation au niveau du *span*).
- `theme2_score_confiance` vaut `""` (chaîne vide) quand il n'y a qu'un thème, alors que
  `theme1_score_confiance` vaut `0.0` — **incohérence de typage** dans `_empty_result()`.
- **Au moins un thème est toujours retourné**, même si toutes les probas sont sous le seuil
  (repli sur l'argmax). Il **n'existe pas** de sortie « hors sujet / non classable » côté
  CamemBERT (les moteurs LLM ont, eux, une sentinelle `Autre / Non classé`).

---

## 3. Données d'entrée

### 3.1 Les trois schémas de fichiers

Le mapping des colonnes est **entièrement externalisé** dans `config/config.yaml → sources`,
et le chargement dans `src/preprocessing/loader.py`. Les fichiers sources ne sont **jamais
modifiés**.

**Source MDTC** (retours post-commande) :

| Rôle | Colonne |
|---|---|
| date | `Date de commande` |
| satisfaction | `Niveau de satisfaction général` |
| texte principal | `Verbatim justification` |
| texte secondaire | `Verbatim suggestion` |

→ concaténation `justification. suggestion` (les deux émanent du même client, même commande).

**Source Mopinion** (formulaire libre) :

| Rôle | Colonne |
|---|---|
| date | `Date du retour` |
| satisfaction | `Niveau de satisfaction général` |
| texte | première non-vide parmi `Description du bug` (insatisfaits) / `Suggestion` (satisfaits) |

**Historique labellisé** (`data/raw/historique_labels_poc.xlsx`) — **le jeu d'entraînement**,
14 colonnes, 7 000 lignes :

```
source | date | verbatim_original | satisfaction_score | nb_themes
theme1_niv1 | theme1_niv2 | theme1_sentiment
theme2_niv1 | theme2_niv2 | theme2_sentiment
signal_rupture_client | signal_churn | signal_insatisfaction_forte
```

Le loader normalise tout vers trois colonnes techniques préfixées pour éviter les collisions
métier : `__source__`, `__text_raw__`, `__satisfaction__`. **C'est le contrat interne du
pipeline** : ajouter une source nouvelle = écrire un loader qui produit ces trois colonnes.

### 3.2 Caractéristiques du jeu d'entraînement actuel

Source : `data/processed/dataset_stats.json`.

| Indicateur | Valeur |
|---|---|
| Total | **7 000** verbatims labellisés |
| Split | train **4 900** / val **1 050** / test **1 050** (70/15/15, stratifié sur `theme1_niv1`) |
| Verbatims mono-thème | 6 972 (**99,6 %**) |
| Verbatims bi-thèmes | **28** (0,4 %) |
| Distribution niv.1 | de 187 (`Annulation commande`) à 545 (`Suivi de commande et livraison`) — **remarquablement équilibrée** |
| Distribution sentiment | Négatif 2 400 / Neutre 2 319 / Positif 2 281 — **quasi parfaitement équilibrée** |
| `signal_rupture_client` | **0,41 %** de positifs (≈ 29 cas) |
| `signal_churn` | 25,6 % |
| `signal_insatisfaction_forte` | 25,7 % |
| PII masquées | 302 noms de personnes (`PER`) ; **0 email, 0 téléphone, 0 n° de commande** |
| Verbatims trop courts | 7 (conservés) / vides : 0 |
| Sous-thèmes rares (<50 ex.) | `Problème de remboursement` (34), `Erreur de prix` (31) |

> ⚠️ **Signal d'alerte majeur pour le cadrage.** Cette distribution est **trop propre pour
> être un échantillon de production** : équilibre quasi parfait des 20 thèmes et des 3
> sentiments, un seul thème par verbatim dans 99,6 % des cas, zéro email/téléphone/numéro de
> commande dans 7 000 verbatims de e-commerce. Il faut considérer comme **hautement probable
> que `historique_labels_poc.xlsx` soit un jeu synthétique ou fortement rééquilibré**. Les
> métriques mesurées ne sont donc **pas transposables** à la production, et le vrai enjeu du
> nouveau modèle est de savoir **ce que contiennent réellement les nouveaux fichiers**
> (déséquilibre réel, multi-thématique réelle, bruit, PII réelles).

---

## 4. La taxonomie — source de vérité

Fichier : `data/raw/taxonomy_cultura_poc.json`. Chargé par `src/utils/taxonomy.py` (classe
`Taxonomy`).

- **20 thèmes niveau 1**, **67 sous-thèmes niveau 2**.
- Structure : `{"themes": [{"niv1": "...", "niv2": ["...", "..."]}, ...]}`.
- **L'ordre du JSON est figé** : il sert d'index d'encodage des labels et **doit rester stable
  entre entraînement et inférence**. Insérer un thème au milieu du fichier décale tout
  l'espace de labels et invalide les modèles entraînés.

**Deux invariants vérifiés au chargement (lèvent une exception) :**

1. Pas de doublon de libellé niv.1.
2. **Pas de doublon de libellé niv.2 entre deux niv.1 différents.** Contrainte forte et non
   évidente : l'historique ne stocke que la chaîne niv.2 sans son parent, donc un même libellé
   sous deux parents rendrait l'encodage ambigu. *Exemple concret du référentiel actuel :
   « Erreur de prix » existe sous `Annulation commande` et « Erreur de prix affiché » sous
   `Prix produit` — les libellés ont dû être différenciés artificiellement pour respecter cet
   invariant.* Toute évolution de taxonomie devra soit conserver l'unicité globale des niv.2,
   soit **passer à une clé composite (niv1, niv2)** — refonte du module d'encodage.

**Les 20 thèmes niveau 1** (nombre de sous-thèmes entre parenthèses) :

Suivi de commande et livraison (5) · Tunnel de vente – Paiement (4) · Annulation commande (3) ·
Trouver son produit (4) · Prix de la livraison (3) · Site / Application (4) · Produit (3) ·
Service client (3) · Programme de fidélité (3) · Retour / Remboursement (3) ·
Disponibilité & Stock (4) · Click & Collect (4) · Compte client & Connexion (3) ·
Communication & Emails Cultura (3) · Fiche produit & Contenu (3) · Catalogue & Offre produit (3) ·
Prix produit (3) · Carte cadeau physique (3) · Expérience omnicanale (3) ·
Personnalisation & Recommandations (3).

**Utilitaires clés exposés** : `is_valid_pair(niv1, niv2)`, `hierarchy_mask()` (matrice
booléenne 20×67), `best_niv2_for_niv1(niv1, probs)` → argmax **restreint aux enfants**.

> Note : une table `taxonomy_entries` existe en base depuis la migration `0009` (permet la
> saisie de nouveaux thèmes lors de la revue humaine), mais **le JSON reste la source de
> vérité du modèle**. Les deux référentiels peuvent donc divergerdivergence à surveiller.

---

## 5. Chaîne de préparation des données

Orchestrée par `src/training/prepare_dataset.py`. **Point capital : cette chaîne est identique
à l'entraînement et à l'inférence**, pour que les distributions coïncident et qu'aucune PII
n'atteigne jamais le modèle.

### 5.1 Anonymisation — `src/preprocessing/anonymizer.py`

Exécutée **en tête de pipeline, avant tout traitement et tout stockage**.

Ordre d'application (important) :

1. **Regex** : e-mails → `[EMAIL]`, téléphones → `[TEL]`, numéros de commande → `[COMMANDE]`.
2. **NER spaCy** (`fr_core_news_sm`, entités `PER`) → `[NOM]`, avec **stoplist** pour éviter de
   masquer des mots courants ou des noms de marque détectés à tort.

Mode dégradé : si spaCy est absent, le module **continue avec les regex seules** et émet un
avertissement — les noms propres ne sont alors **pas** masqués. Comportement à connaître : il
échoue en silence sur la partie la plus sensible.

Le compteur de PII masquées est journalisé (`pii_masked` dans les stats).

### 5.2 Nettoyage — `src/preprocessing/cleaner.py`

Piloté par `config.yaml → cleaning` :

| Étape | Valeur actuelle |
|---|---|
| Normalisation Unicode | NFKC |
| Suppression emojis / pictogrammes | oui (7 plages Unicode) |
| **Passage en minuscules** | **`true`** |
| Normalisation des espaces | oui |
| Filtre longueur min | 5 tokens (signalé, non écarté à l'entraînement) |
| Longueur max | 512 tokens |
| Accents | **toujours préservés** |

> ⚠️ **`lowercase: true` est un choix contestable.** CamemBERT-base est un modèle **cased**
> (sensible à la casse) : le pré-entraînement a vu des majuscules. Le commentaire du code le
> reconnaît explicitement (« pour maximiser la performance on peut le désactiver ») mais
> conserve le réglage car « explicitement demandé au cahier des charges ». **Piste de gain
> rapide et quasi gratuite pour le nouveau modèle : tester `lowercase: false`.** Effet
> collatéral : les MAJUSCULES DE COLÈRE (signal d'intensité émotionnelle) sont actuellement
> détruites avant le modèle de sentiment.

Les verbatims **vides après nettoyage** sont écartés de l'entraînement ; à l'inférence ils
produisent un résultat neutre avec `revue_humaine_requise = true`.

### 5.3 Split et pondérations

- **Split stratifié 70/15/15** sur `theme1_niv1`, `random_state = seed = 42`. Repli sur split
  aléatoire si une classe est trop rare pour être stratifiée (log d'avertissement).
- **L'explosion des verbatims bi-thèmes en 2 exemples niv.2 intervient APRÈS le split** :
  aucun verbatim n'est partagé entre train/val/test. Pas de fuite.
- **Pondérations calculées sur le TRAIN uniquement** :
  - niv.1 : `pos_weight = n_neg / n_pos` par classe → `BCEWithLogitsLoss`.
  - niv.2 et sentiment : `balanced` = `total / (n_classes × count_c)` → `CrossEntropyLoss`.
- **Détection des classes rares** : avertissement < 30 exemples, pondération obligatoire < 50.

### 5.4 Artefacts produits

| Fichier | Contenu |
|---|---|
| `data/processed/dataset.csv` | texte nettoyé + labels + colonne `split` |
| `data/processed/encoders.json` | ordre des classes (dérivé de la taxonomie) + les 3 vecteurs de poids |
| `data/processed/dataset_stats.json` | statistiques de distribution, PII, classes rares |

`encoders.json` **dérive de la taxonomie**, jamais des données observées : c'est ce qui garantit
la cohérence train ↔ inférence.

---

## 6. Architecture des modèles

Module : `src/modeling/architecture.py`.

### 6.1 Modèle de base

`camembert-base` (licence MIT, HuggingFace), poids **rapatriés en local** dans
`data/models/camembert-base/` (≈ 442 Mo, `model.safetensors`) par `scripts/setup_models.py`.
Après cette étape, `local_files_only=True` partout → **fonctionnement hors ligne strict**.

### 6.2 Les trois têtes transformer

Toutes construites via `AutoModelForSequenceClassification` **standard** — décision explicite
pour préserver l'export ONNX d'`optimum`.

| Modèle | `problem_type` | Labels | Perte |
|---|---|---|---|
| niv.1 | `multi_label_classification` | 20 | `BCEWithLogitsLoss(pos_weight)` |
| niv.2 | `single_label_classification` | 67 | `CrossEntropyLoss(class_weight)` |
| sentiment | `single_label_classification` | 3 | `CrossEntropyLoss(class_weight)` |

**Justification documentée du choix niv.2 « à plat »** (`src/training/train_classifier.py`) —
le cahier des charges proposait 20 classifieurs niv.2 conditionnés ou une tête multi-têtes
hiérarchique ; l'implémentation a retenu une 3ᵉ voie :

- avec ~100 exemples par sous-thème, **un encodeur partagé unique** apprend de meilleures
  représentations que 20 petites têtes affamées de données ;
- **maintenance** : ajouter un sous-thème = 1 classe + réentraîner 1 modèle, pas recâbler
  20 têtes ;
- **export ONNX trivial** (têtes standard).

La hiérarchie est donc **imposée à l'inférence** par masquage — jamais apprise.

### 6.3 Injection du score de satisfaction

`src/utils/features.py → sentiment_input()`. Le score 1–10 devient un **préfixe textuel** :

```
"[SATISFACTION 3/10] le colis est arrivé avec deux semaines de retard"
```

Score invalide/absent → aucun préfixe. **Cette fonction doit être appelée à l'identique à
l'entraînement et à l'inférence**, sinon les distributions divergent (le code le signale en
capitales). Utilisée **uniquement** par le modèle de sentiment — les classifieurs thématiques
ne voient pas la satisfaction.

### 6.4 Détecteurs de signaux

`src/training/train_signals.py` + `EmbeddingExtractor`.

- Embeddings CamemBERT **gelés** (`AutoModel`, sans tête), **mean pooling masqué** (option `cls`
  disponible), dimension 768.
- Une **`Pipeline(StandardScaler → LogisticRegression)`** par signal, `class_weight='balanced'`,
  `max_iter=2000`, `C=1.0`, `random_state=42`.
- Les 3 signaux **partagent les embeddings** (une seule passe d'extraction) mais sont
  **entraînés séparément** (3 binaires indépendants).
- **Calibrage du seuil de rupture sur la validation** : `_threshold_for_recall()` renvoie le
  **plus grand seuil atteignant recall ≥ 0,80** (quantile des probas des positifs), afin de
  maximiser la précision sous contrainte de rappel. Les seuils `churn` et `insatisfaction`
  restent aux valeurs de config (0,50).
- Sérialisation `joblib` + `signals_metadata.json` (seuils retenus, métriques val/test,
  dimension d'embedding, pooling).

### 6.5 Versioning et export ONNX

**Versioning horodaté** : chaque entraînement écrit dans `<base>/<YYYYMMDD_HHMMSS>/` et met à
jour un fichier pointeur **`CURRENT`** contenant l'horodatage actif. `resolve_model_dir()`
résout la version au chargement (tolérant : si `CURRENT` absent, prend `base_dir`). Chaque
version embarque une **`training_card.json`** (tâche, type, labels, seuils, modèle de base,
meilleur F1-macro val, date).

Versions actuellement présentes dans `data/models/` :

| Modèle | Version active |
|---|---|
| `classifier_niv1` | `20260618_153719` |
| `classifier_niv2` | `20260618_173552` |
| `sentiment` | `20260618_194134` |
| `signals` | `20260618_194158` |

**Export ONNX + quantization int8** (`export_onnx_int8`) : quantization **dynamique**
(`is_static=False`, pas de données de calibration), config `AutoQuantizationConfig.avx2`,
sortie dans `<version>/onnx_int8/model_quantized.onnx`.

**Deux backends d'inférence interchangeables**, même API `predict_proba(texts) -> np.ndarray` :
`OnnxSeqClassifier` (privilégié) et `TorchSeqClassifier` (fallback). `load_classifier()`
tente l'ONNX puis retombe sur PyTorch avec un warning.

> ⚠️ La config `avx2` est une cible **x86**, alors que le poste de production est un **Mac
> Apple Silicon (arm64)**. Le gain de la quantization sur ce matériel n'est pas mesuré.
> ⚠️ L'`EmbeddingExtractor` des signaux **n'est pas exporté en ONNX** : l'inférence des signaux
> passe forcément par **PyTorch + une passe CamemBERT complète supplémentaire**. C'est
> mécaniquement le **goulot d'étranglement** du temps de traitement d'un lot (4 passes
> transformer par verbatim au total : niv.1, niv.2, sentiment, embeddings).

---

## 7. Procédure d'entraînement

L'entraînement est une **opération CLI maîtrisée, jamais déclenchée depuis l'application**
(garde-fou du cahier des charges : pas de réentraînement automatique en production).

### 7.1 Séquence

```bash
pip install -r requirements.txt            # env ML complet (torch, transformers, optimum…)
python scripts/setup_models.py             # 1 seule fois, AVEC internet
python scripts/run_training.py --smoke     # validation de la chaîne (quelques minutes)
python scripts/run_training.py             # entraînement réel (CPU, plusieurs heures)
```

`run_training.py` enchaîne : `prepare_dataset` → `train_niv1` → `train_niv2` →
`train_sentiment` → `train_signals` → export ONNX int8 → `evaluate`.
Options : `--skip-prepare`, `--skip-onnx`, `--skip-eval`, `--smoke`.

Validation **sans torch** possible via `scripts/make_demo_data.py` +
`scripts/validate_pipeline.py` (moteur stub, sortie attendue `✅ PIPELINE VALIDE`).

### 7.2 Boucle de fine-tuning — `src/training/trainer.py`

| Élément | Valeur |
|---|---|
| Optimiseur | AdamW, `lr = 2e-5`, `weight_decay = 0.01` |
| Scheduler | linéaire avec warmup, `warmup_ratio = 0.10` |
| Batch | 16 (train) / 32 (inférence) |
| Epochs | 5 max |
| Gradient clipping | norme 1.0 |
| **Early stopping** | sur **F1-macro validation**, patience 3, restauration du meilleur état |
| Seed | 42 (`set_seed`) |
| Device | `auto` (cible CPU) |
| `max_length` | 256 tokens |
| Mixed precision / grad accumulation | **aucune** (assumé, CPU) |
| Journal | `data/processed/training_logs.json` (métriques par epoch et par tâche) |

Métriques d'époque calculées : F1-macro, F1-micro, précision macro, rappel macro.

**Mode smoke test** (`config.yaml → smoke_test`) : 400 exemples, 1 epoch, `max_length = 64`.
Produit des artefacts **structurellement valides mais sans valeur prédictive** — à ne jamais
confondre avec un modèle de production.

### 7.3 Déploiement d'un modèle entraîné

1. Vérifier la présence et la non-vacuité des **4 sous-dossiers** de `data/models/`.
2. `docker compose restart worker` → `sync_registry()` détecte le modèle (`_detect_real`).
3. UI **Administration → Modèles → Activer** (action tracée à l'audit).
4. Les dashboards affichent les KPI lus dans `eval_report.json`, avec alerte visuelle si sous
   le seuil cible.

Le volume `data/models` est monté **en lecture seule** dans les conteneurs.

### 7.4 Pièges documentés

| Symptôme | Cause |
|---|---|
| `OSError ... camembert-base` | `setup_models.py` non exécuté (nécessite internet) |
| Entraînement très lent / OOM | réduire `batch_size_*`, ~8 Go RAM libres nécessaires |
| L'app reste en mode stub | sous-dossiers manquants/vides **ou** worker non redémarré |
| Pas de KPI qualité | `eval_report.json` absent (relancer sans `--skip-eval`) |

---

## 8. Logique d'inférence et de décision

`src/inference/predictor.py`. **Séparation volontaire en deux responsabilités** — c'est le point
d'architecture le plus réutilisable du projet :

- **`build_output(...)`** — **logique de décision PURE** (numpy/python, **sans torch**) :
  prend les probabilités brutes, applique seuils, masquage hiérarchique, plafond de thèmes,
  règles métier, agrégation de confiance, routage en revue. **Testable isolément, réutilisée
  telle quelle par tous les moteurs alternatifs.**
- **`VerbatimPredictor`** — orchestration : charge les modèles, anonymise, nettoie, tokenise,
  infère par lots, délègue.

### 8.1 Algorithme de `build_output`, étape par étape

```
0. Texte vide           → gabarit neutre, revue_humaine_requise = true. STOP.

1. Thèmes niv.1         : tri des probas décroissant
                          activés = { i : p_i >= 0.35 }
                          si aucun → activés = { argmax }      ← toujours ≥ 1 thème
                          troncature à max_themes = 2

2. Sentiment            : argmax(softmax) sur le verbatim entier
                          (le même pour les 2 thèmes)

3. Pour chaque niv.1    : niv.2 = argmax des probas RESTREINTES aux enfants
   retenu                 → couple (niv1, niv2) toujours valide

4. Signaux              : rupture       = p >= seuil calibré (val, recall≥0,80)
                          churn         = p >= 0,50
                          insat_modèle  = p >= 0,50
                          insat_règle   = (satisfaction <= 3) ET (sentiment == "Négatif")
                          ─────────────────────────────────────────────────────────
                          insatisfaction = insat_modèle OU insat_règle
                          churn          = churn OU rupture      ← règle métier
                                           « une rupture est par construction un churn »

5. Confiance            : confidence_globale = moyenne(niv1_conf, niv2_conf, sentiment_conf)
                                                        du thème 1 uniquement
                          revue_humaine_requise = confidence_globale < 0,50
```

### 8.2 Observations critiques sur cette logique

- **`confidence_globale` est une moyenne non pondérée de trois probabilités hétérogènes** :
  une sigmoïde multi-label (niv.1), un softmax sur 67 classes **déjà masqué** (niv.2), un
  softmax sur 3 classes (sentiment). Ces échelles ne sont pas comparables. La composante
  sentiment (3 classes → plancher ≈ 0,33) **tire mécaniquement la moyenne vers le haut**, et
  la composante niv.2 masquée est artificiellement élevée puisque restreinte à 3–5 candidats.
  **Ce n'est pas une probabilité calibrée** — juste un score heuristique. Aucune calibration
  (Platt, isotonique, température) n'est appliquée nulle part dans le projet.
- Le **thème 2 n'entre pas** dans la confiance globale ni dans la décision de revue.
- Le **seuil de revue vaut 0,50 en config** (`thresholds.revue_humaine`) alors que le cahier
  des charges spécifie **0,70** ; le commentaire du code indique « calibré sur le modèle
  réel ». Cohérent avec les mesures : à 0,50 → **9,8 %** des verbatims en revue ; à 0,65 →
  **100 %**. Autrement dit **le seuil contractuel de 0,70 est inexploitable avec ce modèle**.
- Le `OU` de la règle déterministe sur l'insatisfaction **ne peut qu'augmenter** le taux de
  positifs : c'est un booster de rappel, jamais de précision.
- La règle `churn = churn OU rupture` **est déjà vraie dans les données** (tout positif rupture
  est aussi churn) : elle est donc inopérante en pratique, mais protège d'une incohérence.

### 8.3 Traitement par lots

`src/inference/batch_processor.py` (CLI) et `app/worker/tasks.py` (production).

- Anonymisation pilotée **en amont** par l'appelant (pour journaliser les PII), puis
  `predict_cleaned_batch()` pour l'inférence pure.
- **Progression par chunks** : `PROGRESS_CHUNK = 250` verbatims entre deux commits (réduit pour
  les moteurs LLM afin de garder une progression visible et une annulation réactive).
- **Résilience par verbatim** : en cas d'échec du batch, repli `_predict_one_by_one` — un
  verbatim défaillant n'interrompt pas le lot.
- **Annulation coopérative** vérifiée entre chunks.

---

## 9. Évaluation — méthodologie et résultats mesurés

`src/evaluation/evaluate.py` → `data/processed/eval_report.json`. Évaluation sur le **split
test** (1 050 verbatims), en **rejouant la vraie logique de décision** (`build_output`), pas
seulement les sorties brutes des modèles.

### 9.1 Métriques calculées

- **niv.1** : F1 macro / micro / weighted (multi-label au seuil 0,35), F1 **par thème**,
  top-1 accuracy, **matrice de confusion 20×20** (+ heatmap ASCII).
- **niv.2** : F1 macro / weighted, **accuracy conditionnée au niv.1 vrai**, F1 par sous-thème.
- **Hiérarchique** : `P(niv1 correct)`, `P(niv2 correct | niv1 correct)`, `P(niv1 correct ∧ niv2
  faux)`, **`P(joint correct)`**.
- **Sentiment** : accuracy, F1 macro, F1 par classe.
- **Signaux** : précision / rappel / F1 / **AUC-ROC**, seuil et nombre de positifs.
- **Revue humaine** : **taux de mise en revue simulé pour 6 seuils** (0,50 → 0,80) — outil de
  calibrage du seuil opérationnel.

### 9.2 Résultats mesurés (version du 18/06/2026)

**Niveau 1 — le point faible**

| Métrique | Valeur | Cible CDC |
|---|---|---|
| **F1-macro** | **0,564** | **≥ 0,70** ❌ |
| F1-micro | 0,479 | – |
| F1-weighted | 0,551 | – |
| Top-1 accuracy | **0,830** | – |

Écart notable : top-1 accuracy 0,83 mais F1-micro 0,48 → le **seuil multi-label de 0,35 est mal
calibré** ; le modèle sait désigner le bon thème principal mais active trop de thèmes
secondaires parasites.

F1 par thème — dispersion extrême :

| Meilleurs | F1 | Pires | F1 |
|---|---|---|---|
| Prix produit | 0,970 | Produit | 0,284 |
| Service client | 0,907 | Suivi de commande et livraison | **0,314** |
| Communication & Emails | 0,811 | Trouver son produit | 0,317 |
| Prix de la livraison | 0,752 | Click & Collect | 0,348 |
| Catalogue & Offre produit | 0,730 | Personnalisation & Recommandations | 0,358 |
| Programme de fidélité | 0,716 | Annulation commande | 0,431 |

**Confusions dominantes lues dans la matrice** — toutes convergent vers
`Suivi de commande et livraison`, qui agit comme **thème aspirateur** :

| Vrai thème | Confondu avec | Cas |
|---|---|---|
| **Click & Collect** | Suivi de commande et livraison | **45 / 62** (le modèle échoue majoritairement) |
| Disponibilité & Stock | Suivi de commande et livraison | 17 |
| Retour / Remboursement | Suivi de commande et livraison | 10 |
| Service client | Suivi de commande et livraison | 9 |
| Annulation commande | Suivi de commande et livraison | 7 |
| Programme de fidélité | Tunnel de vente / Site / Application | 9 + 9 |
| Carte cadeau physique | Compte client & Connexion | 7 |

→ **Diagnostic : le problème n'est pas la capacité du modèle mais la conception du référentiel
niveau 1.** Les frontières entre `Suivi de commande et livraison`, `Click & Collect`,
`Disponibilité & Stock` et `Annulation commande` sont sémantiquement poreuses. C'est un sujet
de **cadrage métier**, pas d'hyperparamètres.

**Niveau 2 — excellent**

| Métrique | Valeur |
|---|---|
| F1-macro | **0,891** |
| F1-weighted | 0,896 |
| Accuracy (niv.1 vrai connu) | **0,900** |

**33 des 67** sous-thèmes à F1 ≥ 0,95. Pires : `Facile` (**0,154**), `Problème de remboursement`
(0,400 — classe rare, 34 ex.), `Commande non prête à l'heure prévue` (0,640),
`Prix trop élevé vs concurrence` (0,643), `Recherche peu efficace` (0,679),
`Filtres peu performants` (0,692).

> Le cas `Facile` (F1 0,154) est révélateur : c'est le **seul sous-thème positif** du
> référentiel (sous `Trouver son produit`), noyé parmi 66 sous-thèmes de plainte. Le
> référentiel est **structurellement conçu pour les irritants** — un axe majeur à trancher si
> le nouveau modèle doit aussi valoriser les retours positifs.

**Performance hiérarchique**

| Métrique | Valeur |
|---|---|
| P(niv.1 correct) | 0,830 |
| P(niv.2 correct \| niv.1 correct) | **0,913** |
| P(niv.1 correct ∧ niv.2 faux) | 0,087 |
| **P(couple complet correct)** | **0,757** |

Lecture : **la performance de bout en bout est plafonnée par le niveau 1.** Améliorer le niv.2
n'apporterait presque rien ; corriger le niv.1 remonterait mécaniquement le joint.

**Sentiment — faible**

| Métrique | Valeur |
|---|---|
| Accuracy | **0,641** |
| F1-macro | 0,605 |
| F1 Négatif | 0,663 |
| F1 **Neutre** | **0,360** |
| F1 Positif | 0,792 |

La classe **Neutre est le trou noir** du modèle, alors même que le jeu est parfaitement
équilibré (2 319 exemples) et que le score de satisfaction est injecté en préfixe. Deux
hypothèses : « Neutre » est mal défini dans l'annotation, ou la granularité 3 classes est
inadaptée (une échelle ordinale ou une régression sur la satisfaction serait plus naturelle).

**Signaux**

| Signal | Seuil | Précision | Rappel | F1 | AUC | n+ test |
|---|---|---|---|---|---|---|
| **rupture** | **0,95** (calibré) | 0,333 | 1,000 | 0,500 | 1,000 | **1** |
| churn | 0,50 | 0,744 | **0,993** | 0,850 | 0,931 | 275 |
| insatisfaction | 0,50 | 0,745 | **0,993** | 0,851 | 0,931 | 276 |

Trois constats :

1. **`rupture` n'est pas évaluable** : 1 seul positif dans le test, AUC = 1,0 et précision 0,33
   sont statistiquement vides de sens. Le seuil calibré à 0,95 (borne haute de la plage
   admise) trahit un modèle qui sépare artificiellement bien sur si peu de cas.
2. `churn` et `insatisfaction` ont des métriques **quasi identiques à 3 décimales**
   (P 0,744/0,745 · R 0,993 · F1 0,850/0,851 · AUC 0,9315/0,9310) : les deux labels sont
   **quasiment le même signal** dans les données. Un des deux est probablement redondant.
3. Rappel 0,99 pour précision 0,74 sur les deux : le comportement est « ratisser large », ce
   qui est cohérent avec la priorité métier mais génère **~26 % de faux positifs**.

**Taux de revue humaine simulé**

| Seuil | % en revue |
|---|---|
| 0,50 | **9,8 %** |
| 0,60 | 60,8 % |
| **0,65** | **100 %** |
| 0,70 – 0,80 | 100 % |

Conclusion sans ambiguïté : **la distribution de `confidence_globale` est concentrée entre 0,50
et 0,65**. Le seuil ne peut pas être réglé en dehors de cette fenêtre étroite — le levier
« ajuster le seuil de revue » est **inutilisable** en l'état. Il faut d'abord **calibrer** le
score de confiance.

### 9.3 Ce que l'évaluation ne mesure pas

- Aucune **matrice de confusion niv.2** ni analyse d'erreur intra-parent.
- Aucun **intervalle de confiance / test de significativité** sur les métriques.
- Aucune **évaluation par source** (MDTC vs Mopinion) — alors que les deux ont des schémas et
  probablement des styles rédactionnels très différents.
- Aucune évaluation de la **latence / du débit** : le critère DoD « lot de 11 000 en < 1 h »
  **n'a jamais été mesuré** (jalon T2 déclaré « en cours » dans `PLAN_V3.md` et `PASSATION.md`).
- Aucun **suivi de drift** ni comparaison inter-versions.
- Aucune mesure de la **qualité de l'anonymisation** (rappel du masquage PII).
- Les **corrections de la revue humaine ne sont pas rebouclées** dans l'entraînement : elles
  sont stockées et exportables, mais aucun mécanisme n'existe pour en faire du réapprentissage.

---

## 10. Multi-moteur : CamemBERT, stub, LLM locaux, Claude

L'architecture a évolué vers un **système multi-moteur** (V4 puis V5). C'est un acquis majeur
et **directement réutilisable** pour introduire un nouveau modèle.

### 10.1 Interface commune des prédicteurs

Tout moteur doit exposer exactement :

```python
anonymizer, cleaner, batch_size, signal_thresholds, sentiment_labels
predict_cleaned_batch(cleaned: list[str], satisfactions: list) -> list[dict]
# + LLM uniquement (cascade V5) :
refine_cleaned_batch(cleaned, sats, proposals) -> list[dict]
```

Le **contrat de sortie est le dict de `build_output()`** — identique quel que soit le moteur.
Dispatch dans `app/worker/classifiers.py → get_predictor(active_model, cfg)` sur
`active_model.kind`.

### 10.2 Les moteurs implémentés

| `kind` | Module | Nature | Usage |
|---|---|---|---|
| `real` | `src/inference/predictor.py` | CamemBERT fine-tuné, ONNX int8 | **production** |
| `stub` | `app/worker/classifiers.py` | ~20 règles mots-clés, torch-free | démo / recettes / app démontrable sans modèle |
| `lmstudio` | `app/worker/lmstudio_predictor.py` | LLM local (API compatible OpenAI, `host.docker.internal:1234`) | production possible, désactivé par défaut |
| `ollama` | `app/worker/ollama_predictor.py` | LLM local via Ollama (`:11434`) | variante du précédent |
| `claude` | `app/worker/claude_predictor.py` | API Anthropic `/v1/messages`, sortie contrainte par *tool use* | **comparaison / test uniquement — refus serveur en production** |

**Logique LLM mutualisée** dans `app/worker/llm_common.py` : construction du prompt proposeur
(`build_llm_prompt`) et raffineur (`build_refiner_prompt`), **taxonomie injectée dans le
prompt** (donc **zéro réentraînement pour faire évoluer le référentiel** — argument clé des
moteurs LLM), `map_llm_response()` (mapping + revalidation), garde-fous, normalisation. Seul le
transport HTTP est spécifique à chaque moteur. Prompts **versionnés** (`prompt_version`).

### 10.3 Garde-fous LLM

- Texte envoyé **déjà anonymisé et nettoyé** — aucun brut ne sort du pipeline.
- Sortie **contrainte par schéma JSON** (`response_format: json_schema`) ou **tool use**
  (Claude), **puis revalidée contre la taxonomie** : appariement tolérant (casse, accents,
  espaces → libellé canonique), **jamais de devinette**, dédoublonnage des couples.
- Repli **`Autre / Non classé`** : sentinelle **propre au moteur**, **volontairement NON
  ajoutée à la taxonomie partagée** (sinon l'espace de 20 labels de CamemBERT serait décalé).
- **Plafonds de confiance déterministes** : couple hors taxonomie → repli + revue, confiance
  **≤ 0,40** ; JSON hors-forme → repli + revue, **≤ 0,30** ; sentiment invalide → Neutre +
  revue ; deux thèmes au sentiment divergent (dont Négatif) → revue.
- **Échec propre** : LLM injoignable → le lot échoue, **aucun repli silencieux** vers CamemBERT.
- `enabled: false` par défaut → un poste sans LLM se comporte exactement comme avant.
- **Claude est exclu de la production côté serveur** (refus 400 à l'activation *et* à la
  création de lot), la clé vit uniquement dans `.env`.

### 10.4 Cascade et comparaison (V5)

- **Cascade** : moteur *proposeur* → moteur *raffineur* LLM, opt-in par lot
  (`batches.refiner_label`). Si `NULL`, pipeline strictement identique à V4. **Désaccord mesuré
  sur `theme1_niv1` uniquement → revue humaine forcée** ; la sortie du raffineur fait foi ; les
  deux prédictions sont conservées (`engine_predictions`).
- **Comparaison** : rejoue un échantillon d'un lot (défaut 50, max 200) sur 2–3 moteurs, avec
  **juge LLM aveuglé** (« A »/« B », ordre permuté aléatoirement, appelé uniquement sur les
  paires divergentes). Mode dégradé sans clé : métriques d'accord objectives, distribution de
  confiance, latence. Admin only, tracé à l'audit.
- **Aucun objectif de perf « 11k < 1 h »** dès qu'un LLM est dans la chaîne (cascade ≈ 2× le
  moteur le plus lent).

> ⚠️ **Dette documentaire.** `PASSATION.md` décrit l'état du projet comme « V1 + V2 + V3 » et ne
> mentionne ni V4 ni V5, alors que le code contient les cinq moteurs et que l'historique git
> montre les lots **C1 à C6 de V5 tous mergés** (`recette_v5` → 112/112). `SPEC_V5` se présente
> encore comme « projet à valider PO » avec une DoD entièrement décochée. **La documentation de
> passation est en retard d'environ deux versions sur le code.**

---

## 11. Contrat d'intégration applicatif (annexe app)

Le nouveau modèle devra s'insérer dans cet existant. Synthèse de ce qui le contraint.

### 11.1 Architecture

5 services Docker Compose (`linux/arm64`), seul `web` exposé, **sur `127.0.0.1` uniquement** :

```
navigateur (localhost:8080)
   └─ [web] nginx : build React + proxy /api (CSP stricte, X-Frame-Options DENY)
        ├─ [api] FastAPI/uvicorn — SANS torch (démarrage léger) : auth, RBAC, lots, KPI, admin
        │     └─ [db] PostgreSQL 16
        └─ [redis] file RQ ← [worker] RQ + moteur ML (importe src/)
                                 volumes : models (RO) · uploads · output
                          Aucun trafic réseau sortant.
```

Package partagé **`app/common`** (engine SQLAlchemy + ORM) importé par `api` **et** `worker`
→ schéma unique, pas de duplication. Le worker garde les modèles **chargés à chaud**, **un seul
job lourd concurrent**.

### 11.2 Contrat de persistance

Table `results` (`app/common/models/result.py`) : mapping 1:1 du contrat de sortie, plus
`corrected`, `reviewed`, `reviewed_by`, `reviewed_at` et **`original_columns` (JSON)** qui
stocke les colonnes du fichier source pour reconstituer le CSV enrichi.

**RGPD** : seul `verbatim_analyse` (anonymisé) est en base ; le brut ne vit que dans le volume
`uploads`, soumis à purge. Rétention **13 mois** par défaut, purge auto au démarrage du worker
+ purge manuelle admin.

Autres tables : `users`, `batches`, `corrections`, `model_versions`, `audit_log`, `app_config`,
`taxonomy_entries`, `engine_predictions`, `comparison_runs`, `judge_verdicts`.
**9 migrations Alembic** (`0001` → `0009`).

### 11.3 Contraintes d'exploitation

| Contrainte | Valeur |
|---|---|
| Matériel | laptop macOS Apple Silicon, **CPU seul**, ≥ 16 Go RAM / 4 cœurs (Docker : 8 Go / 4 cœurs) |
| Réseau | **hors ligne strict** après installation ; aucune télémétrie |
| Auth | argon2, cookie httpOnly, ≥ 12 caractères, verrouillage après 5 échecs, **RBAC côté API** |
| Rôles | Analyste / Admin (le data scientist est **hors application**) |
| Entrée | `.xlsx` uniquement, 50 Mo max, validation des colonnes avant traitement |
| Perf UI | écran/dashboard < 3 s, recherche/filtre < 2 s sur 11k, lancement de lot en ≤ 3 clics |
| Perf lot | **11 000 verbatims < 1 h** (DoD, **jamais mesuré**) |
| Transmission | `scripts/package_app.sh` / `restore_app.sh` (images + dump PG + volumes + manifeste) |
| Recettes | `recette_v1` 48/48, `recette_v3` 13/13, `recette_v4` 50/50, `recette_v5` 112/112 — toutes **torch-free, SQLite, moteur stub** |

**12 garde-fous « jamais »** du cahier des charges, dont les plus contraignants pour le modèle :
jamais de classe hors taxonomie ni de couple invalide ; jamais de réentraînement automatique en
production ; jamais présenter une prédiction comme validée (toujours afficher confiance +
statut auto/en revue/corrigé) ; jamais bloquer l'UI pendant un traitement long.

---

## 12. Configuration — inventaire des paramètres

`config/config.yaml` est la **source unique** : « aucun nombre magique ne doit être codé en dur
dans le code source ». Récapitulatif des valeurs actives.

```yaml
model:      base_model camembert-base · max_length 256 · batch 16/32 · epochs 5
            lr 2e-5 · warmup 0.10 · weight_decay 0.01 · seed 42 · patience 3 · device auto

thresholds: classification_niv1 0.35      # seuil sigmoïde niv.1
            classification_niv2 0.40      # ⚠️ DÉCLARÉ MAIS NON UTILISÉ (argmax masqué)
            signal_rupture 0.60           # ⚠️ écrasé par le calibrage sur val (→ 0.95)
            signal_churn 0.50 · signal_insatisfaction 0.50
            revue_humaine 0.50            # ⚠️ CDC spécifie 0.70
            max_themes 2

signals:    pooling mean · class_weight balanced · max_iter 2000
            insatisfaction_score_max 3 · rupture_recall_priority true

sentiment:  labels [Négatif, Neutre, Positif] · use_satisfaction_prefix true

dataset:    70/15/15 · stratify_on theme1_niv1
            rare_class_threshold_warn 30 · rare_class_threshold_weight 50

cleaning:   lowercase true · remove_emojis true · NFKC · min_tokens 5 · max_tokens 512

anonymization: enabled true · spacy fr_core_news_sm
               entities [PER, EMAIL, PHONE, ORDER_ID] → [NOM] [EMAIL] [TEL] [COMMANDE]

onnx:       enabled true · quantize_int8 true · use_for_inference true

smoke_test: sample_size 400 · epochs 1 · max_length 64

lmstudio / claude / orchestration / comparison : cf. §10
```

**Trois incohérences à noter** : `classification_niv2` est déclaré mais jamais lu (l'inférence
fait un argmax masqué sans seuil) ; `signal_rupture: 0.60` est systématiquement écrasé par le
calibrage sur validation ; `revue_humaine: 0.50` diverge du 0,70 contractuel.

---

## 13. Limites, dettes et angles morts du modèle actuel

Synthèse — c'est la matière première du cadrage du nouveau modèle.

### 13.1 Qualité du modèle

| # | Constat | Gravité |
|---|---|---|
| L1 | **F1-macro niv.1 = 0,564 vs cible 0,70** — critère de succès non atteint | 🔴 |
| L2 | `Suivi de commande et livraison` agit en **thème aspirateur** ; `Click & Collect` y est absorbé dans 45 cas sur 62 → **frontières du référentiel niv.1 mal définies** | 🔴 |
| L3 | **Sentiment faible** (accuracy 0,641), classe **Neutre à F1 0,360** | 🔴 |
| L4 | **`confidence_globale` non calibrée** : moyenne de 3 échelles incomparables, distribution écrasée entre 0,50 et 0,65 → **le seuil de revue est inréglable** (0,65 ⇒ 100 % en revue) | 🔴 |
| L5 | `signal_rupture` **non évaluable** (1 positif en test, 0,41 % dans les données) | 🟠 |
| L6 | `churn` et `insatisfaction` **quasi redondants** (métriques identiques à 3 décimales) | 🟠 |
| L7 | Seuil multi-label 0,35 **mal calibré** : top-1 accuracy 0,83 mais F1-micro 0,48 → sur-activation de thèmes secondaires | 🟠 |
| L8 | Le référentiel est **conçu pour les irritants** : un seul sous-thème positif (`Facile`, F1 0,154) — les retours positifs sont mal traités | 🟠 |
| L9 | **Aucune évaluation par source** (MDTC vs Mopinion) alors que les schémas et styles diffèrent | 🟠 |
| L10 | `lowercase: true` sur un modèle **cased**, destruction des majuscules d'intensité — gain potentiel gratuit | 🟡 |
| L11 | **Aucune calibration probabiliste** (Platt / isotonique / température) nulle part | 🟡 |
| L12 | Pas de matrice de confusion niv.2, pas d'intervalles de confiance | 🟡 |

### 13.2 Données

| # | Constat |
|---|---|
| D1 | **Le jeu d'entraînement est très probablement synthétique ou fortement rééquilibré** (équilibre parfait des 20 thèmes et des 3 sentiments, 99,6 % mono-thème, 0 email / 0 téléphone / 0 n° de commande sur 7 000 verbatims e-commerce). Les métriques ne sont **pas transposables** en production. |
| D2 | **28 verbatims bi-thèmes seulement** : la capacité multi-label n'est en pratique **pas entraînée** |
| D3 | 2 sous-thèmes sous le seuil de 50 exemples (`Problème de remboursement` 34, `Erreur de prix` 31) |
| D4 | **Les corrections de la revue humaine ne sont jamais rebouclées** en entraînement (stockées et exportables, mais aucun mécanisme de réapprentissage) |
| D5 | **Contrainte d'unicité globale des libellés niv.2** : toute évolution du référentiel doit la respecter ou refondre l'encodage vers une clé composite |
| D6 | La table `taxonomy_entries` (nouveaux thèmes saisis en revue) peut **diverger du JSON**, source de vérité du modèle |
| D7 | Le sentiment est annoté **au niveau du verbatim**, pas du thème → impossible de porter deux sentiments divergents |

### 13.3 Technique / exploitation

| # | Constat |
|---|---|
| T1 | **4 passes transformer par verbatim** (niv.1, niv.2, sentiment, embeddings signaux) — goulot d'étranglement du débit |
| T2 | **`EmbeddingExtractor` non exporté en ONNX** → l'inférence des signaux force PyTorch |
| T3 | **Quantization ciblée `avx2` (x86)** alors que le poste est Apple Silicon (arm64) — gain non mesuré |
| T4 | **Le DoD « 11 000 verbatims < 1 h » n'a jamais été mesuré** (jalon T2 « en cours ») |
| T5 | L'anonymisation **échoue en silence sur les noms** si spaCy est absent (mode dégradé regex) |
| T6 | Aucune mesure du **rappel de l'anonymisation** |
| T7 | Aucune détection de **drift**, aucune comparaison inter-versions automatisée |
| T8 | L'entraînement exige **internet une fois** (rupture ponctuelle de l'offline) |
| T9 | `theme2_score_confiance = ""` vs `theme1_score_confiance = 0.0` — incohérence de typage |
| T10 | Toutes les recettes tournent sur le **moteur stub** : elles valident la plomberie, **jamais la qualité du modèle** |
| T11 | **Documentation de passation en retard de ~2 versions** sur le code (V4/V5 absentes de `PASSATION.md`) |
| T12 | **Mono-poste = point de défaillance unique** ; sauvegardes manuelles ; licence Docker Desktop payante |
| T13 | Confiance LLM **auto-déclarée non calibrée** (seulement plafonnée par règles) |

---

## 14. Points de décision pour le nouveau modèle

Questions à trancher avec Cultura avant tout développement. Elles structurent le découpage en
lots et sont reprises par l'agent Product Owner (`.claude/agents/po-verbatim-ml.md`).

**A. Données**
Que contiennent réellement les nouveaux fichiers (schéma, volume, période, sources) ? Sont-ils
**labellisés** ? Par qui, avec quel référentiel, avec quel accord inter-annotateurs ?
L'historique de 7 000 verbatims est-il conservé, remplacé, ou fusionné ? A-t-on enfin un
échantillon **représentatif de la production** (déséquilibre réel, multi-thématique réelle,
PII réelles) ?

**B. Référentiel**
Le référentiel 20/67 évolue-t-il ? Les frontières poreuses (`Suivi de commande` /
`Click & Collect` / `Disponibilité & Stock` / `Annulation`) sont-elles refondues ? Le
référentiel doit-il couvrir les **retours positifs** ou rester centré sur les irritants ?
Contrainte d'unicité globale des niv.2 : maintenue, ou bascule vers une clé composite ?

**C. Comportements attendus (« nouveaux comportements du modèle »)**
Que faut-il changer exactement — plus de 2 thèmes ? un sentiment **par thème** ? une sortie
« hors sujet / non classable » ? de nouveaux signaux ? de l'extraction (produit, magasin,
motif) ? de la synthèse/regroupement de verbatims ? de la détection d'émergences / drift ?

**D. Confiance et revue humaine**
La confiance doit-elle être **calibrée** (objectif : seuil réglable, taux de revue pilotable) ?
Quel taux de revue le métier accepte-t-il (aujourd'hui 9,8 % à 0,50, 100 % dès 0,65) ?
Quel arbitrage précision / rappel par signal ?

**E. Architecture cible**
On garde le CamemBERT fine-tuné, on passe à un **LLM local** (agilité taxonomie, zéro
réentraînement — déjà branché en V4), à une **cascade** (déjà branchée en V5), ou à un modèle
plus récent (embeddings + tête légère, encodeur français plus récent) ? Contrainte offline/CPU
maintenue ou assouplie (GPU, API) ?

**F. Objectifs chiffrés**
Quelles cibles de F1 par niveau ? Quelle contrainte de débit (le « 11k < 1 h » reste-t-il
valable si un LLM est dans la chaîne — il ne l'est pas) ? Quel budget d'entraînement (temps,
matériel) ?

**G. Boucle d'amélioration**
Les corrections de la revue humaine doivent-elles alimenter le réentraînement ? Avec quelle
cadence, quelle gouvernance, quel MLOps depuis l'UI (prévu en « V2 » de la trajectoire) ?

**H. Non-régression**
Le contrat de sortie (`OUTPUT_COLUMNS`), la base, les exports et le front peuvent-ils évoluer,
ou le nouveau modèle doit-il s'y conformer ? Quel plan de comparaison ancien / nouveau modèle
(la **page Comparaison V5 avec juge aveuglé existe déjà** et peut servir de dispositif de
recette).

---

## 15. Cartographie des fichiers

**Moteur ML — `src/` (2 849 lignes de Python)**

| Fichier | L. | Rôle |
|---|---|---|
| `utils/config.py` | 104 | chargement `config.yaml`, `resolve_path`, `resolve_device`, `set_seed` |
| `utils/taxonomy.py` | 136 | **référentiel + contrainte hiérarchique** (`hierarchy_mask`, `best_niv2_for_niv1`) |
| `utils/features.py` | 46 | `sentiment_input()` — préfixe satisfaction (train ↔ inférence) |
| `preprocessing/loader.py` | 191 | lecture Excel MDTC / Mopinion / historique → `__source__`, `__text_raw__`, `__satisfaction__` |
| `preprocessing/anonymizer.py` | 177 | regex (EMAIL/TEL/COMMANDE) + NER spaCy (PER) + stoplist |
| `preprocessing/cleaner.py` | 90 | NFKC, emojis, minuscules, espaces, filtres de longueur |
| `modeling/architecture.py` | 330 | têtes HF, versioning `CURRENT`, backends Torch/ONNX, `EmbeddingExtractor`, export int8 |
| `training/prepare_dataset.py` | 307 | anonymisation → nettoyage → split stratifié → poids → artefacts ; `ProcessedDataset` |
| `training/dataset.py` | 87 | `EncodedDataset` (tokenisation, tenseurs) |
| `training/trainer.py` | 168 | boucle générique : AdamW, warmup, pertes pondérées, early stopping, logs |
| `training/train_classifier.py` | 148 | `train_niv1` (multi-label) + `train_niv2` (multi-classes) |
| `training/train_sentiment.py` | 88 | sentiment 3 classes avec préfixe satisfaction |
| `training/train_signals.py` | 164 | 3 LogReg sur embeddings gelés + calibrage du seuil de rupture |
| `inference/predictor.py` | 278 | **`build_output` (décision pure)** + `VerbatimPredictor` (orchestration) |
| `inference/batch_processor.py` | 121 | traitement DataFrame, progression, repli unitaire |
| `inference/human_review_queue.py` | 35 | file de revue |
| `evaluation/evaluate.py` | 238 | toutes les métriques + heatmap ASCII → `eval_report.json` |
| `output/exporter.py` | 39 | export CSV/XLSX |

**Scripts** — `setup_models.py` (téléchargement des poids) · `run_training.py` (orchestrateur
complet) · `validate_pipeline.py` (validation torch-free) · `make_demo_data.py` ·
`run_monthly_batch.py` · `package_app.sh` / `restore_app.sh`

**Application** — `app/api/` (14 modules de routes, 9 migrations Alembic) ·
`app/worker/` (13 modules : `tasks.py`, `classifiers.py`, `model_registry.py`, `llm_common.py`,
`lmstudio_predictor.py`, `ollama_predictor.py`, `claude_predictor.py`, `comparison.py`) ·
`app/common/` (14 modèles ORM + `retention.py`) · `app/web/` (React 18/TS, design system maison)
· `app/tests/` (recettes V1/V3/V4/V5, torch-free)

**Données** — `data/raw/` (3 fichiers sources + taxonomie) · `data/models/` (camembert-base +
4 modèles versionnés) · `data/processed/` (dataset.csv, encoders, stats, training_logs,
eval_report) · `data/{uploads,output,demo,logs}/`

**Documentation** — `docs/` : `CAHIER_DES_CHARGES.md` (v0.1, brouillon), `PLAN_DEVELOPPEMENT_V1.md`,
`PLAN_V2_DESIGN.md`, `PLAN_V3.md`, `SPEC_V4_LMSTUDIO.md`, `SPEC_V5_MULTI_MOTEUR.md`,
`GUIDE_ENTRAINEMENT.md`, `GUIDE_UTILISATEUR.md`, `EXPLOITATION.md`, `TRANSMISSION.md`,
`TRANSMISSION_GITHUB.md`, `RECETTE_V1.md`, `CHARTE_UI_V2.md`, `SUIVI_LOTS.md`, `PASSATION.md`

**Notebooks** — `01_exploration.ipynb`, `02_training_demo.ipynb`, `03_inference_demo.ipynb`

---

### Sources de ce document

Code lu sur `main` @ `95cddf8` : `src/**`, `app/worker/**`, `app/common/models/**`,
`config/config.yaml`, `scripts/**`.
Artefacts mesurés : `data/processed/eval_report.json`, `data/processed/dataset_stats.json`,
`data/raw/taxonomy_cultura_poc.json`, `data/raw/historique_labels_poc.xlsx`.
Documentation : `docs/CAHIER_DES_CHARGES.md`, `docs/GUIDE_ENTRAINEMENT.md`, `docs/PLAN_V3.md`,
`docs/SPEC_V4_LMSTUDIO.md`, `docs/SPEC_V5_MULTI_MOTEUR.md`, `docs/PASSATION.md`, `README.md`.

*Projet interne Cultura / eXalt — usage confidentiel.*
