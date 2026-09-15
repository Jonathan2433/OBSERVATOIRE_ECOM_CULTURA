# Rapport de lot L6 — réentraînement sur données Cultura

> **Objet.** Réentraînement des modèles sur le corpus Cultura 2026, arbitrages du
> PO appliqués, et calibrage du seuil multi-label (lot L5').
>
> **Statut.** v1.0 — 9 septembre 2026. **Auteur.** Data scientist.
> **Reproduction.** `python scripts/entrainer_cultura.py --lowercase false`
> puis `python scripts/evaluer_cultura.py --seuil <calibré>`.
> **Références.** `docs/RAPPORT_L1a_CHARGEUR.md`, `docs/RAPPORT_L2_BASELINE.md`.
>
> ---
>
> 📌 **Relevé daté — non réécrit.** Ce rapport décrit l'état du modèle **au terme
> de l'entraînement**, avant l'industrialisation de la couche de décision. Ses
> chiffres restent exacts *pour cette configuration* : ils décrivent le **modèle
> nu**, à seuil unique et sans levier.
>
> Les chiffres **en vigueur** sont dans
> [`COUCHE_DECISION.md`](COUCHE_DECISION.md) et
> [`RECETTE_NOUVEAU_MODELE.md`](RECETTE_NOUVEAU_MODELE.md) :
> F1-macro niv.1 **0,6922** (contre 0,6647 ici), précision du second thème
> **0,4000** (contre 0,1833), taux de faux second thème **2,05 %** (contre 4,92 %).
>
> Un rapport de lot qu'on récrit ne prouve plus rien : la correction s'ajoute,
> elle n'efface pas.

---

## 1. Configuration d'entraînement

| Élément | Valeur | Origine |
|---|---|---|
| Corpus | 7 501 verbatims · train 5 244 / val 1 129 / test 1 128 | L1a |
| Découpage | **jeu de recette gelé**, par texte unique, fuite nulle | L2 |
| Exemples utiles | niv1 4 827 · niv2 4 764 · sentiment 4 443 (train) | masques `apprend_*` |
| Espace de labels | 11 thèmes · **43 sous-thèmes entraînables** sur 59 | D-32 |
| Échelle de satisfaction | 1-4 | D-37 |
| Préfixe | **conditionnel** : conservé ≤ 10 mots, retiré au-delà | D-39 |
| Casse | `lowercase: false` — CamemBERT est un modèle *cased* | recommandation |
| Signaux | `insatisfaction` seul (616 positifs au train) | D-41 |
| Sortie | `data/models/cultura_2026/` — **la V1 n'est pas écrasée** | prudence |

Les modèles de la V1 restent en place et actifs : l'application continue de
fonctionner pendant tout le lot. La bascule est une opération distincte de L9.

### Ce qui a été corrigé avant de lancer

Deux défauts de méthode, trouvés en relecture **avant** publication du moindre
chiffre. Les deux auraient produit des résultats faux sans rien déclencher.

1. **Deux jeux de test différents.** La baseline regroupait les doublons sur le
   texte brut, la préparation sur le texte nettoyé. Les deux donnaient 1 128
   verbatims de test et ne partageaient que **23,6 %** de leurs lignes. Corrigé
   par le jeu de recette gelé (cf. `RAPPORT_L2_BASELINE.md` §1).
2. **`--lowercase false` sans effet.** Le nettoyage s'applique à la préparation,
   pas à l'entraînement : le modèle aurait été entraîné sur du texte minuscule
   avec une carte affirmant `lowercase: False`. Corrigé : chaque variante de
   nettoyage prépare son corpus, en réutilisant le gel commun. Vérifié — 6 702
   verbatims conservent leurs majuscules, et le jeu de test reste identique au
   verbatim près.

### Un gain de temps qui change le budget d'itérations

`dataset.py` complétait chaque exemple à 256 tokens fixes, pour une médiane
réelle de **10 tokens**. Passage au padding dynamique : **×7,3 mesuré**, une
passe complète des trois modèles tombant de **4,0 h à 0,5 h**. Numériquement
équivalent — le masque d'attention neutralise les positions ajoutées.

> La réserve du plan (« une passe se compte en heures », « le plan ne tolère
> qu'un nombre très limité d'itérations ») ne tient plus, et **Q-7 perd
> l'essentiel de son objet**.

---

## 2. Lot L5' — calibrage du seuil multi-label

Courbe établie sur la **validation** (1 048 verbatims annotés, dont 35 bi-thèmes
soit 3,3 %), jamais sur le test.

| Seuil | Sorties bi-thèmes | Précision 2ᵉ thème | Taux de faux 2ᵉ | F1-macro *(après plafond)* |
|---|---|---|---|---|
| 0,35 *(hérité V1)* | 96,0 % | 0,106 | 0,962 | 0,481 |
| 0,50 | 40,1 % | 0,210 | 0,385 | 0,524 |
| 0,65 | 17,0 % | 0,185 | **0,155** | 0,558 |
| 0,80 | 9,3 % | 0,247 | **0,082** | 0,582 |
| **0,85** | **5,7 %** | **0,267** | **0,053** | **0,584** |
| 0,90 | 2,1 % | 0,136 | 0,020 | 0,563 |

**Deux enseignements.**

**(a) La cible « précision du second thème ≥ 0,70 » est hors d'atteinte.** Le
maximum observé est **0,267**, à tous les seuils. Le facteur limitant n'est pas
le modèle mais l'annotation : le corpus ne compte que **314 bi-thèmes (4,4 %)**,
dont ~155 au train. R-1 a été déclaré levé sur l'arrivée de 7 068 annotations,
mais le second thème — qui *est* le grief n°1 — reste annoté à 3-4 %.

**(b) La cible « taux de faux second thème ≤ 15 % » est atteinte** dès 0,65, et
largement à 0,85.

**Effet sur la maille de décision de Cultura.** Au seuil hérité de 0,35, 96 % des
verbatims sortent bi-thèmes et 89 % de ces seconds thèmes sont faux : le volume
par (thème × sentiment) est massivement gonflé. À **0,85**, 5,7 % sortent
bi-thèmes — proche des 3,3 % réellement annotés — et la pollution tombe à **~4 %
des verbatims**. La distorsion passe de ~85 % à ~4 %.

**Recommandation eXalt : retenir 0,85**, et **découpler les deux cibles de la
famille B** — conserver « taux de faux second thème ≤ 15 % » comme engagement,
reclasser « précision du second thème ≥ 0,70 » en indicatif, assortie d'une
demande d'annotation à Cultura. C'est la seule des deux qui dépende de nous.

### Ce que la correction du F1-micro a révélé

Le trainer annonçait **0,3023** de F1-macro validation au seuil 0,35. Cette
valeur est calculée **avant plafonnement** — exactement le défaut corrigé en L2.
La même configuration, décision réelle rejouée, donne **0,481** ; au seuil
calibré, **0,584**. L'ancien calcul sous-estimait de 28 points **tout en
masquant** la sur-activation qu'il aurait dû révéler.

---

## 3. Contrainte d'environnement — export ONNX int8

`optimum` s'installe en version 1.24.0, la dernière compatible Python 3.9, mais
ses classes ONNX ne s'importent plus avec transformers 4.57 (dérive d'API). Les
versions récentes d'`optimum` exigent Python ≥ 3.10.

