# La couche de décision — industrialisation des trois leviers

> **Objet.** Les trois leviers validés par le PO le 11/09/2026 sont désormais
> **dans le produit**, plus dans des scripts d'analyse. Ce document dit ce
> qu'ils font, ce qu'ils rapportent réellement, et ce que l'industrialisation a
> corrigé de ce que j'avais annoncé.
>
> **Statut.** v1.2 — 11 septembre 2026, après les arbitrages du PO.
> **Code.** `src/inference/decision.py` · **Configuration.** `config.yaml → decision`
> **Recette.** `app/tests/recette_couche_decision.py` — 41 OK · 0 ÉCHEC

---

## 1. Ce qui change dans le code

### Une seule décision, à un seul endroit

La sélection des thèmes de niveau 1 était écrite **deux fois** : dans
`build_output` (production) et dans `src/evaluation/decision_niv1.py`
(évaluation), avec la consigne de les garder identiques à la main. Tant que la
règle tenait en trois lignes — seuil, repli sur l'argmax, plafond — le risque
restait théorique.

Il cesse de l'être dès lors qu'un levier déplace le **thème 1** : une évaluation
qui rejouerait une décision approchée mesurerait un produit qui n'existe pas.

La décision vit donc maintenant dans `PolitiqueDecision`
(`src/inference/decision.py`), appelée par la production **et** par
l'évaluation. La recette le vérifie sur 300 verbatims simulés à sources
mélangées : *0 désaccord*.

### Ordre d'application

```
1. seuils par thème        →  activation, repli sur l'argmax
2. plafond max_themes      →  troncature à 2
3. arbitrage par source    →  bascule contextuelle du thème 1
4. suppression des paires  →  retrait du membre le moins probable
```

Le plafond précède la suppression **délibérément** : le créneau libéré n'est pas
repourvu par un troisième thème. Supprimer une paire veut dire « ces deux
étiquettes désignent un seul sujet », pas « il reste une place à pourvoir ».

### Non-régression

| Recette | Résultat |
|---|---|
| V1 · V3 · V4 · V5 · V6 | **48 · 13 · 50 · 112 · 26 OK**, 0 échec |
| L1a — chargeur | 29 OK · 1 échec *(connu : jeu factice obsolète)* |
| L2 — protocole sans fuite | 15 OK · 0 échec |
| **Couche de décision** | **41 OK · 0 échec** |

### La source traverse la chaîne

L'arbitrage contextuel a besoin de la provenance **fine** (`MDTC-postrecep`, pas
`MDTC`). Elle circule désormais du chargeur jusqu'à la décision
(`predict_cleaned_batch(..., sources)`), et le chargeur de production l'affine
quand il reconnaît le schéma de la livraison (`loader.affiner_source`).

La source **n'entre dans aucun modèle** : elle ne sert qu'à arbitrer.

---

## 2. Deux défauts trouvés en industrialisant

### Le seuil déclaré n'était pas le seuil appliqué

`config.yaml` portait `classification_niv1: 0.35`, hérité du prototype. Tous les
rapports depuis le 09/09 passaient `--seuil 0.85` en ligne de commande. **La
configuration de production, elle, restait à 0,35** — soit environ 2,5 thèmes
activés par verbatim, tronqués à 2 : c'est ce qui produisait les **95,1 % de
sorties bi-thèmes** mesurées sur la baseline.

Le seuil déclaré est désormais le seuil appliqué (0,85, calé sur la validation).

### L'évaluation mesurait deux décisions différentes

Dans `evaluer_cultura.py`, `--seuil` était appliqué **après** l'inférence : les
métriques de niveau 1 sortaient au seuil demandé pendant que la hiérarchie, le
routage D-40 et la confiance sortaient du seuil de configuration.

Sans conséquence tant que seul le thème 1 comptait — il est le même à tout
seuil. Faux dès que les leviers le déplacent. Le seuil est maintenant posé avant
la construction du prédicteur.

---

## 3. Ce que les leviers rapportent réellement

**Jeu de test gelé, n = 1 010 verbatims annotés en thème, cumulatif, mesuré avec
l'implémentation de production :**

