# Rapport de lot L1a — chargeur Cultura 2026

> **Objet.** Compte rendu d'exécution du lot L1a (`docs/SPEC_CHARGEUR.md`), livrables,
> mesures, et **écarts constatés avec les documents de cadrage**.
>
> **Statut.** v1.0 — 9 septembre 2026. **Auteur.** Data scientist.
> **Destinataire.** Product Owner.
> **Protocole.** Toutes les mesures de ce document portent sur la livraison
> `data/raw/cultura_2026/v2_20260909/` (9 fichiers, 26 826 lignes), rejouable par
> `python app/tests/recette_l1a_chargeur.py`. Aucun chiffre n'est repris
> d'`eval_report.json`.

---

## 1. Ce qui est livré

| Livrable | Fichier | Lignes |
|---|---|---|
| Normalisation des noms de colonnes (§4) | `src/preprocessing/column_norm.py` | 104 |
| Normalisation des labels (§8) | `src/preprocessing/label_norm.py` | 216 |
| Chargeur : 4 schémas, composition, anomalies, rapport | `src/preprocessing/cultura_loader.py` | 608 |
| Recette d'acceptation §11 | `app/tests/recette_l1a_chargeur.py` | 349 |
| Configuration : schémas, synonymes, échelles, périmètre | `config/config.yaml` (2 sections) | +175 |
| Anonymisation : les 3 points de §10 | `src/preprocessing/anonymizer.py` | modifié |
| Rapport de chargement | `data/processed/rapport_chargement_l1a.json` | produit |

**Recette L1a : 29 OK · 1 ÉCHEC · 1 SKIP.** L'échec et le skip sont analysés en §5.

---

## 2. Résultat du chargement

| Mesure | Valeur | Référence |
|---|---|---|
| Fichiers lus, schéma reconnu | **9 / 9** | 9 attendus |
| Lignes lues | **26 826** | audit §3 : 26 826 ✔ |
| Verbatims produits | **7 501** | voir §3 |
| Lignes annotées produisant un verbatim | 6 902 | – |
| Durée de chargement | 2,9 s | – |

**Par source :** MDTC post-achat 1 919 · MDTC post-réception 3 844 ·
Mopinion desktop 521 · Mopinion mobile 1 217.

### Les deux pièges de §7 sont neutralisés et testés

- Le caractère invisible `\x0b` en fin de libellé Mopinion mobile est supprimé :
  **les deux exports convergent vers un jeu de colonnes identique**. Sans cela,
  l'export janvier-mai perdait ses 4 champs libres en silence.
- `Dites-nous en plus :` et `Dites nous en plus :` **restent deux colonnes
  distinctes**. Une normalisation touchant aux traits d'union les fusionnerait ;
  le chargeur **échoue explicitement** dans ce cas plutôt que d'écraser un champ.

> **Précision de comptage.** Après normalisation il reste **4 schémas**, non 5.
> Le « cinquième schéma » de l'audit était la variante non normalisée de Mopinion
> mobile — c'est exactement ce que §4 demande de faire disparaître.

---

## 3. Réconciliation du total — écart assumé avec §11

`SPEC_CHARGEUR` §11 attend **7 552 verbatims**. Le chargeur en produit **7 501**.
L'écart est de **51**, et il est entièrement expliqué :

```
7 501 verbatims produits
+  51 textes écartés comme non classables
= 7 552  (total de §11)
```

**Cause.** §5.2 règle 1 dit qu'un champ « ne contenant que des espaces, de la
ponctuation seule ou `nan` » **ne produit aucune ligne**. Le total de 7 552 a été
établi sans appliquer cette règle. Les 51 textes concernés sont : `.` (32×),
`...` (4×), `??` / `????` / `??????` (7×), `!` (2×), et `:)`, `;`, `,,`, `/`, `*`,
`👍`, `👍🏻`, `😉`.

**Ce que fait le chargeur.** Il applique la règle 1 — un verbatim `.` ou `👍` n'est
pas classifiable, et les emojis sont de toute façon supprimés au nettoyage
(`cleaning.remove_emojis: true`), ce qui les rendrait vides plus loin dans la
chaîne. Le rapport publie **les deux chiffres**, pour que l'écart soit vérifiable
et non subi.

