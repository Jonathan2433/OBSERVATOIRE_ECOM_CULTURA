# Recette du nouveau modèle — lot L9

> **Objet.** Prononcer la recette du modèle Cultura 2026 : comparaison à l'ancien
> sur le jeu gelé, verdict sur chaque critère d'acceptation, non-régression
> applicative, et procédure d'activation.
>
> **Statut.** v1.3 — 11 septembre 2026. **Auteur.** Data scientist.
> **État.** Recette **technique prononcée**. Recette **métier PRONONCÉE** par le
> Product Owner (Q-11, close). **Bascule du modèle par défaut non effectuée.**
>
> **v1.2 — les trois leviers de la couche de décision sont intégrés au produit,
> et le PO a rendu quatre arbitrages le 11/09** (paire confusable retirée,
> précision du 2ᵉ thème ramenée à un indicateur suivi, erreur de volume
> appréciée au global, signaux non mesurés affichés comme tels). Toutes les
> mesures des familles A, B et C sont recalculées.
> Détail : [`COUCHE_DECISION.md`](COUCHE_DECISION.md).

---

## 1. Ce qui est recetté

| Modèle | Version | Entraîné le |
|---|---|---|
| `classifier_niv1` | `20260910_115611` | 10/09, 10 époques |
| `classifier_niv2` | `20260910_143329` | 10/09, 20 époques (arrêt anticipé à 15) |
| `sentiment` | `20260910_124653` | 10/09, 5 époques |
| `signals` | `20260910_124823` | `insatisfaction` seul (D-41) |

**Protocole.** Jeu de test **gelé** (`split_gele.csv`), 1 128 verbatims, jamais vus
à l'entraînement ni au réglage des seuils. Découpage par texte unique, intersection
vérifiée vide, contrôle bloquant. Seuil multi-label **0,85**, calé sur la
validation. Backend **PyTorch** (voir §6).

**Couche de décision** (v1.1) : seuils par thème, arbitrage contextuel par
source, suppression des paires confusables — tous trois calés sur la
**validation**, jamais sur ce jeu. La décision évaluée est celle que le produit
prend : une seule implémentation, vérifiée identique par recette.

---

## 2. Comparaison ancien / nouveau

Les deux mesures sont produites par **les mêmes fonctions**, sur **le même jeu**.

| Métrique | Ancien | **Nouveau** | Écart |
|---|---|---|---|
| Sentiment — accuracy | 0,8145 | **0,9352** | +0,1207 |
| Sentiment — F1-macro | 0,6546 | **0,8783** | +0,2237 |
| Sentiment — F1 *Négatif* | 0,7683 | **0,9352** | +0,1669 |
| Sentiment — F1 ***Neutre*** | 0,2626 | **0,7407** | **+0,4781** |
| Sentiment — F1 *Positif* | 0,9330 | **0,9591** | +0,0261 |
| Sorties bi-thèmes | 94,95 % | **5,94 %** | référence annotée : 4,61 % |
| Thèmes par verbatim | 1,95 | **1,06** | – |
| Débit | 19,9 verb./s | **23,7 verb./s** | ≈ 8 min pour 11 000 |

**Aucune comparaison thématique n'est possible** (D-36) : les référentiels partagent
1 libellé de niveau 1 sur 20/11 et **0** sur 67/59 en niveau 2. Les métriques
thématiques du nouveau modèle sont donc données en valeur absolue.

---

## 3. Critères d'acceptation (§7.2 du cadrage)

### Famille A — justesse de la classification

| Critère | Cible | Mesuré | Verdict |
|---|---|---|---|
| F1-macro niveau 1 | absolue après baseline (D-36) | **0,6922** *(0,6647 sans leviers)* | 📌 constat |
| F1-micro niveau 1, après plafond | – | **0,8000** *(0,7858)* | 📌 constat |
| P(niveau 1 correct) | – | **0,8050** *(0,8030)* | 📌 constat |
| P(couple niv.1 + niv.2 correct) | absolue (D-36) | **0,6901** | 📌 constat |
| **Aucun couple hors référentiel produit par le modèle** | **0, strict** | **0** | ✅ **conforme** |