| Configuration | F1-macro | Bi-thèmes | Précision 2ᵉ | Faux 2ᵉ |
|---|---|---|---|---|
| Seuil unique 0,85 | 0,6647 | 5,94 % | 0,1833 | 4,92 % |
| + seuils par thème | 0,6683 | 6,53 % | 0,2121 | 5,33 % |
| + arbitrage par source | 0,6688 | 6,53 % | 0,2121 | 5,33 % |
| **+ suppression des paires** | **0,6922** | **2,97 %** | **0,4000** | **2,05 %** |

**Gain total : +2,75 points de F1-macro. Faux second thème divisé par 2,4.
Précision du second thème +118 % en relatif. Part de bi-thèmes 2,97 % pour
3,47 % annotés — dans la bande visée.**

Par thème, le gain est très concentré, et **aucun thème n'est dégradé** :

| Thème | n | Avant | Après | Écart |
|---|---|---|---|---|
| Recherche produit | 26 | 0,4918 | **0,6667** | **+0,175** |
| Choix produit | 32 | 0,4507 | **0,5556** | **+0,105** |
| Bug | 68 | 0,6712 | 0,6901 | +0,019 |
| Réception commande | 421 | 0,8649 | 0,8681 | +0,003 |
| Général | 336 | 0,8452 | 0,8459 | +0,001 |
| *(6 autres thèmes)* | | | | inchangés |

---

## 4. Ce que j'avais annoncé et qui ne tient pas

L'industrialisation a invalidé deux affirmations de
`OPTIMISATION_SANS_CULTURA.md`. Elles venaient d'une réimplémentation
simplifiée de la décision — le document le signalait, mais je n'en avais pas
tiré la conséquence : **les écarts eux-mêmes n'étaient pas fiables.**

### La règle post-réception n'est pas « le levier le plus rentable »

J'annonçais **24 erreurs corrigées pour 2 créées**. Mesuré avec la vraie couche
de décision, à la marge d'origine (`avance_max = 0,6`), sur la validation :

> **19 décisions modifiées → 9 corrigées, 8 cassées.** Un pile ou face.

**Cause identifiée.** La marge avait été calée *avant* l'existence des seuils par
thème. Les deux leviers se recouvrent : les seuils par thème arbitrent déjà entre
`Général` (0,75) et `Réception commande` (0,80). Appliquée par-dessus, la règle
rejoue un arbitrage déjà rendu, et le rend moins bien.

**Recalibration** (`scripts/calibrer_regle_source.py`, sur la validation) :