> ⚠️ **Arbitrage PO demandé.** Confirmer que la règle 1 prime sur le total de §11,
> et corriger §11 en conséquence (7 501). Sinon, indiquer que ces 51 textes doivent
> entrer dans le corpus.

---

## 4. Écarts avec l'audit du 09/09 — l'audit sous-comptait

Les décomptes ci-dessous sont à la **maille de l'annotation** (une ligne source),
comme l'audit. Le rapport publie aussi la maille du verbatim, qui diffère parce
qu'un répondant Mopinion multi-champs produit plusieurs verbatims portant la même
annotation.

| Anomalie | Mesuré | Audit / spec | Explication de l'écart |
|---|---|---|---|
| `SENTIMENT_ABSENT` | **572** | 572 | ✔ exact |
| `ANNOTATION_RECOPIEE` | **6** | 6 | ✔ exact |
| `SIGNAL_INCONNU` | **0** | 0 | ✔ exact |
| Sentiments | 4 177 / 1 948 / 371 | idem | ✔ exact |
| Signaux | 519 / 368 / 64 / 32 | idem | ✔ exact |
| `Attente commande` (thème 1) | **208** | 208 | ✔ exact |
| Hors périmètre D-32 (thème 1) | **58** | 58 | ✔ exact |
| `THEME_INCONNU` | **6** | 5 | +3 `#N/A`, −2 désormais résolus par synonyme |
| `SOUSTHEME_INCONNU` | **14** | 5 | voir ci-dessous |
| `COUPLE_INVALIDE` (thème 1) | **19** | 16 à 18 | +3 couples apparus **après** normalisation |
| Hors périmètre (thème 1 + 2) | **75** | 58 | l'audit n'a mesuré que le thème 1 |

### Quatre constats nouveaux, à porter au registre

**(a) `#N/A` — 3 occurrences en colonne thème, 3 en sous-thème.** Valeur d'erreur
tableur, absente de toutes les tables de §8. Elle explique exactement l'écart entre
les **7 071 lignes portant un thème** que je mesure et les **7 068 annotations** de
l'audit : 7 071 − 3 = 7 068.

**(b) `Retait magasin` — 5 occurrences.** Faute de frappe pour `Retrait magasin`,
absente de l'audit §4.2 et de la table de synonymes de §8.2. **Non corrigée** : le
chargeur l'écarte et la journalise, et la propose en *candidat synonyme*. Ajouter
une entrée en configuration récupérerait ces 5 lignes.

**(c) `Moyens de paiement` — 1 occurrence** pour `Modes de paiement`. Même
traitement.

**(d) Deux sous-thèmes déclarés « sans aucun exemple » en ont un.**
`Commande marketplace reçue` et `Expérience personnalisée` apparaissent chacun
**une fois, dans la colonne thème 2** — que l'audit n'a pas examinée. Les
sous-thèmes réellement à zéro exemple sont donc **5, et non 7** (audit §4.4). Sans
effet sur D-32 (tous restent sous le seuil de 10), mais cela corrige un chiffre
utilisé dans l'arbitrage Q-27 / L15.

> ⚠️ **Arbitrage PO demandé.** Ajouter `Retait magasin → Retrait magasin` et
> `Moyens de paiement → Modes de paiement` à la table de synonymes ? Je ne l'ai
> **pas** fait : ajouter un synonyme modifie l'espace de labels, ce qui relève d'un
> arbitrage, pas du chargeur. Gain : 6 lignes.

### Les couples invalides ne sont pas corrigés (§8.4)

19 sur le thème 1, 2 sur le thème 2. Le plus fréquent reste
**(Général, Retrait magasin) × 11** — une divergence d'interprétation, pas une
faute de frappe. Trois couples n'étaient pas dans la liste de l'audit
(`Passer commande > Produits numériques`, `Attente commmande > Autre passer
commande`, `Général > Rétractation client`) : ils **n'apparaissent qu'après**
normalisation du thème, l'audit les ayant classés en « thème inconnu ». Tous sont
journalisés dans le rapport, à destination de l'atelier L3.