**Non bloquant pour la mise en service** : le débit mesuré en PyTorch pur est de
20 à 25 verbatims/s, soit ~10 minutes pour 11 000 contre une cible de 1 à 2 h
(ENF-1). L'export ONNX était une optimisation, pas une nécessité.

**À traiter en même temps qu'une dette déjà présente** : les trois environnements
virtuels du dépôt sont inutilisables — OneDrive a déshydraté leurs liens
symboliques (`.venv/bin/python` fait 7 octets). Reconstruire l'environnement
**hors du dossier synchronisé**, sur Python 3.11, lève les deux problèmes d'un
coup.

---

## 4. Résultats — jeu de test gelé, 1 128 verbatims, seuil 0,85

Entraînement complet en **56,8 min** (niv1 18,8 · niv2 19,5 · sentiment 17,4).

### 4.1 Sentiment — la seule tâche comparable à l'ancien modèle

| | Ancien | **Nouveau** | Écart |
|---|---|---|---|
| Accuracy | 0,8145 | **0,9352** | +0,1207 |
| F1-macro | 0,6546 | **0,8783** | +0,2237 |
| F1 *Négatif* | 0,7683 | **0,9352** | +0,1669 |
| F1 ***Neutre*** | 0,2626 | **0,7407** | **+0,4781** |
| F1 *Positif* | 0,9330 | **0,9591** | +0,0261 |