| `avance_max` | Modifiées | Corrigées | Cassées | Net |
|---|---|---|---|---|
| ≤ 0,25 | 0 | 0 | 0 | 0 |
| **0,30** | **4** | **4** | **0** | **+4** |
| 0,35 | 10 | 7 | 3 | +4 |
| 0,40 | 11 | 7 | 4 | +3 |
| 0,60 *(valeur d'origine)* | 19 | 9 | 8 | **+1** |
| 0,80 | 56 | 21 | 33 | **−12** |

Retenu : **0,30** — le seul réglage qui ne casse rien. Le levier devient
strictement positif, mais il est **petit** : 4 corrections sur 1 048 en
validation, 4 sur 1 128 en test. Il l'est réellement ; c'est la mesure d'origine
qui était fausse, pas le levier qui s'est dégradé.

### C'est la suppression des paires qui porte le gain

Ablation sur la **validation** (n = 1 048), chaque levier isolé :

| Levier seul | F1-macro | Écart |
|---|---|---|
| Aucun | 0,5824 | — |
| Seuils par thème | 0,5963 | **+0,0139** |
| Paires confusables | 0,5877 | +0,0053 |
| Arbitrage par source | 0,5826 | +0,0002 |
| **Les trois** | **0,6081** | **+0,0257** |

Le total dépasse la somme des parties : les seuils par thème font monter les
bi-thèmes (6,30 %), que la suppression des paires reprend (2,29 %). **Les deux
leviers se complètent** — c'est pour cela qu'ils se mesurent ensemble.

---

## 5. Arbitrage : la paire `Cartes cadeaux / Passer commande` est retirée

Les deux paires ne se valaient pas.

| Configuration | F1-macro (val) | Bi-thèmes (val) | Effet sur `Passer commande` |
|---|---|---|---|
| Les deux paires | 0,6081 | 2,29 % | **F1 0,5556 → 0,5000** |
| **`Choix produit / Recherche produit` seule** | **0,6078** | **3,63 %** | **inchangé** |
| `Cartes cadeaux / Passer commande` seule | 0,5834 | 4,39 % | dégradé |

**Décision du PO du 11/09 : retirer `Cartes cadeaux / Passer commande`.**

Elle coûtait 5,6 points de F1 à `Passer commande` sans en rapporter aucun à
`Cartes cadeaux` (0,7077 inchangé dans tous les cas), pour un gain global de
0,0003 — du bruit. Son seul effet réel était de réduire encore la part de
sorties bi-thèmes : un bénéfice tant que le modèle sur-activait, **un coût une
fois la sur-activation corrigée**. C'est exactement ce qui s'est produit — avec
les deux paires la part tombait à 2,18 % en test, sous le plancher de la bande
visée ; avec une seule elle est à 2,97 %, dedans.

Le retrait améliore donc **tout** : F1-macro 0,6871 → 0,6922, précision du
second thème 0,3182 → 0,4000, part de bi-thèmes remise dans la bande, et plus
aucun thème dégradé. Le seul recul est le taux de faux second thème, 1,44 % →
2,05 % — soit toujours **cinq fois sous l'engagement** de 10 %.

La cause — le recouvrement des libellés `Cartes cadeaux` et `Passer commande` au
référentiel — appartient à Cultura (D-7) et **est remontée à l'atelier L3**.
Masquer un défaut de référentiel en aval n'est pas le corriger.

---

## 6. Critères d'acceptation, recalculés

Calculés par `evaluer_cultura.py` (bloc `criteres`), plus recopiés à la main.
La distinction **engagement / indicateur suivi** est celle arbitrée par le PO
le 11/09.

| Critère | Statut | Cible | Avant | **Après** | Verdict |
|---|---|---|---|---|---|
| Taux de faux second thème | **engagement** | ≤ 10 % | 4,92 % | **2,05 %** | ✅ |
| Erreur de volume (thème × sentiment) | **engagement** | ≤ 15 % **au global** | 13,6 % | **12,51 %** | ✅ |
| Part bi-thèmes dans un facteur 1,5 de l'annotée | **engagement** | [2,31 % ; 5,20 %] | 5,94 % | **2,97 %** | ✅ |
| Précision du second thème | *indicateur suivi* | — *(ex-≥ 0,70)* | 0,1833 | **0,4000** | 📌 |

**Les trois engagements sont tenus.**

### Deux arbitrages ont rendu cette table lisible

**La précision du second thème devient un indicateur suivi.** Elle mesurait
mal : sur 30 propositions annotées, 1 seule est un second sujet légitime, 9 sont
une hésitation entre deux étiquettes qui se recouvrent, 6 ont le « second
thème » égal au thème 1 annoté. Elle portait de surcroît sur 35 verbatims
bi-thèmes, et n'avait jamais été validée par Cultura (Q-9). Elle reste publiée —
elle a plus que doublé — mais elle n'est plus opposable.

**L'erreur de volume s'apprécie au global.** Les quatre plus gros couples
(thème × sentiment), ceux qui pilotent effectivement la priorisation, sont à
5-11 %. Les écarts se concentrent sur les couples moyens, où une dizaine de
verbatims suffit à faire bouger le pourcentage : 32 annotés contre 43 prédits
pour `Bug / Négatif`, ce sont 11 verbatims. Le détail par couple reste produit
et publié, **en suivi**.

### La bande de bi-thèmes, tenue de justesse et par le bon bout

Avec les deux paires confusables, la part émise tombait à 2,18 % pour 3,47 %
annotés : **sous le plancher** de 0,13 point. Le retrait de la paire
`Cartes cadeaux / Passer commande` la ramène à **2,97 %**, dans la bande.

Le réglage n'a jamais été calé sur le test : la décision de retrait s'appuie sur
la validation, où la paire s'était déjà révélée inutile (+0,0003 de F1-macro
pour 5,6 points perdus sur `Passer commande`). Que le critère du test revienne
dans la bande est une conséquence, pas un objectif — recalibrer sur le jeu de
test serait une fuite d'un autre genre, et le projet a déjà payé ce prix une
fois.

### Les volumes, à la maille de décision de Cultura