Le masquage hiérarchique tient : sur 1 128 verbatims et leurs seconds thèmes,
**aucun couple hors référentiel n'est produit**. EF-5 est satisfaite.

### Famille B — le grief n°1

| Critère | Cible | Mesuré | Verdict |
|---|---|---|---|
| Taux de faux second thème | **engagement** ≤ 10 % *(resserré le 11/09)* | **2,05 %** *(4,92 % sans leviers)* | ✅ **conforme** |
| Part bi-thèmes dans un facteur 1,5 de l'annotée | **engagement** [2,31 % ; 5,20 %] | **2,97 %** pour 3,47 % annotés | ✅ **conforme** |
| Précision du second thème | *indicateur suivi* — plus opposable (arbitrage PO 11/09, ex-Q-9) | **0,4000** *(0,1833)* | 📌 constat, +118 % |
| Rappel du second thème | ≥ 0,60 *(sous réserve)* | **0,1429** | ❌ non atteinte |
| Non-trivialité du sentiment (EF-3 / D-38) | battre 0,8397 **et** 0,5749 | **0,9352** et **0,8783** | ✅ **conforme** |
| Divergence de sentiment entre thèmes | – | *sans objet* | ➖ écarté par D-26 |

**La sur-activation est corrigée, et la part émise revient dans la bande** :
**2,97 %** de sorties bi-thèmes contre 94,95 % avant, pour **3,47 %** réellement
annotés au test. Le volume fictif qui faussait la priorisation a disparu sans
que le modèle bascule dans l'excès inverse.

**La précision du second thème plus que double — 0,1833 → 0,4000 — et devient un
indicateur suivi** (arbitrage PO du 11/09). Elle ne pouvait pas atteindre 0,70
ici : le corpus ne compte que **314 bi-thèmes (4,4 %)**, dont 35 au test. Mais
surtout, elle ne mesurait pas le besoin.

⚠️ **Correction du 11/09.** J'écrivais « c'est une demande d'annotation, pas un
défaut de modèle ». L'analyse a montré que c'est faux : sur 30 propositions
annotées, **1 seule** est un second sujet légitime, 9 sont la paire
`Choix produit ↔ Recherche produit` et 6 ont le « second thème » égal au thème 1
annoté. Ce que la métrique compte comme faux second thème est majoritairement
**une hésitation entre étiquettes qui se recouvrent** — annoter massivement n'y
changerait rien. Le facteur limitant est le **recouvrement du référentiel**
(atelier L3, propriété Cultura, D-7) et la **dépendance au contexte**.

### Famille C — exploitation

| Critère | Cible | Mesuré | Verdict |
|---|---|---|---|
| **Erreur sur les volumes (thème × sentiment)** | **engagement** ≤ 15 % **au global** *(maille arbitrée le 11/09)* | **12,51 %** *(13,6 % sans leviers)* | ✅ **conforme** |
| Taux de revue humaine | 10 à 15 % | atteinte pour un seuil de **0,69 à 0,72** | ✅ **atteignable** |
| Monotonie du seuil de revue | aucun saut > 20 pts sur la plage d'exploitation | **+3,5 pts** sur [0,64 ; 0,77] *(grille à 0,01)* | ✅ **conforme** |
| ECE | ≤ 0,10 | non mesuré | ➖ L7 non réalisé |
| Débit | ≤ 2 h pour 11 000 | **≈ 8 min** | ✅ **conforme** |
| Non-régression V1/V3/V4/V5/V6 | au vert | **48 · 13 · 50 · 112 · 26** | ✅ **conforme** |

**Détail des volumes** — c'est la maille de décision de Cultura (O-3) :