---

## 5. Les deux points non satisfaits de §11

**❌ Le jeu factice n'est pas lu par le chargeur.** `data/raw/fake/` a été généré
le 12 août **sur les maquettes**, que l'audit a déclarées non fiables. Mesuré :
3 fichiers sur 5 ne correspondent à aucun schéma réel ; les 2 fichiers Mopinion
ont 26 colonnes contre 31 et 33 en réel. Il faut soit régénérer le jeu factice sur
les schémas réels (`scripts/generate_fake_dataset.py`, D-22), soit retirer ce
critère de §11. **Non traité dans ce lot** : c'est un artefact distinct, avec sa
propre spécification (`docs/SPEC_JEU_FACTICE.md`), et le régénérer n'était pas le
meilleur emploi du temps du chemin critique.

**⏭️ Les recettes V1, V3, V4, V5 et V6 n'ont pas été rejouées.** Elles exigent
l'environnement applicatif (base, API, worker). Aucun code applicatif n'a été
modifié par ce lot — les modules livrés sont nouveaux, et les trois fichiers
existants touchés (`anonymizer.py`, `evaluate.py`, `config.yaml`) le sont en
ajout. À rejouer en L9, comme prévu.

---

## 6. Anonymisation — les 3 points de §10

| Point | Mesure | État |
|---|---|---|
| `P########` masqué | `ma commande P12345678` → `ma [COMMANDE]` | ✅ le regex existant le couvrait déjà — **testé, pas supposé** |
| E-mail partiellement masqué | `******@free.fr` **n'était pas masqué** | ✅ corrigé : l'astérisque est admis dans la partie locale |
| spaCy absent | dégradait **en silence** | ✅ le chargeur échoue explicitement au démarrage |

Le mode dégradé du constructeur est conservé — il est légitime pour les recettes
applicatives torch-free, qui n'ingèrent aucune donnée réelle. Le contrôle bloquant
est placé à l'entrée du chargeur, et pilotable par
`anonymization.require_spacy`.

> **Observation, non corrigée.** `_ORDER_KEYWORD_RE` masque le mot-clé en même
> temps que l'identifiant : `ma commande P12345678` devient `ma [COMMANDE]`, ce qui
> détruit le mot « commande », fortement thématique. Défaut préexistant, qui
> s'applique identiquement à l'ancien et au nouveau modèle. Le corriger changerait
> la distribution des textes : à arbitrer avant L6, pas pendant.

---

## 7. Conformité RGPD

- Les données réelles **sont** protégées : `data/raw/cultura_2026/.gitignore`
  (`*` + `!.gitignore`) les exclut de Git — vérifié par `git check-ignore`.
- Le commentaire trompeur du `.gitignore` racine (« données simulées, aucune PII
  réelle ») **a été corrigé** : c'était l'action 4 de l'audit §11, restée ouverte.
- Le contrat de sortie du chargeur est une **liste blanche** : seules les colonnes
  déclarées en configuration sont recopiées. Une liste noire laisserait passer en
  silence une colonne PII ajoutée par Cultura à la prochaine livraison. Testé :
  aucune des 15 colonnes écartées par D-18 n'atteint la sortie.

---

## 8. Décisions d'implémentation à connaître

1. **Le libellé canonique n'est pas écrit en configuration.** Les groupes de
   synonymes déclarent des graphies équivalentes ; le canonique est celui des
   membres qui figure au référentiel (D-7). Si Cultura corrige
   « Attente comm**m**ande », la configuration reste valable sans modification —
   ce qui rend **D-27 réellement optionnelle**. Le chargeur échoue si un groupe
   n'a aucun, ou plusieurs, membres au référentiel.
