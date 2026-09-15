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
- Données d'entraînement labellisées : `data/raw/historique_labels_poc.xlsx` (fourni)
  pour la chaîne POC ; livraison Cultura sous `data/raw/cultura_2026/` pour la refonte.
- ~8 Go RAM libres ; prévoir plusieurs heures CPU pour le run complet.

> ⚠️ **`scikit-learn` est épinglé** (`==1.6.1` dans `requirements.txt`). Les détecteurs
> de signaux sont des pipelines sérialisés avec joblib : les recharger sous une autre
> version fait dire à scikit-learn lui-même *« might lead to breaking code or invalid
> results »*, sur des colonnes du contrat de sortie. **Relever cette borne exige de
> réentraîner les détecteurs** et de vérifier que leurs seuils tiennent encore.

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

> **L'export ONNX est produit mais n'est pas servi.** `onnx.use_for_inference` est
> à `false` : mesuré sur cette machine, les modèles servis via ONNX int8 ne
> s'accordent avec PyTorch que sur **55 % / 13 % / 74 %** des argmax selon la tâche,
> pour un débit **3,3× plus lent**. Les réactiver exige une requalification sur le
> matériel cible. `--skip-onnx` est donc sans conséquence sur l'inférence.

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

## 4 bis. Chaîne du modèle Cultura 2026

Chaîne dédiée, avec **découpage gelé** et **contrôle de fuite bloquant** — le
prototype avait été évalué sur un découpage où 99,6 % des textes de test se
retrouvaient à l'entraînement, et les chiffres publiés étaient donc faux.

```bash
python scripts/entrainer_cultura.py        # préparation + entraînement (découpage gelé)
python scripts/evaluer_cultura.py          # évaluation sur le jeu de test, jamais vu
python scripts/evaluer_cultura.py --sans-leviers   # le modèle nu, pour situer l'apport
python scripts/publier_eval_report.py      # rapport au format lu par les tableaux de bord
```

Outils de calibration — **toujours sur la validation, jamais sur le test** :

```bash
python scripts/courbe_seuil.py             # seuil d'activation multi-label
python scripts/calibrer_seuil_niv2.py      # seuil du niveau 2
python scripts/calibrer_regle_source.py    # marge de l'arbitrage contextuel
python scripts/ablation_leviers.py --split val   # apport de chaque levier de décision
```

Calibrer sur le jeu de test serait une fuite d'un autre genre. Les scripts le
refusent par défaut ou l'annoncent.

---

## 4 ter. Ce qu'un modèle doit embarquer

Un modèle n'est exploitable par l'application que s'il embarque **son espace de
labels**. Deux règles :

1. **`<racine>/taxonomy.json`** — le référentiel du modèle, à sa racine. C'est lui
   qui alimente les listes de la revue humaine, et c'est la seule forme qui suive le
   modèle dans les conteneurs (seul `data/models` y est monté).
2. **Un profil déclaré** dans `config.yaml → moteurs_camembert` : racine sous
   `data/models`, et les écarts au réglage global (seuil d'activation, seuil de
   revue, couche de décision, rapport d'évaluation).

```yaml
moteurs_camembert:
  - id: "cultura_2026"
    libelle: "Cultura 2026 — référentiel Cultura (11 thèmes)"
    racine: "data/models/cultura_2026"
    seuil_niv1: 0.85
    seuil_revue: 0.70
    leviers_decision: true
    eval_report: "data/processed/eval_report_cultura_2026.json"
```

La politique de préfixe et le nettoyage **ne se déclarent pas** : ils sont lus dans
la `training_card.json` du modèle. C'est le modèle qui commande — le contredire à
l'inférence dégraderait ses sorties en silence.

Vérifier qu'un dépôt est complet :

```bash
python -c "
from src.utils import load_config, profils, modele_present, libelle_modele
cfg = load_config()
for p in profils(cfg):
    ok = modele_present(cfg, p)
    print(('OK   ' if ok else 'MANQUE '), p['id'], libelle_modele(cfg, p) if ok else p['racine'])
"
```

---

## 5. Déposer & activer dans l'application

Les modèles sont lus depuis le volume monté **en lecture seule** `data/models` :

1. Vérifier que les 4 sous-dossiers sont présents et non vides (l'app les détecte
   ainsi), **et que `taxonomy.json` est à la racine du modèle** (§4 ter).
2. Redémarrer le worker pour la synchro du registre : `docker compose restart worker`
   *(la synchro tourne aussi automatiquement au démarrage).*
3. UI → **Administration → Modèles** : **activer** la nouvelle version (activation tracée à l'audit).
4. UI → **Tableaux de bord** : les **KPI réels** s'affichent, avec **alerte visuelle** si une
   métrique passe sous son seuil cible (§6.1 du cahier).

> Garde-fous : l'app ne ré-entraîne jamais en production et ne modifie jamais les
> poids (volume `:ro`). L'entraînement reste une opération CLI maîtrisée (ce guide).

**Le dépôt est additif.** Un nouveau modèle s'ajoute au sélecteur, il ne remplace
personne : les moteurs précédents restent activables, et le retour arrière est une
resélection. Une entrée de registre dont le modèle a disparu est rendue
indisponible ; si c'est le même modèle sous un libellé différent, l'activation est
reportée sur la nouvelle entrée — renommer ne change pas le modèle servi.

---

## 6. Mesurer la performance (objectif DoD)

Traiter un lot d'environ **11 000 verbatims** et relever la **durée** (visible dans
le tableau de bord du lot et le détail). Objectif : **< 1 h** (backend PyTorch, worker
chaud, `model.batch_size_inference` ajustable dans `config/config.yaml`).

Débit mesuré sur le jeu de test gelé : **≈ 21 verbatims/s**, soit ≈ 9 min pour 11 000.

---

## 7. Dépannage

| Symptôme | Cause | Solution |
|---|---|---|
| `OSError ... camembert-base` | Modèle de base non récupéré | Lancer `setup_models.py` (avec internet) |
| Entraînement très lent / OOM | Volume + RAM | Réduire `batch_size_*` ; fermer les autres applications |
| L'app reste en mode stub après dépôt | Sous-dossiers manquants/vides ou worker non redémarré | Vérifier les 4 dossiers + `docker compose restart worker` |
| Pas de KPI qualité | `eval_report.json` absent | Relancer avec l'évaluation (sans `--skip-eval`) |
| Le modèle déposé n'apparaît pas dans le sélecteur | Profil absent de `moteurs_camembert`, racine hors de `data/models`, ou sous-modèle manquant | Lancer l'inventaire des profils (§4 ter) ; le journal du worker dit lequel est ignoré et pourquoi |
| La revue propose des thèmes sans rapport | `taxonomy.json` absent de la racine du modèle : le référentiel de repli est servi | Le déposer, puis `docker compose restart api` |
| `InconsistentVersionWarning` au chargement des signaux | Version de scikit-learn différente de celle d'entraînement | Réinstaller les dépendances épinglées (`pip install -r requirements.txt`) ; ne pas ignorer l'alerte |
| Le contrôle de fuite bloque la préparation | Un même texte se retrouve dans deux découpages | C'est le garde-fou. Ne pas le contourner : il a déjà rattrapé deux mois de chiffres faux |