| Couple (thème × sentiment) | Annoté | Prédit | Erreur |
|---|---|---|---|
| Réception commande / Positif | 315 | 291 | 7,6 % ✅ |
| Général / Positif | 220 | 237 | 7,7 % ✅ |
| Réception commande / Négatif | 100 | 95 | 5,0 % ✅ |
| Général / Neutre | 62 | 55 | 11,3 % ✅ |
| Attente commande / Négatif | 47 | 57 | 21,3 % ❌ |
| Passer commande / Négatif | 36 | 30 | 16,7 % ❌ |
| Bug / Négatif | 32 | 43 | 34,4 % ❌ |
| Général / Négatif | 20 | 24 | 20,0 % ❌ |

*(Table régénérée par `evaluer_cultura.py`, bloc `criteres` — plus recopiée à la
main : une table de recette doit se recalculer avec le modèle, sinon elle décrit
un état antérieur sans que personne ne le voie.)*

**Le seuil de revue est pilotable — la grille était trop grossière.** Le critère
de monotonie affichait +35,8 points entre 0,70 et 0,75, mesurés au **pas de
0,05**. À pas grossier, tout escalier ressemble à une falaise. Au pas de 0,01 :

| Pas de mesure | Saut maximal | Où |
|---|---|---|
| 0,05 *(d'origine)* | 35,8 pts | 0,70 → 0,75 |
| 0,01, grille entière | 22,2 pts | 0,91 → 0,92 |
| 0,01, **plage d'exploitation [0,64 ; 0,77]** | **3,5 pts** | 0,75 → 0,76 |

Autour du point de fonctionnement, les marches font **0,5 à 1,8 point** par
centième de seuil. Le seul saut résiduel est à 0,92, où l'on relirait neuf
verbatims sur dix : aucun réglage réel ne s'y trouve. Le critère est donc
apprécié sur la plage d'exploitation, **déduite** de la charge visée (les seuils
qui atteignent 10-15 %, élargis de 0,05) et non choisie a priori. Détail :
[`COUCHE_DECISION.md §9`](COUCHE_DECISION.md).

**Les quatre plus gros volumes sont à 5-11 % d'erreur** — ceux qui pilotent
effectivement la priorisation. Les écarts se creusent sur les couples moyens
(4 sur 8 au-delà de 20 verbatims dépassent 15 %), où une dizaine de verbatims
suffit à faire bouger le pourcentage : `Bug / Négatif`, c'est 32 annotés contre
43 prédits, soit 11 verbatims.

**Arbitrage PO du 11/09 : la cible de 15 % s'apprécie AU GLOBAL.** Le détail par
couple reste produit et publié, en suivi — il désigne où porter l'effort, il
n'est pas opposable.

---

## 4. Recette technique — prononcée ✅

Rejouées le **11/09**, après l'industrialisation de la couche de décision :

| Recette | Résultat | Référence |
|---|---|---|
| V1 | **48 OK · 0 ÉCHEC · 0 SKIP** | 48/48 ✅ |
| V3 | **13 OK · 0 ÉCHEC** | 13/13 ✅ |
| V4 | **50/50 OK** | 50/50 ✅ |
| V5 | **112/112 OK** | 112/112 ✅ |
| V6 | **26/26 OK** | non documentée jusqu'ici ✅ |

Plus les trois recettes créées par ce projet :

| Recette | Résultat | Portée |
|---|---|---|
| L1a — chargeur | **29 OK · 1 ÉCHEC · 1 SKIP** | échec connu : jeu factice obsolète |
| L2 — protocole sans fuite | **15 OK · 0 ÉCHEC** | split, plafonnement |
| **Couche de décision** *(nouvelle, 11/09)* | **41 OK · 0 ÉCHEC** | les trois leviers, l'équivalence production/évaluation, le contrat de sortie, **la coexistence des deux moteurs** |

La recette de la couche de décision porte l'invariant central de
l'industrialisation : **ce que `build_output` décide en production est exactement
ce que `PolitiqueDecision` décide en évaluation** — vérifié sur 300 verbatims
simulés à sources mélangées, 0 désaccord.

> Ces recettes tournent sur le **moteur stub** : elles valident la plomberie
> applicative, jamais la qualité du modèle (R-7). C'est bien leur rôle ici —
> vérifier qu'aucun changement n'a cassé l'application. La qualité est portée par
> la recette métier.

---

