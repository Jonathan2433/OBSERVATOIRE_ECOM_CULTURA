# Rapport de lot L2 — protocole d'évaluation et baseline honnête

> **Objet.** Protocole sans fuite, et **première mesure valide** du modèle actuel
> sur données réelles Cultura. Remplace intégralement `eval_report.json`, dont
> aucun chiffre n'est réutilisé.
>
> **Statut.** v1.0 — 9 septembre 2026. **Auteur.** Data scientist.
> **Reproduction.** `python scripts/mesurer_baseline.py --split test`
> → `data/processed/baseline_modele_actuel.json`.
> **Contrôles.** `python app/tests/recette_l2_protocole.py` — 15 OK, 0 ÉCHEC.

---

## 1. Protocole

| Élément | Valeur |
|---|---|
| Corpus | livraison Cultura du 09/09, `v2_20260909` — 7 501 verbatims |
| Découpage | **par texte unique**, stratifié sur le thème de niveau 1, seed 42 |
| Jeu de mesure | split `test` — **1 128 verbatims**, dont **898 annotés en sentiment** |
| Fuite | **0** — intersection des textes entre les 3 splits vérifiée vide, contrôle bloquant |
| Doublons de texte | 1 339 sur 7 501 (17,8 %) — d'où l'obligation du split par texte |
| Préparation | anonymisation puis nettoyage, identiques à la chaîne de production |
| Préfixe de satisfaction | `[SATISFACTION x/10]`, note 1-4 **rééchelonnée** `{1:1, 2:4, 3:7, 4:10}` (D-37) |
| Backend | PyTorch (ONNX indisponible : `optimum` non installé) |

**Ce que le protocole corrige.** Le split historique découpait des *indices de
lignes*. Mesuré sur ce corpus : un découpage par ligne mettrait **234 des
1 126 lignes de test (20,8 %)** en fuite, leur texte étant déjà présent dans le
train. Le contrôle est désormais intégré à la fonction de split — il ne peut pas
être contourné en oubliant de l'appeler.

### Le jeu de recette est GELÉ — et pourquoi il a fallu l'imposer

Un découpage sans fuite ne suffit pas : il faut aussi que ce soit **le même** d'une
mesure à l'autre. Défaut constaté sur ce lot, avant publication de tout chiffre :
la baseline regroupait les doublons sur le texte **brut**, la préparation
d'entraînement sur le texte **nettoyé**. Les deux produisaient 1 128 verbatims de
test — et ne partageaient que **23,6 % de leurs lignes**. Le nombre identique
masquait entièrement l'écart.

Comparer un modèle mesuré sur l'un à un modèle mesuré sur l'autre n'aurait eu
aucun sens, et **rien ne l'aurait signalé** : c'est exactement la classe de défaut
qui a produit les chiffres invalides du prototype.

**Correction.** Le découpage est calculé **une fois**, sur un texte *canonique*
(nettoyage complet, minuscules forcées), et figé dans
`data/processed/cultura_2026/split_gele.csv`, indexé sur l'identité du verbatim
(`source`, `respondent_id`, `field`) — jamais sur son texte. Toutes les mesures le
relisent ; un verbatim absent du gel fait **échouer** le chargement plutôt que
d'être découpé en silence.

Vérifié : avec `lowercase: false`, le jeu de test est **identique au verbatim
près** (1 128 / 1 128). Le découpage ne dépend donc plus des options de nettoyage.

> **Effet sur les chiffres.** La baseline a été rejouée sur le jeu gelé. Les
> conclusions sont inchangées — accuracy 0,8145 contre 0,8151, règle 0,8397
> contre 0,8396, 0 sentiment divergent, inversion du préfixe confirmée. Les
> valeurs de ce rapport sont celles du **jeu gelé**.

**Ce que ce lot ne mesure pas.** Il n'y a **pas de baseline thématique** (D-36) :
les référentiels partagent 1 libellé de niveau 1 sur 20/11 et **0** sur 67/59 en
niveau 2. Aucun F1 thématique n'est calculable entre l'ancien modèle et les
annotations Cultura.

---

## 2. Sentiment — la seule tâche comparable

Les 3 classes sont identiques dans les deux référentiels.

| Métrique | Valeur |
|---|---|
| Accuracy | **0,8151** |
| F1-macro | **0,6461** |
| F1 *Négatif* | 0,7619 (n = 282) |
| F1 *Neutre* | **0,2396** (n = 61) |
| F1 *Positif* | 0,9367 (n = 555) |

> ⚠️ **L'accuracy de 0,8151 ne se compare pas au 0,641 publié.** Ce corpus est
> déséquilibré (62 % de *Positif*), l'ancien l'était artificiellement moins. La
> classe majoritaire seule atteint déjà **0,618**. Le F1-macro est la grandeur à
> suivre, et la classe *Neutre* (5,7 % du corpus) le tire vers le bas comme
> annoncé — **0,2396**, à porter aux cibles avant l'entraînement, pas après.