| Couple (thème × sentiment) | Annoté | Prédit | Erreur | |
|---|---|---|---|---|
| Réception commande / Positif | 315 | 291 | 7,6 % | ✅ |
| Général / Positif | 220 | 237 | 7,7 % | ✅ |
| Réception commande / Négatif | 100 | 95 | 5,0 % | ✅ |
| Général / Neutre | 62 | 55 | 11,3 % | ✅ |
| Attente commande / Négatif | 47 | 57 | 21,3 % | ❌ |
| Passer commande / Négatif | 36 | 30 | 16,7 % | ❌ |
| Bug / Négatif | 32 | 43 | 34,4 % | ❌ |
| Général / Négatif | 20 | 24 | 20,0 % | ❌ |

Les **quatre plus gros volumes sont à 5–11 %** — ce sont eux qui pilotent la
priorisation. Les écarts se creusent sur les couples moyens. La question reste
ouverte : **la cible de 15 % s'applique-t-elle au global ou par couple ?**

---

## 7. Auditabilité

Chaque lot produit compte les applications de chaque règle :

```json
{"verbatims": 1128, "regle_source_appliquee": 4, "paire_supprimee": 43,
 "source_absente": 0, "source_non_reconnue": 616}
```

* `source_absente` à 0 confirme que la source traverse bien la chaîne ;
* `source_non_reconnue` = 616, ce sont les verbatims Mopinion et MDTC-postachat,
  qu'aucune règle ne vise ;
* si une règle ne pouvait **jamais** s'appliquer, le journal le dirait
  (`journaliser_couverture`).

Un libellé de règle absent du référentiel **échoue au démarrage**. Le
référentiel appartient à Cultura (D-7) : s'il change, une règle calée sur
l'ancien doit se voir tout de suite. Un levier silencieusement muet serait pire
que pas de levier.

### Le référentiel attendu est déclaré, pas deviné

Ce garde-fou a d'abord **cassé la recette V1** : l'application V1 tourne sur les
20 thèmes de l'ancien référentiel, où `Général` n'existe pas — la construction
de la politique levait une erreur et le lot échouait.

C'était le garde-fou qui fonctionnait, appliqué à la mauvaise situation. Deux
cas se ressemblent et n'ont rien à voir :

| Situation | Comportement |
|---|---|
| Le référentiel n'est **pas** celui des leviers | leviers **désactivés**, avertissement au journal |
| Le référentiel est le bon, un libellé **manque** | **erreur au démarrage** |

Le discriminant est déclaré (`decision.referentiel_attendu`) et non deviné : les
deux référentiels partagent exactement **un** libellé de niveau 1 (D-36), et une
heuristique fondée sur le recouvrement s'y tromperait. La recette de la couche
verrouille les deux cas.

---

## 8. Deux moteurs CamemBERT, pas un remplacement

**Arbitrage du PO du 11/09 : le modèle Cultura 2026 s'ajoute au sélecteur, il ne
remplace rien.** V1, LM Studio, Claude et le stub restent disponibles.

La procédure d'activation prévue jusque-là écrasait `data/models/` par
`data/models/cultura_2026/`. Elle était irréversible sans restauration de
fichiers, et surtout elle détruisait le seul point de comparaison disponible.

Or les deux modèles n'ont presque rien en commun :

| | V1 | Cultura 2026 |
|---|---|---|
| Référentiel | 20 thèmes / 67 sous-thèmes | 11 / 59 |
| Seuil d'activation niv.1 | 0,35 | 0,85 |
| Couche de décision | aucune | trois leviers |
| Préfixe de satisfaction | échelle 1-5, inconditionnel | échelle 1-4, conditionnel |
| Minuscules au nettoyage | oui | non |
| Détecteurs de signaux | les trois | `insatisfaction` seul |

Un réglage global ne peut pas décrire les deux. Chaque moteur porte donc un
**profil** (`moteurs_camembert` en configuration) qui déclare son **écart** à la
configuration de référence ; le reste est hérité. `get_predictor` retrouve le
profil depuis le chemin enregistré au registre et sert le moteur avec sa
configuration complète.

Deux règles tiennent le reste :

* **C'est le modèle qui commande.** La politique de préfixe et le nettoyage ne
  sont pas déclarés en configuration : ils sont lus dans la
  `training_card.json` du modèle. Les lui contredire à l'inférence dégraderait
  ses sorties en silence — le projet a déjà payé ce genre d'erreur.
* **Les configurations sont des copies profondes.** Le prédicteur mémoïse sa
  politique de décision sur l'identité du dict de configuration ; deux moteurs
  qui partageraient l'objet partageraient la politique. La recette le vérifie.