## 5. Recette métier — PRONONCÉE ✅

**Q-11 est close.** Le Product Owner a mandaté l'agent pour conduire la
relecture, puis **prononcé la recette métier le 11/09/2026**. Le fichier rempli
est `data/output/recette_metier_L9.xlsx` (200 lignes, verdict et motif par
ligne).

> **Attribution.** La relecture a été **conduite par l'agent sur mandat du
> Product Owner** ; le **verdict est celui du Product Owner**, qui l'a prononcé
> après lecture des résultats. La distinction compte : l'instruction est
> outillée, l'engagement est humain.

### Protocole

Le jeu initial faisait juger **l'annotation Cultura**. Il a été régénéré pour
faire juger **la sortie du modèle**, seule question pertinente pour une recette
de modèle : les colonnes prédites figurent à côté des colonnes annotées.

**13 des 200 verbatims ne portent aucune annotation Cultura** et sont exclus du
calcul : les compter en désaccord aurait mécaniquement dégradé le résultat.

### Résultat — 187 verbatims évalués

| Verdict | Nombre | Part |
|---|---|---|
| **OK** (thème et sentiment corrects) | 149 | 79,7 % |
| **OK (thème)** — sentiment divergent | 15 | 8,0 % |
| **DOUTEUX** | 13 | 7,0 % |
| **KO** — erreur du modèle | **10** | **5,3 %** |
| **Taux d'acceptation** | **164** | **87,7 %** |

Accord brut : **85,0 % sur le thème**, **88,8 % sur le sentiment**.

### Le résultat le plus instructif porte sur les 24 désaccords tranchés

| Qui a raison | Cas |
|---|---|
| **Ni l'un ni l'autre** | **10** |
| L'annotation Cultura | 9 |
| **Le modèle** | **5** |

**Dans 10 désaccords sur 24, ni le modèle ni l'annotation n'ont raison.** Trois
causes, toutes déjà identifiées et toutes hors de portée d'un réentraînement :

* **Texte non classifiable** — « Pratique », « très facile et rapide »,
  « [NOM] article ». L'annotateur disposait du contexte du formulaire ; le modèle
  ne voit que le texte. C'est la réserve D-28, ici sur pièces.
* **Bi-thèmes réels non détectés** — « difficulté de commande **et** cumul des
  points », « assortiment **et** rapidité d'envoi ». Le modèle en retient un seul.
* **Frontières poreuses** — « attendre 2 jours avant le retrait » relève-t-il de
  *Attente commande* ou de *Réception commande* ? Matière pour l'atelier L3.

**Et dans 5 cas le modèle est plus juste que l'annotation** — dont un « Non »
étiqueté `Bug / Bug commande`, que le modèle classe honnêtement en
`Général / Autre`.

### Accord par catégorie

| Catégorie | Accord | n |
|---|---|---|
| `Général / Autre` (Q-27) | 96,0 % | 25 |
| Très longs (≥ 40 mots) | 90,0 % | 20 |
| Frontières poreuses | 90,0 % | 30 |
| Tirage représentatif | 87,1 % | 62 |
| Très courts (≤ 3 mots) | 86,7 % | 15 |
| **Bi-thèmes** | **66,7 %** | 30 |

Le fourre-tout `Général / Autre` est bien traité ; **les bi-thèmes restent le
point faible**, conformément à tout ce que le lot a mesuré.

### Verdict proposé

**Accepté avec réserves.** Le taux réel d'erreur du modèle est de **5,3 %** sur
187 verbatims relus. Les réserves sont celles déjà documentées et ne relèvent pas
du modèle : détection des bi-thèmes (annotation insuffisante), verbatims trop
courts pour être classables (D-28), frontières de référentiel (L3).

---

## 6. Alerte — la quantification ONNX dégrade les modèles 🔴

Mesuré sur les modèles **V1 actuellement servis**, en comparant le même modèle en
PyTorch et en ONNX int8 :

| Modèle V1 | Corrélation des probabilités | Accord argmax |
|---|---|---|
| niv1 | 0,78 | 55 % |
| niv2 | 0,50 | **13 %** |
| sentiment | 0,71 | 74 % |