### 2.1 Par source (R-16) — l'écart est majeur

| Source | n | Accuracy | F1-macro |
|---|---|---|---|
| MDTC post-achat | 247 | 0,7368 | 0,6488 |
| MDTC post-réception | 505 | 0,8594 | **0,4965** |
| Mopinion desktop | 66 | 0,7424 | **0,7331** |
| Mopinion mobile | 80 | 0,8375 | **0,3039** |

MDTC post-réception affiche la meilleure accuracy et l'un des pires F1-macro :
massivement positif, le modèle y réussit en suivant la majorité. Mopinion mobile
tombe à 0,3039. **Une métrique globale aurait masqué un facteur 2,4 entre
sources.** R-16 est confirmé et chiffré.

---

## 3. Le résultat le plus actionnable : le préfixe s'inverse avec la longueur

Mesure par tranche de longueur (D-28), avec et sans préfixe de satisfaction :

| Tranche | Accuracy avec préfixe | Sans préfixe | **Apport du préfixe** |
|---|---|---|---|
| 1-2 mots (n=134) | 0,7910 | 0,3731 | **+0,4179** |
| 3-5 mots (n=269) | 0,8959 | 0,8030 | +0,0929 |
| 6-10 mots (n=185) | 0,8757 | 0,8541 | +0,0216 |
| 11-20 mots (n=176) | 0,7614 | 0,8409 | **−0,0795** |
| 21+ mots (n=134) | 0,6642 | 0,8209 | **−0,1567** |

**Lecture.** Sur les verbatims très courts, le texte ne porte aucun signal et
**c'est la note qui fait tout le travail** : sans elle, l'accuracy s'effondre de
79 % à 37 %. Sur les verbatims longs, la note **nuit** : un texte long est plus
souvent nuancé ou mixte, et le score global unique écrase ce que dit le texte.
Sans préfixe, la tranche 21+ mots devient la **meilleure** du corpus (0,8209).

**Conséquence pour L6 — un gain probablement peu coûteux.** Rendre le préfixe
**conditionnel à la longueur** (le conserver sous ~10 mots, le retirer au-delà)
est à tester dès la première itération. La mesure ci-dessus en donne l'ordre de
grandeur attendu sans avoir à l'entraîner d'abord.

---

## 4. EF-3 — la non-trivialité du sentiment n'est pas acquise

Règle **apprise sur le split train** (classe majoritaire par note), évaluée sur le
test, exactement comme le modèle :

```
note 1 → Négatif   note 2 → Négatif   note 3 → Négatif   note 4 → Positif
```

| | Modèle | Règle | Classe majoritaire |
|---|---|---|---|
| Accuracy | 0,8151 | **0,8396** | 0,618 |
| F1-macro | **0,6461** | 0,5725 | – |
| F1 *Neutre* | 0,2396 | **0,0000** | – |

**Verdict partagé.** Un `if/else` de trois lignes **bat le modèle CamemBERT de
2,4 points d'accuracy**. Le modèle ne reprend l'avantage que sur le F1-macro
(+7,4 points), et uniquement parce que la règle est **structurellement incapable
de prédire *Neutre*** : aucune note n'a *Neutre* pour classe majoritaire.

**Ce que cela contredit.** Le cadrage conclut (§1.4 b, EF-3, journal v1.3) que
« R-5 ne se réalise pas » et que EF-3 « n'est plus conditionnelle », au motif que
la note 3 est authentiquement ambiguë. **La prémisse est juste, la conclusion ne
suit pas** : la note 3 est bien ambiguë, mais la note 4 concentre 3 600 positifs
sur 3 755, si bien que la règle reste globalement plus juste que le modèle actuel.

**Deux arbitrages pour le PO :**

1. **Quelle grandeur fait foi pour EF-3 ?** Le verdict s'inverse selon qu'on
   retient l'accuracy ou le F1-macro. Argument métier en faveur du F1-macro :
   Cultura priorise sur des **volumes par (thème × sentiment)** ; une règle qui
   n'émet jamais *Neutre* ferait disparaître 5,7 % du corpus des tableaux de bord,
   silencieusement.
2. **Le plancher est désormais chiffré.** Conformément à D-36, les cibles se
   fixent en valeur absolue : le nouveau modèle doit dépasser **0,8397 d'accuracy
   et 0,5749 de F1-macro**. En dessous, la réponse honnête pour le sentiment est
   la règle, et l'effort ML doit se concentrer sur les thèmes.

> **Nuance à ne pas perdre.** Ce plancher est mesuré sur un modèle entraîné sur un
> **autre domaine**. Un modèle réentraîné sur ces données devrait le dépasser
> confortablement. S'il n'y parvient pas, c'est le signal qu'il faut écouter.

