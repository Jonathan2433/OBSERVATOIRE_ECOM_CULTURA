# Plan V3 — Finalisation « POC avancée »

> **But de la V3** : amener l'application à l'état de **POC avancée définitivement validée** :
> (1) le **moteur ML CamemBERT** prouvé de bout en bout, (2) l'app **transmissible**
> d'un poste à l'autre **sans perdre l'historique**, (3) des traitements **robustes**,
> (4) l'**exploitation & la passation** outillées.

Réf. : [CAHIER_DES_CHARGES.md](CAHIER_DES_CHARGES.md) (DoD §11, garde-fous §10).
Cadence inchangée : **1 lot = 1 branche `v3/N-nom` = 1 porte de validation PO**, merge `--no-ff`.

**Garde-fous V3 (non négociables)** : offline strict (aucune dépendance/CDN), **0 PII en base**,
prédiction toujours contrainte à la taxonomie, et **recette V1 `recette_v1.py` toujours 48/48**
(non-régression) à chaque lot.

---

## Périmètre validé

| Pilier | Sujet | Lots |
|---|---|---|
| A | Valider le moteur ML CamemBERT (entraînement → éval → ONNX → dépôt → activation → KPI réels + perf 11k) | T1, T2 |
| B | Transmission / portabilité conteneurisée avec historique préservé | P1 |
| C | Robustesse des traitements (annulation, reprise) | R1 |
| C | Exploitation & passation (KPI ops, mot de passe, dossier de passation, tag) | X1, F1 |

Chemin critique : **T1 → T2** (T2 dépend de ton run d'entraînement) ; P1, R1, X1 indépendants ; **F1** clôt.

---

## T1 — Chaîne ML fiabilisée + smoke test + jeu de démo
**Objectif** : garantir que toute la chaîne tourne, **sans attendre le run long**.
**Contenu**
- Revue/durcissement des scripts : `setup_models.py` (récupération **offline** de `camembert-base`), `prepare_dataset.py`, `run_training.py`, export **ONNX int8**, `validate_pipeline.py`.
- **Smoke test** (`--smoke`, quelques minutes) : produit des mini-modèles + `eval_report.json` factices mais **structurellement réels**, pour valider toute la chaîne.
- **Jeu de démo synthétique** (sans PII) pour entraîner/rejouer sans donnée client.
- Validation du **chemin de dépôt** : artefacts dans `data/models/` → `model_registry._detect_real` les détecte → activation UI → KPI affichés.
- **Guide d'entraînement** (`docs/GUIDE_ENTRAINEMENT.md`) : prérequis, commandes, durées, dépôt, activation.
**Acceptation** : smoke complet vert ; un modèle « réel » (issu du smoke) s'active dans l'UI et affiche ses KPI ; `recette_v1` 48/48.

## T2 — Run réel CamemBERT + performance *(jalon, run par le PO)*
**Objectif** : prouver le moteur sur les vraies données et clore le DoD #4.
**Contenu**
- **Entraînement réel** (lancé par le PO) → `eval_report` (F1 niv.1/niv.2, sentiment, signaux).
- **Export ONNX int8** + dépôt + **activation** ; KPI réels visibles avec **alertes seuils** (§6.1).
- **Mesure de performance** : lot ~11 000 verbatims **< 1 h** (relevé chiffré consigné).
- Consignation des métriques de référence (carte de version) pour les futures non-régressions.
**Acceptation** : DoD §11 #4 coché ; KPI réels au-dessus des seuils cibles (ou écarts documentés).

## P1 — Transmission : packaging & restauration avec historique
**Objectif** : déplacer l'app **hors-ligne** sur un autre poste/serveur **sans perte de données**.
**Contenu**
- Script **`scripts/package_app.sh`** : `docker save` des 3 images + **dump PostgreSQL** (`pgdata`) + archive des volumes (`models`, `uploads`, `output`) + `.env.example` → **un bundle daté** transférable (USB).
- Script **`scripts/restore_app.sh`** : `docker load` + restauration DB + volumes sur une machine vierge.
- **Vérification d'intégrité** post-restauration (comptes, lots, résultats, corrections, audit : comptages avant/après).
- Procédure documentée (dans l'exploitation) + **test de bout en bout** (état neuf → restore → historique retrouvé).
**Acceptation** : sur une cible vierge, l'app redémarre avec **l'historique identique** ; intégrité vérifiée ; offline strict respecté.

## R1 — Robustesse des traitements
**Objectif** : tenir les exigences §7.3 / §8.
**Contenu**
- **Annulation** d'un lot `pending`/`running` (API + bouton UI) → statut `canceled`, tracé audit.
- **Reprise propre** au démarrage : les jobs `running` orphelins (worker tombé) repassés en `failed` avec message clair.
- Garde-fou « un seul job lourd à la fois » revérifié.
**Acceptation** : annuler un lot fonctionne et est tracé ; après redémarrage brutal, aucun lot ne reste « en cours » fantôme.

## X1 — Exploitation & comptes
**Objectif** : compléter l'admin pour l'exploitation courante (cahier §6.4, §12 comptes).
**Contenu**
- **KPI opérationnels** (admin) : espace disque des volumes, **prochaine échéance de purge**, nombre de lots, **taux d'échec des jobs**, durée moyenne.
- **Changement de mot de passe** par l'utilisateur connecté (API + UI) ; rappel de la politique.
**Acceptation** : l'admin voit les KPI ops à jour ; un utilisateur change son mot de passe et se reconnecte ; RBAC inchangé.

## F1 — Passation & recette V3
**Objectif** : clore proprement et rendre l'app « transmissible » documentairement.
**Contenu**
- **Dossier de passation** (`docs/PASSATION.md`) : consolide install, exploitation, sauvegarde/transmission, dépôt/activation du modèle, recette, dépannage.
- **Recette V3** : étend `recette_v1` (intégrité après restauration simulée, endpoints exploitation, annulation de lot) → `recette_v3` ou section dédiée.
- **Tag `v3.0`** + note de version.
- Revue finale de la **DoD V3** (ci-dessous).
**Acceptation** : DoD V3 entièrement cochée.

---

## Definition of Done — V3

- [x] Smoke ML complet vert ; chaîne entraînement→éval→ONNX→dépôt→activation prouvée (T1).
- [ ] Modèle CamemBERT **réel** entraîné, activé, KPI réels affichés ; lot **11k < 1 h** mesuré (T2 / DoD §11 #4) — *run PO en cours*.
- [x] Bundle de transmission **produit** + script de restauration avec vérification d'intégrité (P1). *(Restauration sur 2ᵉ machine : test PO restant.)*
- [x] Annulation de lot + reprise propre des jobs interrompus (R1).
- [x] KPI opérationnels admin + changement de mot de passe (X1).
- [x] Dossier de passation + recette V3 (tag `v3.0` posé à la fusion de F1) (F1).
- [x] **Aucune régression** : `recette_v1` **48/48** + `recette_v3` **13/13**, offline strict, 0 PII, taxonomie — vérifié à chaque lot.

## Jalons
- **MV3-1** (fin T2) : moteur ML prouvé sur données réelles + perf.
- **MV3-2** (fin P1) : app transmissible avec historique.
- **MV3-3** (fin F1) : POC avancée finalisée, recettée, transmissible, taguée `v3.0`.