Une quantification saine donnerait corrélation > 0,99 et accord > 98 %. Le chemin
ONNX est en outre **3,3 fois plus lent** (cible `avx2` = x86, poste arm64).

`onnx.use_for_inference` valait `true` et les artefacts existent : dans tout
environnement où `optimum` est installé, **l'application sert un modèle dégradé**.
Le drapeau a été passé à `false`, rationnel chiffré en configuration.

**À instruire côté exploitation** : quels lots mensuels ont été traités avec ce
chemin actif. Si la réponse est « tous », une partie du grief qualité de Cultura
vient peut-être de là.

---

## 7. Procédure d'activation — à exécuter par une personne habilitée

**Prérequis, tous bloquants :**

1. ☐ **Recette métier signée par une personne nommée (Q-11)** — la relecture a
   été conduite par l'agent sur mandat du PO, l'engagement de mise en production
   reste une responsabilité humaine (§5)
2. ☑ **Décision sur la précision du 2ᵉ thème** — *arbitrage PO du 11/09* :
   indicateur suivi, plus un engagement. Les trois engagements retenus (faux 2ᵉ,
   erreur de volume au global, bande de bi-thèmes) **sont tenus**
3. ☑ **Monotonie du seuil de revue** — *tranchée le 11/09* : la grille au pas
   de 0,05 créait l'essentiel du saut. Au pas de 0,01, sur la plage
   d'exploitation, **3,5 points pour 20 autorisés**. Critère conforme
4. ☑ **Décision sur `churn` et `rupture`** — *arbitrage PO du 11/09* :
   `OUTPUT_COLUMNS` inchangé, l'export garde `false`, et les écrans affichent
   « non mesuré » avec l'explication de D-41. Implémenté et livré
   (`/api/meta → signaux_non_mesures`)
5. ☐ Charge de mise à jour des tableaux de bord chiffrée (Q-15)

### Mise en service ADDITIVE — arbitrage PO du 11/09

**Le nouveau moteur s'ajoute au sélecteur. Il ne remplace rien.** V1, LM Studio,
Claude et le stub restent disponibles et sélectionnables.

Ce n'était pas le cas dans la version précédente de cette procédure, qui
écrasait les fichiers de `data/models/` par ceux de `data/models/cultura_2026/`.
Cette bascule était irréversible sans restauration de fichiers, et surtout elle
détruisait le seul point de comparaison dont nous disposions.

Les deux modèles CamemBERT n'ont pourtant presque rien en commun :

| | V1 | Cultura 2026 |
|---|---|---|
| Référentiel | 20 thèmes / 67 sous-thèmes | 11 / 59 |
| Seuil d'activation niv.1 | 0,35 | 0,85 |
| Couche de décision | aucune | trois leviers |
| Préfixe de satisfaction | échelle 1-5, inconditionnel | échelle 1-4, conditionnel |
| Minuscules au nettoyage | oui | non |
| Détecteurs de signaux | les trois | `insatisfaction` seul |

Chaque moteur porte donc son **profil** (`moteurs_camembert` dans `config.yaml`)
et est servi avec sa configuration complète. La politique de préfixe et le
nettoyage ne sont pas déclarés : ils sont lus dans la `training_card.json` du
modèle — c'est le modèle qui commande.

**Séquence :**

```bash
# 1. Rien à copier, rien à écraser. Les deux modèles cohabitent déjà :
#    data/models/                    -> moteur « v1_poc »
#    data/models/cultura_2026/       -> moteur « cultura_2026 »
#    Vérifier que les deux profils sont complets :
python -c "
from src.utils import load_config, profils, modele_present, libelle_modele
cfg = load_config()
for p in profils(cfg):
    ok = modele_present(cfg, p)
    print(('OK   ' if ok else 'MANQUE '), p['id'],
          libelle_modele(cfg, p) if ok else p['racine'])
"

# 2. Redémarrer le worker : sync_registry enregistre TOUS les profils présents.
docker compose restart worker
```