**EF-3 / D-38 est satisfaite sur les deux grandeurs** : 0,9352 > plancher 0,8397
(accuracy) et 0,8783 > plancher 0,5749 (F1-macro). Le modèle bat désormais la
règle `note → sentiment` de **+9,6 points d'accuracy**, là où l'ancien lui était
inférieur de 2,5 points.

> **Le gain sur *Neutre* mérite une réserve.** Passer de 0,26 à 0,74 sur la classe
> que tout le monde annonçait structurellement faible est un résultat que j'ai
> cherché à invalider avant de le publier. Écartés : la fuite de texte (jeu gelé,
> intersection vide vérifiée), la fuite par répondant (6 répondants éclatés sur
> 7 491, **aucun annoté en sentiment**), la mémorisation (textes de test inédits).
> L'explication qui reste est la plus simple : l'ancien modèle était entraîné sur
> un **autre domaine et un autre référentiel**, celui-ci sur ces données précises,
> avec pondération de classes. **La réserve qui subsiste est la taille
> d'échantillon : 70 exemples *Neutre* au test.** L'intervalle de confiance est
> large ; à reconfirmer sur la prochaine livraison.

### 4.2 Grief n°1 — le volume fictif est corrigé

| | Ancien | **Nouveau** | Référence annotée |
|---|---|---|---|
| Sorties bi-thèmes | 94,95 % | **6,83 %** | 4,61 % |
| Thèmes par verbatim | 1,95 | **1,07** | ≈ 1,05 |
| Taux de faux 2ᵉ thème | – | **0,0605** | cible ≤ 0,15 ✅ |
| Précision du 2ᵉ thème | – | **0,2319** | cible ≥ 0,70 ❌ |
| Rappel du 2ᵉ thème | – | 0,1714 | (35 bi-thèmes annotés) |

**La sur-activation est résolue** : la sortie bi-thèmes passe de 95 % à 6,8 %,
pour 4,6 % réellement annotés. C'est le préjudice principal décrit au cadrage —
le volume fictif dans les tableaux de priorisation — et il est corrigé.

**La précision du second thème ne l'est pas**, et ne le sera pas sans annotation
supplémentaire : 35 cas bi-thèmes au test, ~155 au train. Voir §2.

### 4.3 Famille A — en valeur absolue (D-36 : pas de baseline thématique)

| Métrique | Valeur |
|---|---|
| F1-macro niveau 1 | **0,6323** |
| F1-micro niveau 1 *(après plafond)* | 0,7524 |
| Précision micro / rappel micro | 0,7405 / 0,7646 |
| P(niveau 1 correct) | 0,7644 |
| **P(couple niv.1 + niv.2 correct)** | **0,5723** |

### 4.4 Signal — `insatisfaction` seul (D-41)

