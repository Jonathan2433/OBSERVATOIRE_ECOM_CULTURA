# Cultura Verbatim Classifier — POC

Classification automatique des verbatims clients e-commerce Cultura par
apprentissage automatique (NLP français, CamemBERT), 100 % local, sans GPU et
sans connexion internet à l'inférence.

---

## 1. Vue d'ensemble

Ce POC automatise l'analyse mensuelle des verbatims clients de cultura.com
(sources MDTC et Mopinion, ~11 000/mois). Pour chaque verbatim, le pipeline
produit : une **classification thématique hiérarchique multi-label** (1 à 2
thèmes, niv.1 + niv.2 contraints par un référentiel), un **sentiment par thème**
(Positif / Neutre / Négatif), trois **signaux forts** (rupture client, churn,
insatisfaction forte) et un **score de confiance** routant les cas incertains
vers une **revue humaine**. Le tout en local, sur CPU, après anonymisation des
données personnelles.

---

## 2. Prérequis

| Élément | Détail |
|---|---|
| **Python** | 3.10 ou supérieur |
| **GPU** | Non requis (entraînement et inférence sur CPU) |
| **Espace disque** | ~3 Go (CamemBERT ~450 Mo, dépendances torch/onnx, modèles fine-tunés) |
| **RAM** | 8 Go recommandés |
| **Internet** | Requis UNE seule fois (`setup_models.py`), puis tout fonctionne hors ligne |

---

## 3. Installation

> **Python 3.10 ou 3.11 recommandé** (3.12 OK). Sur 3.9 ça fonctionne grâce aux
> versions épinglées, mais 3.11 est le plus fiable. **Mettez pip à jour d'abord**
> (le pip bundlé des vieux Python provoque une résolution extrêmement lente).

```bash
# Depuis la racine du projet (cultura-verbatim-classifier/)
python -m venv .venv
source .venv/bin/activate                 # Windows : .venv\Scripts\activate
python -m pip install --upgrade pip       # IMPORTANT (résolveur moderne)

pip install --prefer-binary -r requirements.txt
python -m spacy download fr_core_news_sm  # modèle NER français (anonymisation)
```

Installations **séparées** (recommandé pour aller vite) :

```bash
# (a) Validation rapide SANS torch (~150 Mo, <2 min) : suffit pour valider la plomberie
pip install --prefer-binary -r requirements-core.txt
python -m spacy download fr_core_news_sm
python scripts/validate_pipeline.py       # bout-en-bout sur les vrais .xlsx, sans modèle

# (b) Notebooks (optionnel)
pip install --prefer-binary -r requirements-notebooks.txt
```

### Dépannage installation

| Symptôme | Cause | Solution |
|---|---|---|
| `No module named numpy` en lançant un script | venv vide (deps pas installées) | Lancer le `pip install` ci-dessus d'abord |
| pip tourne >10 min, télécharge des dizaines de versions de `notebook`/`networkx`/`spacy` | résolveur pip ancien + méta-paquet `jupyter` + spaCy non compilable en py3.9 | `Ctrl+C`, puis `python -m pip install --upgrade pip` et réinstaller avec `requirements.txt` à jour (spaCy épinglé 3.7.x, jupyter sorti du coeur) |
| `No matching distribution found for thinc>=8.3.12` | spaCy 3.8 (thinc sans wheel py3.9) | déjà corrigé : `requirements.txt` épingle `spacy>=3.7,<3.8` |
| Résolution lente malgré tout | gros graphe torch+optimum | ajouter `--prefer-binary` (évite les builds source) |

---

## 4. Premier lancement (avec internet)

Télécharge CamemBERT et le modèle spaCy **une seule fois** et les stocke en
local (`data/models/camembert-base/`). Toutes les exécutions suivantes sont
hors ligne.

```bash
python scripts/setup_models.py
```

---

## 5. Entraînement

```bash
python scripts/run_training.py            # pipeline complet (~2-4 h sur CPU)
python scripts/run_training.py --smoke    # validation rapide (sous-échantillon, ~minutes)
python scripts/run_training.py --skip-onnx   # sans export ONNX
```

Enchaîne : `prepare_dataset` → classification niv.1 + niv.2 → sentiment →
signaux → export **ONNX int8** → évaluation. Les modèles sont versionnés avec
horodatage (`data/models/<modèle>/<AAAAMMJJ_HHMMSS>/`, pointeur `CURRENT`).

> **Note sur les données simulées** : sur les 7 000 verbatims simulés, les F1
> obtenus seront plus élevés que sur données réelles (verbatims parfois répétés).
> Cela valide que le **pipeline** fonctionne, pas que le modèle est prêt pour la
> production. Les seuils cibles du cahier des charges visent les données réelles.

