# Guide d'entraînement du modèle CamemBERT

Comment passer du **stub de démonstration** au **vrai modèle** et l'activer dans
l'application. Le moteur ML (`src/`) est celui du POC ; ce guide en décrit l'usage
de bout en bout.

> **Important** : l'entraînement nécessite **torch** (CPU, plusieurs heures sur ~7k
> verbatims) et **internet une seule fois** (téléchargement de `camembert-base`).
> L'inférence dans l'app, elle, reste 100 % hors ligne.

---

## 0. Prérequis

- Python 3.11 + dépendances ML : `pip install -r requirements.txt`.
- Données d'entraînement labellisées : `data/raw/historique_labels_poc.xlsx` (fourni).
- ~8 Go RAM libres ; prévoir plusieurs heures CPU pour le run complet.

---

## 1. Récupérer les modèles de base (une fois, avec internet)

```bash
python scripts/setup_models.py
```
Télécharge et stocke **en local** : `camembert-base` (→ `data/models/camembert-base/`)
et le modèle spaCy `fr_core_news_sm` (anonymisation). Après cette étape, tout
fonctionne **hors ligne**.

---

## 2. Validation rapide SANS entraînement (torch-free)

Pour vérifier la plomberie (chargement → anonymisation → format de sortie) sans
torch, avec le **stub** :

```bash
# sur les fichiers POC
python scripts/validate_pipeline.py
# ou sur un jeu de démo synthétique (sans PII réelle)
python scripts/make_demo_data.py
python scripts/validate_pipeline.py --mdtc data/demo/mdtc_demo.xlsx --mopinion data/demo/mopinion_demo.xlsx
```
Sortie attendue : `✅ PIPELINE VALIDE` (format conforme, hiérarchie respectée, PII masquées).

---

## 3. Smoke test de l'entraînement (quelques minutes)

Valide **toute la chaîne d'entraînement** sur un sous-échantillon (modèles jouets) :

```bash
python scripts/run_training.py --smoke
```
Enchaîne : `prepare_dataset` → classifier (niv.1+niv.2) → sentiment → signaux →
export ONNX int8 → évaluation. Produit des artefacts **structurellement réels**
dans `data/models/` + `data/processed/eval_report.json`. À utiliser pour valider
le branchement **avant** le run long.

---

## 4. Entraînement réel

```bash
python scripts/run_training.py            # chaîne complète
# options : --skip-prepare, --skip-onnx, --skip-eval
```
Produit, sous `data/models/` :
`classifier_niv1/`, `classifier_niv2/`, `sentiment/`, `signals/` (+ variantes ONNX int8),
et `data/processed/eval_report.json` (F1 niv.1/niv.2, sentiment, signaux).

Déterminisme : `SEED=42` (config.yaml). Hyperparamètres et seuils : tous dans `config/config.yaml`.

---

## 5. Déposer & activer dans l'application

Les modèles sont lus depuis le volume monté **en lecture seule** `data/models` :

1. Vérifier que les 4 sous-dossiers sont présents et non vides (l'app les détecte ainsi).
2. Redémarrer le worker pour la synchro du registre : `docker compose restart worker`
   *(la synchro tourne aussi automatiquement au démarrage).*
3. UI → **Administration → Modèles** : **activer** la nouvelle version (activation tracée à l'audit).
4. UI → **Tableaux de bord** : les **KPI réels** s'affichent, avec **alerte visuelle** si une
   métrique passe sous son seuil cible (§6.1 du cahier).

> Garde-fous : l'app ne ré-entraîne jamais en production et ne modifie jamais les
> poids (volume `:ro`). L'entraînement reste une opération CLI maîtrisée (ce guide).

---

## 6. Mesurer la performance (objectif DoD)

Traiter un lot d'environ **11 000 verbatims** et relever la **durée** (visible dans
le tableau de bord du lot et le détail). Objectif : **< 1 h** (ONNX int8, worker chaud,
`model.batch_size_inference` ajustable dans `config/config.yaml`).

---

## 7. Dépannage

| Symptôme | Cause | Solution |
|---|---|---|
| `OSError ... camembert-base` | Modèle de base non récupéré | Lancer `setup_models.py` (avec internet) |
| Entraînement très lent / OOM | Volume + RAM | Réduire `batch_size_*` ; fermer les autres applications |
| L'app reste en mode stub après dépôt | Sous-dossiers manquants/vides ou worker non redémarré | Vérifier les 4 dossiers + `docker compose restart worker` |
| Pas de KPI qualité | `eval_report.json` absent | Relancer avec l'évaluation (sans `--skip-eval`) |