### Les métriques publiées par V1 sont celles qui sont valides

Rendre V1 visible dans le sélecteur posait un piège : son seul rapport
d'évaluation est celui du 18/06, **mesuré sur un découpage fuité à 99,6 %**. Le
publier ferait afficher un F1 de niveau 2 de **0,891 pour V1** contre 0,692 pour
le modèle 2026 — soit exactement la conclusion inverse de la vérité, côte à côte
dans le même tableau.

Le profil V1 ne désigne donc aucun rapport. Il déclare les **seules mesures
valides** de ce modèle : la baseline L2 sur le jeu de test gelé, `accuracy
sentiment 0,8145` et `F1-macro sentiment 0,6546`. Aucune métrique thématique —
les référentiels ne partagent qu'un libellé de niveau 1 sur 20/11 et aucun de
niveau 2 (D-36), la comparaison thématique n'existe pas.

Une case absente au tableau de bord veut dire **non mesuré**, jamais zéro.

### Ce que la coexistence a cassé, et qu'il a fallu réparer

Rendre deux moteurs sélectionnables ne se limitait pas au registre. Trois
défauts n'apparaissaient qu'en conteneur ou à la bascule, et chacun aurait été
découvert en recette en direct.

**1. Aucun moteur n'aurait été détecté en conteneur.** Les profils déclarent des
chemins relatifs au projet (`data/models/cultura_2026`) ; le conteneur monte les
modèles sur `/data/models`. `resolve_path` aurait cherché
`/app/data/models/cultura_2026`, qui n'existe pas — les deux profils auraient
été jugés absents et l'application serait **retombée sur le stub, en silence**.
`config_worker` réécrit désormais les racines de profil comme il réécrit déjà
`paths`.

**2. Le référentiel du modèle 2026 n'était pas joignable.** Il vivait dans
`data/raw/`, que ni l'image du worker ni celle de l'API n'embarquent. Chaque
modèle **embarque maintenant son référentiel à sa racine**
(`<racine>/taxonomy.json`) : c'est la seule forme qui le suive partout, et elle
rend le modèle auto-descriptif. Un modèle sans son espace de labels n'est pas un
modèle exploitable.

**3. La revue humaine aurait proposé le mauvais référentiel.**
`settings.taxonomy_path` était figé sur le POC, et `load_taxonomy` mémoïsé sur
**une seule entrée** — le premier référentiel lu l'aurait été pour la durée du
processus. Un relecteur reprenant des sorties du modèle 2026 se serait vu
proposer les 20 thèmes du POC, dont **aucun sous-thème n'est commun** (D-36) :
chaque correction aurait enregistré un couple « inconnu » en base, et le
référentiel de la revue serait devenu un mélange des deux au bout de quelques
lots.

Le référentiel servi suit désormais le modèle — et plus précisément **le modèle
qui a produit le lot relu** (`GET /api/taxonomy?batch_id=…`), pas celui qui se
trouve actif au moment où la page s'ouvre. C'est la différence qui compte dès
qu'on bascule : un lot ancien se relit avec le référentiel de son propre moteur.

### Retour arrière

Resélectionner V1 dans la liste. Plus aucune manipulation de fichiers — c'est le
principal bénéfice du mode additif.

---

## 9. `churn` et `rupture` : « non mesuré », pas « absent »

`signal_churn` et `signal_rupture_client` n'ont **aucun détecteur entraîné**
(D-41 : 64 et 32 positifs au corpus, trop peu pour un modèle évaluable). Ils
sortent donc constamment à `false`.

L'interface ne les affichait pas — ce qui se lit « pas de rupture détectée »,
alors que nous ne l'avons pas cherchée. Sur les deux colonnes dont l'enjeu
métier est le plus fort, une absence de modèle passait pour une absence de
signal.

**Arbitrage du PO du 11/09 : le contrat de sortie ne bouge pas, l'affichage si.**

| Couche | Comportement |
|---|---|
| `OUTPUT_COLUMNS` | **inchangé** — 15 colonnes, aucune ajoutée ni retirée |
| Export CSV | `false`, comme aujourd'hui |
| `/api/meta` | expose `signaux_non_mesures` (`["rupture", "churn"]`) |
| Écrans *Résultats* et *Test* | badge **« rupture, churn : non mesuré »** et info-bulle expliquant D-41 |