---

## 5. Le grief n°1, mesuré sur données réelles

| Mesure | Valeur | Point de départ connu |
|---|---|---|
| Sorties bi-thèmes | **95,1 %** | 43,3 % (sur 120 verbatims) |
| Annotations bi-thèmes | 3,9 % | 4,4 % sur le corpus |
| Thèmes par verbatim | 1,95 | ≈ 2,5 activés avant plafond |
| **Sentiments divergents entre thème 1 et 2** | **0 sur 1 073** | 0 sur 52 |

**Le sentiment recopié est confirmé, sans appel : 0 divergence sur 1 073 sorties
bi-thèmes.** C'est une propriété du code (`build_output` calcule un unique
`sent_idx`), pas des données — la mesure ne dépend donc pas du référentiel.

> ⚠️ **Les 95,1 % ne caractérisent pas l'ancien modèle dans son domaine.** Il est
> appliqué ici à un corpus dont il n'a jamais vu les thèmes : ses 20 anciennes
> classes reçoivent des probabilités moyennes et deux d'entre elles franchissent
> presque toujours le seuil de 0,35. Le chiffre honnête à retenir de cette ligne
> est **la mesure de référence du sentiment recopié**, pas le taux de bi-thèmes.

**Taux de revue humaine** — le défaut de réglage est reproduit à l'identique :

| Seuil | 0,50 | 0,60 | 0,65 | 0,70 | 0,75 | 0,80 |
|---|---|---|---|---|---|---|
| Taux de revue | 16,8 % | 45,2 % | **93,1 %** | 100 % | 100 % | 100 % |

Le seuil de 0,70 du cahier des charges reste **inexploitable**, et le saut
0,60 → 0,65 (+47,9 points) viole le critère de monotonie de EF-7.

---

## 6. Débit — R-4 est bien moins menaçant que prévu

| Étape | Durée (1 128 verbatims) | Part |
|---|---|---|
| Anonymisation (spaCy + regex) | 1,5 s — 740 verbatims/s | 3 % |
| Nettoyage | < 0,1 s | ~0 % |
| **Inférence (4 passes transformer)** | **44,9 s — 25,1 verbatims/s** | 97 % |
| **Chaîne complète** | **46,4 s** | |

**Extrapolation : 0,13 h — environ 8 minutes — pour 11 000 verbatims**, contre une
cible de 1 à 2 h (D-4).

**Cause identifiée, et elle n'est pas flatteuse par accident** : les verbatims
réels sont très courts (médiane 6 mots). Le remplissage se fait à la longueur du
lot, pas à `max_length: 256` — les passes transformer coûtent donc une fraction de
ce qui était supposé. Le chiffre est obtenu **sans ONNX** (repli PyTorch), ce qui
le rend d'autant plus solide.

> ⚠️ **Ne pas conclure que ENF-1 est tenue.** Cette mesure exclut les
> entrées/sorties base, l'orchestration de lot, les commits de progression tous
> les 250 verbatims et l'export CSV/XLSX. Elle extrapole depuis 1 128 verbatims.
> Seule la mesure de bout en bout du lot **L8 sur un lot réel de 11 000** fait foi.
> Elle indique en revanche que **le goulot n'est ni l'anonymisation ni
> l'`EmbeddingExtractor`**, et que la priorité de L8 devrait se déplacer vers la
> couche applicative.

---

## 7. Ce que ce lot livre

| Livrable | Fichier |
|---|---|
| Split par texte unique + contrôle bloquant | `src/training/split_sans_fuite.py` |
| Décision niveau 1 plafonnée, métriques du 2ᵉ thème, courbe de seuil (L5') | `src/evaluation/decision_niv1.py` |
| `evaluate.py` corrigé : F1 après plafonnement, `avant_plafond` conservé | `src/evaluation/evaluate.py` |
| Harnais de baseline reproductible | `scripts/mesurer_baseline.py` |
| Recette du protocole — 15 OK | `app/tests/recette_l2_protocole.py` |
| Mesures | `data/processed/baseline_modele_actuel.json` |

---

## 8. Réserve de séquencement sur L5'

Le plan place L5' (seuil multi-label) **avant** L6. La courbe de seuil est livrée
et testée, mais **le seuil opérationnel ne peut pas être fixé avant le
réentraînement** : les probabilités dépendent du modèle *et* de son espace de
labels, et un seuil calibré sur le référentiel 20/67 n'est pas transposable au
11/59.

**L5' livre l'outil et la méthode ; la valeur du seuil se fixe sur la validation à
la fin de L6.** Sans incidence sur la durée du chemin critique si les deux lots
sont explicitement enchaînés ainsi — mais à acter, car le plan annonce zéro marge.

---

*Projet interne Cultura / eXalt — usage confidentiel.*