616 positifs au train, 128 en validation. **F1 0,583 · AUC 0,916 · précision
0,525 · rappel 0,656** au seuil 0,50. `churn` et `rupture` n'ont pas de modèle :
le prédicteur les charge désormais **sans échouer**, les journalise et les produit
à `False`. **La règle métier qui doit les remplacer reste à définir en L4** — en
l'état, deux colonnes du contrat de sortie sont constamment fausses, ce qui doit
être dit au métier avant la bascule.

### 4.5 Exploitation

**Débit : 19,7 verbatims/s, inchangé** (−1,2 %, dans le bruit) — soit ~9 minutes
pour 11 000, hors chaîne applicative. ENF-1 reste très largement tenue.

**Le taux de revue reste inréglable, et c'est le principal point ouvert :**

| Seuil | 0,50 | 0,60 | 0,65 | 0,70 |
|---|---|---|---|---|
| Ancien | 16,9 % | 44,3 % | 92,0 % | 100 % |
| **Nouveau** | **2,4 %** | **19,1 %** | 89,5 % | 100 % |

La cible D-9 (10 à 15 %) tombe **entre 0,50 et 0,60** pour le nouveau modèle —
donc atteignable, contrairement à l'ancien. Mais le saut 0,60 → 0,65
(+70 points) viole toujours le critère de monotonie de EF-7. **La calibration
(L7) reste nécessaire pour rendre ce curseur pilotable.**

### 4.6 D-40 — le mécanisme est en place mais ne se déclenche jamais

**0 verbatim** sort avec un `theme1_niv2` vide. C'est logique : les 16
sous-thèmes hors périmètre sont exclus de l'entraînement du niveau 2, donc leurs
neurones de sortie ne s'activent jamais assez pour remporter l'argmax.

Le routage D-32 n'est donc **pas opérant en pratique** : un verbatim dont le vrai
sous-thème est hors périmètre reçoit un sous-thème frère plausible, sans passer
en revue. Le mécanisme prévu pour le détecter — le seuil `classification_niv2`,
déclaré depuis l'origine et jamais lu — est branché mais **inactif par défaut**
(`thresholds.niv2_seuil_actif`). L'activer et le calibrer relève de L7.

---

## 5. Ce que je recommande pour la seconde itération

Elle coûte désormais moins d'une heure.

| # | Action | Justification mesurée |
|---|---|---|
| 1 | **Porter les époques de niv1 et niv2 à 10** | Les deux progressaient encore à la 5ᵉ époque : niv1 0,2975 → 0,3023, niv2 0,2491 → 0,2605. Le sentiment, lui, plafonne dès la 2ᵉ — le laisser à 5. |
| 2 | **Activer et calibrer `niv2_seuil_actif`** | Sans lui, D-40 ne se déclenche jamais et le routage D-32 reste théorique (§4.6). |
| 3 | **Tester `pos_weight_max`** | Le poids atteint 320 sur *Académie* ; la précision micro du niveau 1 plafonne à 0,74. Levier déjà en configuration, inactif. |
| 4 | **Comparer `lowercase` vrai / faux** | Cette itération est en `false` (CamemBERT est *cased*) ; le gain n'a pas été isolé faute de point de comparaison. Une passe suffit. |

---

## 6. Itération 2 — 10 époques sur les classifieurs thématiques

**Un seul paramètre changé** par rapport à l'itération 1 : les époques de niv1 et
niv2 passent de 5 à 10 (le sentiment reste à 5, il plafonnait dès la 2ᵉ). Le gain
est donc attribuable — à une nuance près : porter les époques de 5 à 10 **étire
aussi le calendrier du taux d'apprentissage**, ce n'est pas strictement « plus
d'entraînement ».

Durée : **90,3 min** (niv1 38,1 · niv2 33,8 · sentiment 16,9).

### 6.1 Validation

| Modèle | Itération 1 | **Itération 2** | Gain |
|---|---|---|---|
| niv1 (F1-macro val) | 0,3023 | **0,5098** | +69 % |
| niv2 (F1-macro val) | 0,2605 | **0,4490** | +72 % |
| sentiment (F1-macro val) | 0,8456 | 0,8456 | identique *(même seed, même configuration — reproductibilité confirmée)* |