2. **L'espace insécable est converti en espace, non supprimé** (§4 demande la
   suppression). Le supprimer souderait `Date\xa0d'achat` en `dated'achat`, qui ne
   s'apparierait plus avec `Date d'achat` — le défaut même que §4 prévient. Aucune
   colonne du 09/09 n'en contient : sans effet aujourd'hui, protecteur demain.
3. **`Produits non trouvés` : 104 valeurs vues, 91 rattachées** à un verbatim. Les
   13 autres appartiennent à des répondants n'ayant rempli que ce champ — donnée
   structurée sans verbatim porteur (D-30). Les deux chiffres sont au rapport.
4. **Les anomalies sont comptées à deux mailles** (annotation et verbatim). Sans
   cela, les volumes seraient gonflés par les répondants Mopinion multi-champs :
   `ANNOTATION_RECOPIEE` vaut 6 annotations mais 12 verbatims.
5. **Le rapport publie des *candidats synonymes***, détectés par proximité au
   référentiel et jamais appliqués. C'est le mécanisme qui rendra la prochaine
   livraison indolore : une nouvelle graphie devient visible au lieu de disparaître.

---

## 9. Questions ouvertes rencontrées, hypothèses appliquées

| # | Point | Ce que j'ai fait |
|---|---|---|
| Q-17 / Q-23 | Conversion des échelles 1-5 → 1-4 | Table de §7.1 appliquée, **marquée `hypothese: true`** en configuration. Vérifié : Mopinion `5` → `4`, `4` → `3`. |
| Q-22 | `SRC` (2 occurrences) | Écarté comme anomalie, journalisé. |
| Q-24 | Figer la graphie « Attente comm(m)ande » | Sans objet côté code (cf. §8.1) ; la demande préventive à Cultura reste utile. |
| Q-28 | `Gérer ma réservation` vs « Gérer une activité » | Libellé du référentiel retenu (D-7). |

---

## 10. Deux alertes qui touchent le chemin critique — **arbitrées le 09/09**

Découvertes en préparant L2. Elles remettaient en cause des critères d'acceptation.
**Le Product Owner a tranché les deux le 09/09** ; les décisions sont reportées en
§11, sous une forme reprenable au registre du cadrage.

### Alerte 1 — il n'existe pas de baseline thématique possible

Mesuré sur les deux référentiels :

| Niveau | Ancien | Nouveau | Libellés communs |
|---|---|---|---|
| niv.1 | 20 | 11 | **1** — `Programme de fidélité` |
| niv.2 | 67 | 59 | **0** |

Les modèles actifs émettent l'ancien espace de labels (`classifier_niv1` :
20 labels, `classifier_niv2` : 67). Les nouvelles données ne sont annotées que
dans le nouveau. **Les deux espaces sont disjoints : aucun F1 thématique ne peut
être calculé entre eux.**

Conséquences directes sur le contrat :

- **§7.2 famille A est privée de référence.** « F1-macro niv.1 : progression
  relative de +20 % sur la baseline mesurée » et « P(couple niv.1 + niv.2
  correct) ≥ baseline + 10 points » supposent une baseline thématique qui ne peut
  pas exister.
- **La DoD de L9** — « comparaison ancien/nouveau sur le jeu de recette gelé » —
  ne peut pas porter sur les thèmes.
- **O-5** (« le progrès est démontrable ») doit être reformulé.

Ce qui **reste** mesurable en baseline sur données réelles :

| Mesurable | Pourquoi |
|---|---|
| **Sentiment** | Les 3 classes sont identiques (`Négatif` / `Neutre` / `Positif`). Comparable par source et par tranche de longueur (D-28) — sous réserve de l'alerte 2. |
| **Distribution du nombre de thèmes** (EF-4) | Indépendante des libellés. C'est la mesure du grief n°1 : 43,3 % de sorties bi-thèmes contre 4,4 % d'annotations. |
| **Taux de recopie du sentiment** entre thème 1 et 2 | Indépendante des libellés. Point de départ : 0 divergence sur 52. |
| **Taux de revue, distribution de confiance** | Indépendantes des libellés. |
| **Débit** (ENF-1) | Indépendant des libellés. |

**Trois options, à trancher par le PO :**

1. Construire une **table de correspondance ancien → nouveau référentiel** (20 × 11)
   et évaluer les prédictions de l'ancien modèle projetées dans le nouvel espace.
   Donne une baseline thématique, mais dépendante d'un jugement humain et
   probablement pessimiste. Charge : ~1 j, plus l'arbitrage Cultura.
2. **Renoncer à la baseline thématique** et fixer les cibles de famille A en
   valeur absolue après le premier entraînement, en assumant qu'il n'y a pas de
   « avant » comparable. Coût nul, mais O-5 devient partiel.
3. Restreindre la comparaison au seul thème commun et aux métriques
   comportementales. Peu coûteux, peu informatif.

**Recommandation eXalt : option 2**, en documentant explicitement devant Cultura
que le changement de référentiel — leur décision, D-7 — rend la comparaison
thématique impossible par construction. L'option 1 fabriquerait un chiffre dont
la valeur dépendrait entièrement de la table de correspondance.

> ✅ **Arbitrage PO du 09/09 : option 2 retenue.** Aucune table de correspondance
> n'est construite. Les cibles de la famille A seront fixées en valeur absolue
> après le premier entraînement.

### Alerte 2 — un piège qui rendrait la baseline du sentiment faussement mauvaise

`src/utils/features.py` codait en dur `[SATISFACTION {score}/10]`, et rejetait
tout score hors 1-10. La livraison Cultura est sur une échelle **1-4** (D-20).

Sans correction, mesurer la baseline du sentiment sur les nouvelles données
présenterait un client **très satisfait (4/4)** à l'ancien modèle sous la forme
`[SATISFACTION 4/10]` — que son entraînement associe à l'**insatisfaction** (règle
`1-4 → Négatif` du prototype, vraie sans exception sur 7 000 lignes). La baseline
en sortirait artificiellement catastrophique, et le gain du nouveau modèle
artificiellement spectaculaire.

**Corrigé** : la borne est désormais lue en configuration
(`sentiment.satisfaction_scale_max`, ENF-8), laissée à **10** pour rester
cohérente avec les modèles actifs, et un garde-fou (`features.verifier_echelle`)
échoue si la configuration diverge de la carte d'entraînement.

**Reste à arbitrer — comment présenter la note à l'ancien modèle pour la baseline :**

| Option | Effet |
|---|---|
| `x/10` avec la note 1-4 brute | **À exclure** : biais systématique vers le négatif. |
| `x/4` | Format jamais vu à l'entraînement ; effet inconnu, à mesurer. |
| Rééchelonner 1-4 → 1-10 pour l'ancien modèle seulement | Le plus proche de la distribution d'entraînement. |
| Désactiver le préfixe des deux côtés | Supprime le facteur de confusion ; mesure la seule capacité textuelle. |

**Recommandation eXalt : mesurer la baseline du sentiment sans préfixe**
(`use_satisfaction_prefix: false`) **et** avec rééchelonnement, et publier les
deux. C'est la seule façon de savoir ce que le préfixe apporte réellement, ce que
personne n'a jamais mesuré.

> ✅ **Arbitrage PO du 09/09 : dénominateur `/10` conservé, note 1-4
> rééchelonnée** vers 1-10 (table `{1:1, 2:4, 3:7, 4:10}`, déclarée en
> configuration sous `baseline.reechelonnage_satisfaction`). Le bras de contrôle
> sans préfixe est mesuré et publié en parallèle. L'option « note brute dans
> `/10` » est écartée.

---

## 11. Décisions à porter au registre

Formulées pour être reprises telles quelles dans `docs/CADRAGE_NOUVEAU_MODELE.md` §8.

| # proposé | Décision | Rationnel mesuré |
|---|---|---|
| **D-36** *(09/09)* | **Il n'y a pas de baseline thématique du modèle actuel.** Aucune table de correspondance ancien → nouveau référentiel n'est construite. Les cibles de la famille A (§7.2) sont fixées en valeur absolue après le premier entraînement, et non en progression relative. La comparaison ancien/nouveau de L9 porte sur le sentiment et sur les métriques comportementales. | Les référentiels partagent **1 libellé de niveau 1 sur 20/11** (`Programme de fidélité`) et **0 sur 67/59** en niveau 2. Les espaces de labels étant disjoints, aucun F1 thématique n'est calculable. Conséquence directe de D-7 : le référentiel appartient à Cultura, qui l'a intégralement remplacé. |
| **D-37** *(09/09)* | **La baseline conserve le préfixe `[SATISFACTION x/10]` des modèles actifs, et la note Cultura 1-4 y est rééchelonnée** (1→1, 2→4, 3→7, 4→10). Un bras de contrôle sans préfixe est mesuré et publié. | Injecter la note brute présenterait un client très satisfait (4/4) comme `[SATISFACTION 4/10]`, que l'entraînement de l'ancien modèle associe au négatif (règle `1-4 → Négatif`, vraie sans exception sur 7 000 lignes du prototype). La baseline en sortirait artificiellement mauvaise et le gain du nouveau modèle artificiellement spectaculaire. |

**Conséquence pour L6 :** à l'entraînement sur les nouvelles données,
`sentiment.satisfaction_scale_max` passe à **4** et la valeur est inscrite dans
`training_card.json`. Le garde-fou `features.verifier_politique_prefixe()` échoue
si la configuration et la carte d'entraînement divergent.

### Arbitrages complémentaires du 09/09

| # proposé | Décision | Rationnel mesuré |
|---|---|---|
| **D-38** | **EF-3 est jugée sur les deux grandeurs, cumulativement.** Le nouveau modèle doit dépasser **0,8396 d'accuracy et 0,5725 de F1-macro** — les deux planchers atteints par la règle `note → sentiment`. | La règle bat le modèle actuel sur l'accuracy (0,8396 contre 0,8151) mais pas sur le F1-macro (0,5725 contre 0,6461), faute de pouvoir prédire *Neutre*. Retenir une seule grandeur permettrait de déclarer la réussite sur la moitié du problème. |
| **D-39** | **Le préfixe de satisfaction est conditionnel à la longueur du verbatim** : conservé sous 10 mots, retiré au-delà. Le seuil est calé sur la validation en L6. | Mesuré sur 1 128 verbatims : le préfixe apporte **+0,418 d'accuracy** sur 1-2 mots, où le texte ne porte aucun signal, et **en retire 0,157** au-delà de 20 mots, où il écrase un contenu nuancé. |
| **D-40** | **Sous-thème hors périmètre → `theme*_niv2` vide et revue humaine forcée.** Aucune colonne ajoutée à `OUTPUT_COLUMNS` ; la sémantique de la colonne s'élargit au vide. | Applique D-32 sans introduire de libellé hors référentiel (D-7, EF-5). À contrôler en recette L9 : le front, les exports et les tableaux de bord doivent tolérer un niv2 vide. |
| **D-41** | **Un seul modèle de signal est entraîné : `insatisfaction`** (887 exemples après fusion). `churn` et `rupture` restent au contrat de sortie, produits par règle, sans engagement de performance. | 64 et 32 positifs : à ces effectifs, tout intervalle de confiance est inexploitable. Publier une métrique reviendrait à publier du bruit. Hypothèse par défaut de Q-6. |

### Un gain de temps mesuré sur l'entraînement

`src/training/dataset.py` complétait chaque exemple à `max_length: 256` tokens.
Sur ce corpus, la médiane est de **10 tokens** et la moyenne de 16,7 : le
remplissage fixe faisait porter au calcul **15 fois** plus de tokens que
nécessaire.

| | seq. moyenne | s/pas (lot 16) | passe complète des 3 modèles |
|---|---|---|---|
| `padding="max_length"` | 256 | 2,891 | **4,0 h** |
| `padding=True` (dynamique) | 58 | 0,395 | **0,5 h** |

**Gain mesuré : ×7,3**, soit 3,4 heures récupérées par itération. Le résultat est
numériquement équivalent — le masque d'attention neutralise les positions
ajoutées, vérifié par égalité des sommes de masque. L'inférence, elle, utilisait
**déjà** le padding dynamique : c'est la seule raison pour laquelle la baseline
tourne à 25 verbatims/s.

> Conséquence pour le plan : « une passe complète des trois modèles se compte en
> heures » et « le plan ne tolère qu'un nombre très limité d'itérations » (L6) ne
> tiennent plus. **Q-7 (budget matériel d'entraînement) perd l'essentiel de son
> objet.**

---

*Projet interne Cultura / eXalt — usage confidentiel.*