---

## 6. Évaluation

Le rapport (`data/processed/eval_report.json` + impression console) couvre :

- **niv.1** : F1 macro / micro / weighted, F1 par thème, top-1 accuracy,
  matrice de confusion (heatmap ASCII).
- **niv.2** : F1 macro et accuracy *à niv.1 connu* (qualité intrinsèque de la
  tête niv.2), F1 par sous-thème.
- **Précision hiérarchique** : `P(niv1 correct)`, `P(niv2 | niv1 correct)`,
  `P(niv1 correct mais niv2 faux)`, jointe.
- **Sentiment** : accuracy + F1 par classe.
- **Signaux** : précision / rappel / F1 / AUC-ROC (le rappel est prioritaire
  pour la rupture client).
- **Taux de revue humaine** selon le seuil de confiance.

Critères de réussite (données réelles) : F1-macro niv.1 ≥ 0,70 ; F1-macro niv.2
≥ 0,60 ; accuracy sentiment ≥ 0,75 ; **rappel rupture ≥ 0,80** ; taux de revue
≤ 15 % ; < 2 s / verbatim CPU.

---

## 7. Traitement mensuel

```bash
python scripts/run_monthly_batch.py \
  --mdtc        data/raw/mdtc_juillet2026.xlsx \
  --mopinion    data/raw/mopinion_juillet2026.xlsx \
  --output      data/output/classifications_juillet2026.csv \
  --seuil_revue 0.70
```

Produit le CSV enrichi **et** `revue_humaine_juillet2026.csv` (cas incertains),
puis affiche un résumé (volumes, durée, top thèmes, signaux, taux de revue).
`--seuil_revue` ajuste le seuil de confiance de routage en revue humaine.

---

## 8. Ajouter un nouveau thème (réentraînement trimestriel)

L'architecture est conçue pour qu'ajouter un **sous-thème niv.2** ne nécessite
aucune refonte du pipeline :

1. **Éditer le référentiel** `data/raw/taxonomy_cultura_poc.json` : ajouter le
   nouveau `niv2` sous le bon `niv1` (ou ajouter un nouveau bloc `niv1`).
2. **Labelliser** des exemples du nouveau sous-thème dans
   `historique_labels_poc.xlsx` (viser ≥ 50 exemples ; un avertissement est émis
   sous 30).
3. **Réentraîner** :
   ```bash
   python scripts/run_training.py
   ```
   `prepare_dataset` régénère automatiquement les encodeurs (l'ordre des classes
   dérive de la taxonomie), recalcule les pondérations de classes rares, et les
   modèles niv.1 / niv.2 sont réentraînés avec la nouvelle dimension de sortie.
4. **Vérifier** le `eval_report.json` (F1 du nouveau sous-thème) avant mise en
   production.

Aucune modification de code n'est requise : la taxonomie est l'unique source de
vérité, et la contrainte hiérarchique (masquage niv.2) s'adapte automatiquement.

---

## 9. Fichiers de sortie

Le CSV enrichi conserve **toutes les colonnes d'origine** et ajoute :

| Colonne | Type | Description |
|---|---|---|
| `verbatim_analysé` | str | Texte nettoyé et anonymisé utilisé pour la prédiction |
| `nb_themes` | int | Nombre de thèmes détectés (1 ou 2 ; 0 si non classifiable) |
| `theme1_niv1` | str | Grande thématique principale |
| `theme1_niv2` | str | Sous-thématique principale |
| `theme1_sentiment` | str | Positif / Neutre / Négatif |
| `theme1_score_confiance` | float | Score 0–1 du thème principal |
| `theme2_niv1` | str | Grande thématique secondaire (vide si `nb_themes`=1) |
| `theme2_niv2` | str | Sous-thématique secondaire (vide si `nb_themes`=1) |
| `theme2_sentiment` | str | Vide si `nb_themes`=1 |
| `theme2_score_confiance` | float | Score 0–1 du thème secondaire |
| `signal_rupture_client` | bool | Intention explicite de ne plus acheter |
| `signal_churn` | bool | Risque de churn détecté |
| `signal_insatisfaction_forte` | bool | Insatisfaction forte (note ≤ 3 + sentiment négatif) |
| `confidence_globale` | float | Score synthétique 0–1 |
| `revue_humaine_requise` | bool | True si `confidence_globale < seuil_revue` |

Un second fichier `revue_humaine_*.csv` contient les verbatims sous le seuil,
triés par confiance croissante.

---

## 10. Architecture technique