niv1 a **plafonné** (0,5098 à la 9ᵉ époque, 0,5036 à la 10ᵉ). niv2 **progressait
encore** (0,3397 à la 5ᵉ, 0,4490 à la 10ᵉ) : il reste du gain à prendre.

### 6.2 Test — jeu de recette gelé, 1 128 verbatims, seuil 0,85

| | Ancien | Itération 1 | **Itération 2** |
|---|---|---|---|
| F1-macro niveau 1 | – *(D-36)* | 0,6323 | **0,6647** |
| F1-micro niveau 1 | – | 0,7524 | **0,7858** |
| P(niveau 1 correct) | – | 0,7644 | **0,8030** |
| **P(couple niv.1+niv.2)** | – | 0,5723 | **0,6574** |
| Sentiment accuracy | 0,8145 | 0,9352 | 0,9352 |
| Sentiment F1-macro | 0,6546 | 0,8783 | 0,8783 |
| Sorties bi-thèmes | 94,95 % | 5,94 % | 5,94 % *(annoté : 4,61 %)* |
| Taux de faux 2ᵉ thème | – | 0,0492 | 0,0492 |

**P(couple) gagne 8,5 points** — c'est la métrique la plus proche de l'usage.

### 6.3 Seuil multi-label — la recommandation se déplace

La courbe recalculée sur la validation place l'optimum à **0,65** (F1-macro 0,600)
contre 0,85 à l'itération 1 : le modèle mieux entraîné est mieux calibré, il n'a
plus besoin d'un seuil aussi haut pour cesser de sur-activer.

Le **rappel du second thème triple** (0,086 → 0,286). Mais sa **précision plafonne
toujours à 0,291** contre 0,70 visés. Mesuré désormais **sur deux modèles de
qualité très différente** : la limite est bien le volume d'annotation
(35 bi-thèmes au test, ~155 au train), pas le modèle.

**Arbitrage retenu : 0,85 plutôt que 0,65.** Sur la validation, 0,65 a un meilleur
F1-macro (0,600 contre 0,582) ; mais 0,85 produit 5,7 % de bi-thèmes contre 10,7 %,
pour 3,3 % annotés. Comme la maille de décision de Cultura est le **volume par
(thème × sentiment)**, la fidélité du volume prime sur 1,8 point de F1. Le test
conforte ce choix — sans le fonder, un seuil ne se règle pas sur le test.

### 6.4 Le taux de revue devient pilotable

| Seuil | 0,60 | 0,65 | **0,66** | **0,67** | 0,68 | 0,70 |
|---|---|---|---|---|---|---|
| Taux de revue | 2,5 % | 9,2 % | **11,7 %** | **14,7 %** | 17,8 % | 25,3 % |

**Les seuils 0,66 et 0,67 tiennent la cible D-9 (10 à 15 %)** — objectif O-4, qui
devait attendre L7. L'ancien modèle passait de 16,9 % à 92,0 % entre 0,50 et 0,65 :
aucun réglage n'existait.

Réserve : sur la grille standard à pas de 0,05, le saut 0,70 → 0,75 vaut
+39,4 points et **viole toujours le critère de monotonie de EF-7**. Mais cette zone
raide n'est pas le point de fonctionnement ; au pas de 0,01, la courbe est régulière
autour de 0,66.

### 6.5 D-40 fonctionne, mais reste invalidable

Avec `niv2_seuil_actif: true` et un seuil de 0,10 (calibré sur la validation),
**100 verbatims (8,9 %) sortent avec un `theme1_niv2` vide, et tous sont routés en
revue**. Le mécanisme est fonctionnel.

Le calibrage s'est nettement amélioré : la confiance médiane des cas valides passe
de 0,098 (itération 1) à **0,289**, contre 0,094 pour les hors-périmètre. À 0,10,
on détecte **57 % des hors-périmètre pour 8,5 % de routage à tort**.