Le périmètre est **détecté**, jamais codé en dur : `signaux_sans_modele(cfg)`
regarde quels `<signal>.joblib` existent, sans charger le moindre modèle. Le
jour où L4 entraînera un détecteur de churn, le badge disparaîtra tout seul. Si
la détection échoue, l'interface retombe sur son comportement d'origine plutôt
que d'annoncer un périmètre inventé.

Le périmètre suit **le moteur sélectionné**, pas la configuration de référence :
V1 possède les trois détecteurs, le modèle Cultura 2026 n'en a qu'un. Choisir V1
fait donc disparaître l'avertissement, choisir Cultura 2026 le fait apparaître.
C'est la conséquence directe de la coexistence des deux moteurs (§8).

---

## 10. Le seuil de revue : la grille était trop grossière

Le critère de monotonie — aucun bond de plus de 20 points d'un pas de seuil au
suivant — était le dernier resté en échec, avec **+35,8 points entre 0,70 et
0,75**. Il rendait le réglage inexploitable sur le papier : impossible de viser
une charge de relecture donnée si un demi-centième de seuil fait doubler le
volume à relire.

**Il était mesuré au pas de 0,05.** À pas grossier, tout escalier ressemble à une
falaise. Le pas ramené à **0,01** donne :

| Pas de mesure | Saut maximal | Où |
|---|---|---|
| 0,05 *(d'origine)* | **35,8 pts** | 0,70 → 0,75 |
| 0,01, grille entière | **22,2 pts** | 0,91 → 0,92 |
| 0,01, **plage d'exploitation** | **3,5 pts** | 0,75 → 0,76 |

Deux choses apparaissent, et elles n'ont rien à voir l'une avec l'autre.

**L'essentiel du saut était un artefact de mesure.** 35,8 points sur un pas de
0,05 recouvraient un empilement de marches de 1 à 2 points. Autour du point de
fonctionnement, la courbe est lisse :

```
seuil   taux de revue   marche
 0,68        9,6 %       +0,8
 0,69       11,1 %       +1,5   ← cible D-9 (10-15 %)
 0,70       11,6 %       +0,5
 0,71       12,8 %       +1,2
 0,72       14,1 %       +1,2
 0,73       15,9 %       +1,8
```

**Le saut qui subsiste est hors de portée d'usage.** Les 22,2 points restants
sont entre 0,91 et 0,92, où le taux de revue passe de 69 % à 92 % — un réglage
qui ferait relire neuf verbatims sur dix. Personne ne le choisira.

Le critère est donc désormais évalué sur la **plage d'exploitation**, et non sur
toute la grille. Cette plage se **déduit** de la charge visée : ce sont les
seuils qui atteignent les 10-15 % de D-9 (ici **0,69 à 0,72**), élargis d'une
marge déclarée de 0,05, soit **[0,64 ; 0,77]**. Elle n'est pas choisie a
priori — sinon on l'ajusterait jusqu'à ce que le critère passe, et il ne vaudrait
plus rien.

Sur cette plage : **3,5 points de saut maximal pour 20 autorisés. Le critère est
tenu.** Le saut sur la grille entière reste publié dans le rapport, pour que
l'écart entre les deux reste visible.

**Ce que cela donne concrètement** : la charge de relecture visée s'obtient à un
seuil de **0,69 à 0,72**, et un centième de seuil déplace la charge d'environ un
point. C'est pilotable.

---

## 11. Reproduire

```bash
python scripts/evaluer_cultura.py                    # avec les leviers
python scripts/evaluer_cultura.py --sans-leviers     # modèle nu, seuil unique
python scripts/ablation_leviers.py --split val       # apport de chaque levier
python scripts/calibrer_regle_source.py              # marge de l'arbitrage
python app/tests/recette_couche_decision.py          # recette de la couche
```

Inventaire des moteurs déclarés et réellement présents :

```bash
python -c "
from src.utils import load_config, profils, modele_present, libelle_modele
cfg = load_config()
for p in profils(cfg):
    ok = modele_present(cfg, p)
    print(('OK   ' if ok else 'MANQUE '), p['id'],
          libelle_modele(cfg, p) if ok else p['racine'])
"
```

---

*Projet interne Cultura / eXalt — usage confidentiel.*