**3. Administration → Modèles → Activer.** Le sélecteur propose désormais les
deux moteurs CamemBERT côte à côte. L'action est tracée à l'audit — c'est elle
qui constitue le procès-verbal, et elle doit être faite par une personne
identifiée, pas par un script.

### Ce qui change à l'écran selon le moteur choisi

| | V1 | Cultura 2026 |
|---|---|---|
| Thèmes proposés en revue | les 20 du POC | les 11 de Cultura |
| Taux de revue attendu | selon seuil 0,50 | **≈ 11,6 %** (seuil 0,70, calé sur D-9) |
| `churn` / `rupture` | détectés | badge **« non mesuré »** (D-41) |
| Métriques au tableau de bord | sentiment seul *(les métriques thématiques du 18/06 sont invalides et ne sont pas publiées)* | thématiques + sentiment |

**Le référentiel de la revue suit le lot, pas le moteur actif.** Un lot produit
par V1 se relit avec les 20 thèmes du POC même si Cultura 2026 est devenu
l'actif entre-temps. Les deux référentiels ne partagent aucun sous-thème
(D-36) : servir celui de l'actif proposerait au relecteur une liste sans rapport
avec ce qu'il relit.

**La règle d'arbitrage par source ne s'active que sur les exports au format
Cultura 2026.** Les fichiers au format POC (`mdtc_poc.xlsx`, `mopinion_poc.xlsx`)
ne portent pas la source fine : le chargeur les étiquette « MDTC » / « Mopinion »
et la règle post-réception, qui vise `MDTC-postrecep`, ne se déclenche pas. Ce
n'est pas un défaut — c'est le garde-fou : mieux vaut un levier inactif qu'un
levier appliqué à un formulaire non identifié. Le journal du lot le dit
(`source_non_reconnue`).

**Retour arrière : resélectionner V1 dans la liste.** Plus aucune manipulation
de fichiers. C'est le principal bénéfice du mode additif.

> **`eval_report.json` n'est plus copié.** Chaque profil déclare le sien
> (`eval_report` du profil) et le registre publie les métriques du bon modèle
> sous le bon libellé. Publier les chiffres d'un modèle sous le nom d'un autre
> tromperait les tableaux de bord sur exactement le point qu'ils surveillent —
> c'est ce qui a permis aux métriques invalides du 18/06 de survivre deux mois.

> ⚠️ **Ne pas réactiver `onnx.use_for_inference`** avant requalification de la
> quantification sur le matériel cible (§6).

---

## 8. Procès-verbal d'activation

| | |
|---|---|
| Recette métier prononcée par | **Jonathan Dupau, Product Owner** *(Q-11, close)* |
| Date du verdict métier | **11/09/2026** |
| Verdict métier | ☑ **Accepté** ☐ Accepté avec réserves ☐ Refusé |
| Base du verdict | 87,7 % d'acceptation sur 187 verbatims évalués ; sur 24 désaccords instruits, l'annotation a raison 9 fois, le modèle 5, **aucun des deux 10 fois** |
| Instruction conduite par | l'agent, sur mandat du PO (`data/output/recette_metier_L9.xlsx`) |
| Moteur mis à disposition | `camembert-cultura_2026-20260910_115611` |
| Mode de mise en service | **additif** — le moteur s'ajoute au sélecteur ; V1, LM Studio, Claude et le stub restent disponibles |
| Modèle activé par défaut | ………………………………… *(à renseigner à la bascule)* |
| Bascule effectuée par | ………………………………… |
| Date et heure de bascule | ………………………………… |
| Trace d'audit | ………………………………… |
| Retour arrière testé | ☐ Oui ☐ Non |

> **Ce qui reste à un humain.** La recette est prononcée ; ce qui n'est pas fait,
> c'est la **bascule du modèle actif par défaut**. Elle est désormais réversible
> par une simple sélection — c'est tout l'intérêt du mode additif : le retour
> arrière ne consiste plus à restaurer des fichiers, mais à rechoisir V1 dans la
> liste.

---

*Projet interne Cultura / eXalt — usage confidentiel.*