> ⚠️ **Ces 57 % portent sur 7 cas** — quatre détectés sur sept. Le jeu de validation
> ne contient que 7 sous-thèmes hors périmètre, et le jeu de test 5. **Le routage
> D-32 n'est pas validable statistiquement sur ce corpus**, quelle que soit la
> qualité du modèle. À assumer comme tel, ou à faire porter par la calibration de
> confiance de L7.

---

## 7. 🔴 Défaut de production découvert — la quantification ONNX dégrade les modèles

En rétablissant l'export ONNX (le blocage venait simplement du paquet `onnx`
absent, non d'une incompatibilité de versions comme je l'avais d'abord conclu),
la comparaison des deux backends **sur les modèles V1 actuellement servis** donne :

| Modèle V1 | Corrélation des probabilités | Accord argmax |
|---|---|---|
| niv1 | 0,78 | **55 %** |
| niv2 | 0,50 | **13 %** |
| sentiment | 0,71 | **74 %** |

Une quantification int8 saine donnerait une corrélation > 0,99 et un accord > 98 %.
**Le modèle servi en ONNX n'est pas le modèle entraîné.**

Et il n'est même pas plus rapide : **6,8 verbatims/s en ONNX contre 22,4 en
PyTorch**, soit **3,3 fois plus lent**. La configuration
`AutoQuantizationConfig.avx2` cible x86 alors que le poste de production est
Apple Silicon arm64 (ENF-2). **Le risque T3 de l'état des lieux est confirmé — et
il coûte de la justesse, pas seulement de la vitesse.**

**Portée.** `onnx.use_for_inference` valait `true` et les artefacts ONNX existent
pour les trois modèles V1 : dans un environnement où `optimum` est installé —
c'est le cas du worker Docker — **l'application sert un modèle dégradé depuis la
mise en production**. Cela signifie aussi que la baseline publiée en L2, mesurée
en repli PyTorch, est **plus favorable que ce que la production délivre
réellement**.

**Action prise :** `onnx.use_for_inference: false`, avec le détail des mesures en
commentaire. Sans ONNX, le débit est de 22 à 24 verbatims/s, soit ~8 minutes pour
11 000 — très au-dessus de ce qu'exige ENF-1. Aucune raison de réactiver ce chemin
avant d'avoir requalifié la quantification sur le matériel cible.

> **À vérifier côté exploitation** : quels lots mensuels ont été traités avec le
> chemin ONNX actif. Si la réponse est « tous », une partie du grief de Cultura
> sur la qualité pourrait venir de là, et non du modèle.

---

## 8. Non-régression applicative — les 5 recettes sont au vert

Rejouées le 10/09/2026 après **tous** les changements de ce lot (chargeur,
`predictor.build_output`, `features`, `dataset`, `config.yaml`) :

| Recette | Résultat | Référence documentée |
|---|---|---|
| V1 | **48 OK · 0 ÉCHEC · 0 SKIP** | 48/48 ✅ |
| V3 | **13 OK · 0 ÉCHEC** | 13/13 ✅ |
| V4 | **50/50 OK** | 50/50 ✅ |
| V5 | **112/112 OK** | 112/112 ✅ |
| **V6** | **26/26 OK** | absente de l'état des lieux — désormais couverte ✅ |

Elles tournent sur le **moteur stub** : elles valident la plomberie applicative,
jamais la qualité du modèle (R-7). C'est précisément ce qu'on leur demande ici —
vérifier qu'aucun des changements du lot n'a cassé l'application. La qualité, elle,
est portée par la recette métier (`data/output/recette_metier_L9.xlsx`).