```
                         ┌─────────────────────────────┐
  mdtc_*.xlsx  ─────────▶│  loader.py                  │  (2 schémas distincts,
  mopinion_*.xlsx ──────▶│  extraction texte principal │   colonnes préservées)
                         └──────────────┬──────────────┘
                                        ▼
                         ┌─────────────────────────────┐
                         │  anonymizer.py  (PII AVANT   │  EMAIL/TEL/COMMANDE (regex)
                         │  tout traitement)            │  + NOMS (spaCy NER + stoplist)
                         └──────────────┬──────────────┘
                                        ▼
                         ┌─────────────────────────────┐
                         │  cleaner.py (NFKC, emojis,   │  filtre longueur min/max
                         │  espaces, lowercase config)  │
                         └──────────────┬──────────────┘
                                        ▼
        ┌───────────────────────────────────────────────────────────────┐
        │                    predictor.py (inférence)                    │
        │                                                                │
        │  CamemBERT niv.1 ──▶ sigmoïdes (20)  ─┐  seuil + top-2          │
        │  (multi-label, ONNX int8)             │                        │
        │                                       ▼                        │
        │  CamemBERT niv.2 ──▶ softmax (67) ─▶ MASQUAGE hiérarchique ─▶   │
        │  (multi-classes)                      (enfants du niv.1)       │
        │                                                                │
        │  CamemBERT sentiment ──▶ softmax (3)   [+préfixe satisfaction] │
        │                                                                │
        │  CamemBERT (gelé) ─▶ embeddings ─▶ 3× LogReg (rupture/churn/   │
        │                                     insatisfaction)            │
        │                                                                │
        │  ─▶ build_output(): seuils, confiance globale, revue humaine   │
        └───────────────────────────────┬───────────────────────────────┘
                                         ▼
              exporter.py (CSV enrichi)  +  human_review_queue.py (CSV revue)
```

**Choix d'architecture** (détaillés dans `train_classifier.py`,
`train_signals.py`, `modeling/architecture.py`) :
- niv.1 multi-label + niv.2 multi-classes 67 voies **masqué** par la hiérarchie
  à l'inférence → zéro sortie hors-référentiel, et réentraînement simple.
- Têtes HuggingFace **standard** → export **ONNX int8** trivial via `optimum`.
- Signaux = LogReg sur embeddings **gelés** (robuste aux ~0,4 % de positifs de
  rupture ; seuil calibré sur la validation pour viser un rappel ≥ 0,80).

---

## 11. Confidentialité & RGPD

| Garantie | Mise en œuvre |
|---|---|
| **Anonymisation avant traitement** | `anonymizer.py` masque les PII (e-mails, téléphones, n° de commande par regex ; noms propres par NER spaCy) **avant** toute tokenisation, à l'entraînement **comme** à l'inférence. |
| **Aucune PII dans les modèles** | Les textes sont anonymisés avant d'entrer dans CamemBERT ; les poids ne contiennent donc aucune donnée brute. |
| **Pas de sortie de données du SI** | Aucun appel réseau après `setup_models.py`. Inférence 100 % locale (CPU). |
| **Journalisation** | Le nombre d'entités PII masquées est journalisé à chaque lot (sans exposer les valeurs). |
| **Réversibilité nulle** | Les PII sont remplacées par des jetons neutres (`[NOM]`, `[EMAIL]`, `[TEL]`, `[COMMANDE]`) — non réversibles. |
| **Faux positifs NER maîtrisés** | Une liste de vocabulaire métier (Livraison, Colis, Site…) empêche le masquage de termes non personnels, préservant le signal thématique. |

> Les fichiers `data/processed/` et `data/output/` (qui peuvent contenir des
> verbatims) sont exclus du versionnement (`.gitignore`). En production,
> exclure également `data/raw/`.

---

## Structure du projet

```
cultura-verbatim-classifier/
├── config/config.yaml            # tous les hyperparamètres et seuils
├── data/{raw,processed,models,output}/
├── src/
│   ├── utils/        config, taxonomie (contrainte hiérarchique), features
│   ├── preprocessing/ loader, cleaner, anonymizer
│   ├── modeling/     architecture partagée train↔inférence, ONNX, embeddings
│   ├── training/     prepare_dataset, dataset, trainer, train_{classifier,sentiment,signals}
│   ├── inference/    predictor, batch_processor, human_review_queue
│   ├── evaluation/   evaluate (rapport complet)
│   └── output/       exporter (CSV enrichi)
├── scripts/          setup_models, run_training, run_monthly_batch, validate_pipeline
└── notebooks/        01_exploration, 02_training_demo, 03_inference_demo
```

## Reproductibilité

`SEED = 42` fixé partout (`random`, `numpy`, `torch`). Modèles horodatés.
Configuration entièrement externalisée dans `config/config.yaml`.