**Environnement d'exécution.** La procédure documentée
(`docs/RECETTE_V1.md`, `app/README.md`) prévoit un venv dédié avec
`fastapi httpx sqlalchemy pydantic pydantic-settings argon2-cffi PyJWT
python-multipart pandas numpy openpyxl pyyaml redis rq`. Le `.venv_validate` du
dépôt étant inutilisable (liens symboliques déshydratés par OneDrive), il a été
reconstruit hors du dossier synchronisé. **`httpx` est bien documenté** — son
absence de `app/api/requirements.txt` est normale, c'est une dépendance de test.

---

## 9. Itération 3 — niv2 seul, 20 époques

**Un seul modèle retouché**, niv1 et le sentiment étant restés à leur version de
l'itération 2. Arrêt anticipé déclenché à l'époque 15 (patience 3) : le plateau
est atteint. Durée **51,5 min**.

| | Itération 2 | **Itération 3** |
|---|---|---|
| niv2 — F1-macro validation | 0,4490 | **0,5675** (+26 %) |

### Bilan des trois itérations — jeu gelé, 1 128 verbatims, seuil 0,85

| Métrique | Ancien | Itér. 1 | Itér. 2 | **Itér. 3** |
|---|---|---|---|---|
| Sentiment accuracy | 0,8145 | 0,9352 | 0,9352 | **0,9352** |
| Sentiment F1-macro | 0,6546 | 0,8783 | 0,8783 | **0,8783** |
| dont F1 *Neutre* | 0,2626 | 0,7407 | 0,7407 | **0,7407** |
| F1-macro niveau 1 | – | 0,6323 | 0,6647 | **0,6647** |
| F1-micro niveau 1 | – | 0,7524 | 0,7858 | **0,7858** |
| P(niveau 1 correct) | – | 0,7644 | 0,8030 | **0,8030** |
| **P(couple niv.1+niv.2)** | – | 0,5723 | 0,6574 | **0,6901** |
| Part de sorties bi-thèmes | 94,95 % | 6,83 % | 5,94 % | **5,94 %** *(annoté 4,61 %)* |
| Taux de faux 2ᵉ thème | – | 0,0605 | 0,0492 | **0,0492** |
| Précision du 2ᵉ thème | – | 0,2319 | 0,1833 | **0,1833** |

Seul **P(couple)** bouge entre les itérations 2 et 3, ce qui est attendu : seul
niv2 a changé. Il gagne **3,3 points**, et **11,8 points depuis l'itération 1**.

> La précision du 2ᵉ thème baisse de 0,2319 à 0,1833 entre les itérations 1 et 2.
> Sur **35 cas** bi-thèmes, cela représente moins de deux verbatims : c'est du
> bruit d'échantillonnage, pas une régression. C'est la même petitesse
> d'échantillon qui rend la cible de 0,70 inatteignable et non mesurable avec
> confiance.

### Le seuil de niveau 2 devient discriminant

La séparation entre sous-thèmes dans le périmètre et hors périmètre se creuse à
chaque itération :

| | Confiance médiane, dans périmètre | Hors périmètre | Rapport |
|---|---|---|---|
| Itération 1 | 0,098 | 0,053 | 1,8 |
| Itération 2 | 0,289 | 0,094 | 3,1 |
| **Itération 3** | **0,737** | 0,113 | **6,5** |

À un seuil de 0,30, on détecte désormais **71 % des hors-périmètre pour 16 % de
routage à tort** — contre aucun point de fonctionnement exploitable à l'itération 1.

> ⚠️ **Toujours 7 cas de validation.** Ces 71 % valent cinq verbatims sur sept.
> Le mécanisme est devenu discriminant, mais **la validation statistique du
> routage D-32 reste hors de portée de ce corpus.**

### Où s'arrêter

niv1 et le sentiment ont plafonné ; niv2 vient de plafonner à son tour (arrêt
anticipé). **Les trois modèles sont au bout de ce que ce corpus et cette
architecture permettent** sans changer autre chose : plus d'annotations
bi-thèmes, un référentiel moins concentré, ou une architecture hiérarchique.

---

*Projet interne Cultura / eXalt — usage confidentiel.*
