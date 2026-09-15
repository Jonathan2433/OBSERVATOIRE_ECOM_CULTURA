# Cadrage du nouveau modèle ML — Cultura Verbatim Classifier

> **Objet.** Transformer la demande Cultura (« un modèle plus pertinent, sur de nouveaux
> fichiers, avec de nouveaux comportements ») en exigences exécutables, testables et
> priorisées.
>
> **Statut.** v1.1 — 30 juillet 2026. Issu de l'entretien de cadrage du 30/07/2026 entre
> l'agent Product Owner et Jonathan Dupau (eXalt), puis d'une relecture critique qui a
> **corrigé le diagnostic du grief n°1** (cf. §1.4 e et §11).
> **Échéance projet.** 30 août 2026 (dimanche) — **22 jours ouvrés disponibles**, du
> jeudi 30/07 au vendredi 28/08 inclus. Le 15 août 2026 tombe un samedi : aucun jour ouvré
> perdu.
> **Document jumeau.** `docs/PLAN_LOTS_NOUVEAU_MODELE.md` (découpage, charges, chemin critique).
> **Socle de référence.** `docs/ETAT_DES_LIEUX_ML.md`.

---

## Sommaire

1. [Contexte et problème](#1-contexte-et-problème)
2. [Objectifs](#2-objectifs)
3. [Périmètre](#3-périmètre)
4. [Exigences fonctionnelles](#4-exigences-fonctionnelles)
5. [Exigences non fonctionnelles](#5-exigences-non-fonctionnelles)
6. [Contrat de sortie cible](#6-contrat-de-sortie-cible)
7. [Critères d'acceptation chiffrés](#7-critères-dacceptation-chiffrés)
8. [Registre de décisions](#8-registre-de-décisions)
9. [Hypothèses et questions ouvertes](#9-hypothèses-et-questions-ouvertes)
10. [Risques](#10-risques)
11. [Journal des corrections de ce document](#11-journal-des-corrections-de-ce-document)

---

## 1. Contexte et problème

### 1.1 Ce que Cultura reproche au modèle actuel

**Grief n°1, formulé par le métier : « la logique d'avoir la possibilité de 2 thèmes en
1 verbatim n'est pas respectée ».** Un verbatim qui mentionne deux sujets doit produire deux
thèmes, chacun avec son sous-thème et **son propre sentiment**. Exemple donné par le métier :
*« le paiement n'aboutit pas, mais j'ai facilement trouvé mon produit sur le site »* → thème 1 =
Tunnel de vente/Paiement **(négatif)** + thème 2 = Trouver son produit **(positif)**.

L'analyse détaillée en §1.4(e) montre que le défaut n'est **pas** l'absence du second thème,
mais **la recopie forcée du sentiment** et la mauvaise qualité du second thème produit.

### 1.2 Ce que l'usage métier rend critique

Cultura utilise les classifications pour **prioriser ses chantiers e-commerce** : si les
verbatims négatifs se concentrent sur la recherche de produit, la refonte de la recherche
passe en tête du plan d'action. La maille de décision est donc le **volume de verbatims par
couple (thème × sentiment)**.

Conséquence directe du grief n°1 : **les volumes qui servent à arbitrer les investissements sont
faussés**. Un second thème surnuméraire crée du volume fictif ; un sentiment recopié attribue
un verbatim « négatif » à un thème dont le client est en réalité satisfait. Le préjudice n'est
pas une métrique dégradée, c'est une décision d'investissement prise sur des chiffres biaisés —
et biaisés dans les deux sens.

### 1.3 Diagnostic mesuré du modèle actuel

Métriques publiées (`data/processed/eval_report.json`, 18/06/2026) :

| Métrique | Valeur | Cible CDC |
|---|---|---|
| F1-macro niv.1 | **0,564** | ≥ 0,70 ❌ |
| F1-micro niv.1 | **0,479** | – |
| Top-1 accuracy niv.1 | 0,830 | – |
| F1-macro niv.2 | 0,891 | – |
| Sentiment accuracy | **0,641** | – |
| Sentiment F1 classe *Neutre* | **0,360** | – |
| P(couple niv.1+niv.2 correct) | 0,757 | – |
| Taux de revue au seuil 0,50 / 0,65 | **9,8 % / 100 %** | seuil CDC 0,70 inexploitable |

### 1.4 Ce que l'analyse des données révèle — et qui invalide ce qui précède

Cinq mesures faites pendant le cadrage sur `data/raw/historique_labels_poc.xlsx`,
`data/processed/dataset.csv`, `data/output/_validation_classifications.csv` et
`src/evaluation/evaluate.py`. Elles changent la nature du projet.

**(a) Le jeu d'entraînement contient 403 verbatims uniques, pas 7 000.**
Chaque texte est dupliqué **17,4 fois en moyenne** (maximum 46). Le split stratifié 70/15/15
sépare correctement des *lignes*, mais pas des *textes*. Résultat mesuré :

- **99,6 % des lignes de test** (1 046 / 1 050) ont un texte **strictement identique** présent
  dans le train.
- **99,9 % des lignes de validation** (1 049 / 1 050) dans le même cas.

**Conséquence : toutes les métriques d'`eval_report.json` sont invalides.** Le F1-macro niv.2
de 0,891 ne mesure pas de la généralisation, il mesure la mémorisation de 403 phrases. **Il
n'existe aujourd'hui aucune baseline valide du modèle actuel.**

Corollaire aggravant pour le référentiel : `Click & Collect` est absorbé par `Suivi de commande
et livraison` dans **45 cas sur 62** — sur des textes que le modèle avait **déjà vus à
l'entraînement**. Un modèle qui n'arrive pas à discriminer deux thèmes en récitant par cœur a
un problème de **frontières de référentiel**, pas de capacité. Aucun réentraînement ne le
corrigera seul.

**(a bis) Les labels de signaux sont contradictoires sur un texte identique.**
Les libellés de thème et de sentiment sont, eux, parfaitement constants pour un texte donné
(0 incohérence sur 403). Mais **213 des 403 textes uniques portent des valeurs contradictoires
de `signal_churn` et de `signal_insatisfaction_forte`** : la même phrase est étiquetée à la
fois churn et non-churn selon la ligne. Un texte porte également des `signal_rupture_client`
contradictoires. Les modèles de signaux ont donc été entraînés sur du bruit d'étiquetage pur,
sur plus de la moitié du vocabulaire du jeu.

**(b) Le sentiment est une fonction déterministe de la note de satisfaction.**
Mesuré sur les 7 000 lignes, **sans une seule exception** :

| Note de satisfaction | Sentiment annoté |
|---|---|
| 1 – 4 | Négatif (2 400 cas) |
| 5 – 7 | Neutre (2 319 cas) |
| 8 – 10 | Positif (2 281 cas) |

Un `if/else` de trois lignes atteint 100 %. Le modèle CamemBERT, à qui cette note est pourtant
injectée en préfixe textuel (`[SATISFACTION 3/10] …`), atteint **0,641**. Il n'y a pas de
tâche de sentiment dans ces données : il y a une règle, et le modèle échoue à la reproduire.

**(c) Le comportement demandé n'a aucun exemple d'apprentissage.**
Sur les 28 lignes bi-thèmes, soit **11 textes uniques** :

- **0 verbatim** porte des sentiments divergents entre thème 1 et thème 2 (22 cas
  Négatif/Négatif, 6 cas Positif/Positif).
- L'exemple fondateur du métier (« paiement KO **mais** recherche facile ») n'existe nulle part.

Le référentiel produit par ailleurs des contradictions d'annotation vérifiables : le verbatim
*« Application mobile fluide et recommandations pertinentes. Je reviens souvent. »* (ligne 1488)
est étiqueté thème 2 = **« Recommandations non pertinentes »** avec sentiment **Positif**.
L'annotateur a dû coller un libellé négatif sur un retour élogieux, faute de libellé adéquat.
Le seul sous-thème positif du référentiel, `Facile`, plafonne à **F1 0,154**.

**(d) Redondance des signaux, confirmée.**
`signal_churn` est un sous-ensemble quasi parfait de `signal_insatisfaction_forte` :
1 794 positifs communs, **2 exceptions** sur 7 000. Les métriques publiées sont identiques
**à deux décimales** (précision 0,744/0,745 · rappel 0,993/0,993 · F1 0,850/0,851 ·
AUC 0,9315/0,9310). `signal_rupture_client` ne compte que 0,41 % de positifs (29 cas) et
**1 seul cas positif dans le test** — non évaluable.

**(e) CORRECTION MAJEURE — le modèle sur-active les thèmes, il ne les sous-active pas.**

L'hypothèse initiale de ce cadrage était que le modèle produit un seul thème dans la quasi-
totalité des cas. **Elle est fausse.** Trois éléments concordants :

1. `src/evaluation/evaluate.py` calcule le F1-micro sur `niv1_probs >= 0.35`, **sans appliquer
   le plafond `max_themes`**. Avec un rappel micro de 0,830 et un F1-micro de 0,479, la
   précision micro implicite est de **0,336** — soit **environ 2,5 thèmes activés par verbatim**
   au seuil de 0,35. Après plafonnement à 2, le modèle en émet donc deux très fréquemment.
2. La seule sortie réelle du prédicteur présente au dépôt
   (`data/output/_validation_classifications.csv`, 120 verbatims) comporte **43,3 % de sorties à
   deux thèmes** (52 sur 120).
3. Sur ces 52 sorties bi-thèmes, **0 porte des sentiments divergents**. Zéro sur 52. Le code le
   confirme : `build_output` (`src/inference/predictor.py`, l. 77-93) calcule un unique
   `sent_idx` et l'applique tel quel à chaque thème.

**Le grief n°1 se relit donc ainsi :** le second thème est bien produit ; ce qui échoue, c'est
(i) **le sentiment, recopié de force** depuis le premier thème, et (ii) **la justesse du second
thème**, le seuil de 0,35 sur-déclenchant massivement. Dans l'exemple du métier, « j'ai
facilement trouvé mon produit » n'est pas absent — il ressort étiqueté **Négatif**.

**Conséquence favorable pour le projet** : le mécanisme multi-thème fonctionne mécaniquement.
Ce qui manque est un correctif d'ingénierie sur le sentiment, plus un recalibrage de seuil —
pas des milliers d'exemples bi-thèmes. Le risque R-1 est reclassé de *critique* à *élevé*, et
les critères d'acceptation basculent du **rappel** du second thème vers sa **précision**
(§7.2 famille B).

### 1.5 Formulation du problème

> Le modèle actuel n'est pas « perfectible » : il est **non mesuré**. Le projet doit établir une
> mesure honnête avant de prétendre améliorer quoi que ce soit.
>
> Sur le fond, le défaut central n'est pas un manque de puissance mais **trois défauts de
> conception cumulés** : un sentiment unique recopié sur des thèmes qui peuvent être de
> polarités opposées ; un seuil d'activation multi-label non calibré qui produit des seconds
> thèmes parasites ; et un référentiel dont les frontières se recouvrent au point que le modèle
> échoue à discriminer des textes qu'il a mémorisés. Aucun de ces trois défauts ne se corrige
> par un simple réentraînement sur de nouvelles données.

---

## 2. Objectifs

Formulés en résultats métier. La colonne « porté par » assure la traçabilité vers le plan de lots.

| # | Objectif | Traduction opérationnelle | Porté par |
|---|---|---|---|
| **O-1** | Quand un client parle de deux sujets, Cultura voit les deux — et seulement quand c'est vrai | Le second thème est remonté quand il existe, et **pas** quand il n'existe pas | L5, L6 |
| **O-2** | Quand un client est mécontent d'un sujet et satisfait d'un autre, Cultura le voit | Chaque thème porte son propre sentiment | L5, L6 |
| **O-3** | Cultura peut prioriser ses chantiers sur des volumes fiables | L'erreur sur les volumes agrégés par (thème × sentiment) est mesurée et bornée | L2, L6 |
| **O-4** | Le métier sait combien de verbatims il doit relire, et peut régler ce curseur | Confiance calibrée, taux de revue pilotable entre 10 et 15 % | **L7 — conditionnel** |
| **O-5** | Le progrès est démontrable | Baseline sans fuite, protocole reproductible, comparaison ancien/nouveau chiffrée | L2, L9 |
| **O-6** | Le modèle s'améliore d'un mois sur l'autre | Les corrections de la revue humaine deviennent la source d'annotation | **L10 — conditionnel** |

> **Alerte de gouvernance.** O-4 et O-6 sont portés par les deux seuls lots déclarés
> abandonnables du plan. Si l'échéance se tend, ces deux objectifs tombent. À assumer
> explicitement devant Cultura, ou à re-prioriser.

---

## 3. Périmètre

### 3.1 Dans le périmètre

**Ferme :**

- Audit des nouveaux fichiers et du nouveau référentiel Cultura.
- Reconstruction du protocole d'évaluation (déduplication, split sans fuite) et établissement
  d'une **baseline honnête** du modèle actuel.
- Multi-thème correct : recalibrage du seuil d'activation multi-label, mesure de la précision et
  du rappel du second thème, et de la distribution du nombre de thèmes en sortie.
- **Sentiment conditionné au thème** : nouvelle entrée du modèle de sentiment.
- Réentraînement des modèles CamemBERT sur les nouvelles données.
- Redéfinition métier des signaux avant réentraînement.
- Règles d'arbitrage entre thèmes voisins et guide d'annotation.
- Mesure et optimisation du débit pour tenir 11 000 verbatims en 1 à 2 h.
- Mise à jour du prompt du moteur LLM local sur le nouveau référentiel, et vérification du
  switch multi-moteur.
- Recette comparative ancien / nouveau modèle et mise en production.

**Conditionnel — abandonnable si l'échéance se tend :**

- Calibration du score de confiance et réglage du taux de revue (L7 — porte O-4, EF-6, EF-7).
- Outillage de la boucle « corrections de revue → jeu d'entraînement » (L10 — porte O-6, EF-10).
- Refonte de l'encodage vers une clé composite (L11 — activé seulement si Q-5 est négative).
- Campagne d'annotation complémentaire (L13 — activé seulement si L1 révèle un déficit).

### 3.2 Hors périmètre — explicitement

| Hors périmètre | Motif |
|---|---|
| Plus de 2 thèmes par verbatim | D-2. |
| Sortie « hors sujet / non classable » côté CamemBERT | Non demandé au cadrage. La sentinelle existe déjà côté moteurs LLM. |
| Extraction d'entités (produit, magasin, motif, canal) | Non demandé au cadrage. |
| Synthèse ou regroupement automatique de verbatims | Non demandé au cadrage. |
| Détection d'émergences et de drift | Non demandé au cadrage. À porter à la trajectoire post-30/08. |
| Refonte complète du référentiel par eXalt | D-7 : le référentiel est fourni par Cultura. |
| Réentraînement automatique en production | Garde-fou du cahier des charges, maintenu (D-11). |
| Changement de moteur principal vers un LLM | D-3 : écarté par la contrainte de débit de 1-2 h. |
| Sortie du mono-poste (serveur, multi-utilisateur, cloud) | Contrainte d'exploitation inchangée. |
| Assouplissement de l'offline strict en production | Contrainte RGPD et CDC inchangée. |
| Refonte de l'interface web | Seules les évolutions rendues nécessaires par le contrat de sortie. Voir toutefois Q-15 (dashboards). |
| Correction du mécanisme de saisie libre de thèmes en revue | Voir R-12 : le défaut est identifié, sa correction n'est pas provisionnée. |

---

## 4. Exigences fonctionnelles

Chacune est testable. Les exigences marquées **[C]** sont conditionnelles à un lot abandonnable
ou à une question ouverte : elles ne doivent pas être présentées à Cultura comme des engagements
fermes.

| # | Exigence | Vérifiable par |
|---|---|---|
| **EF-1** | Un verbatim mentionnant deux sujets distincts produit deux thèmes, chacun avec son sous-thème valide au regard du référentiel. Un verbatim mono-sujet n'en produit qu'un. | Précision et rappel du second thème mesurés sur le jeu de recette ; jeu de cas limites incluant l'exemple fondateur. |
| **EF-2** *(reformulée le 09/09 — D-26)* | Sur un verbatim mêlant un aspect négatif et un aspect positif, **seul le thème négatif est retourné**. Le sentiment reste unique par verbatim. | Jeu de cas mixtes dans la recette ; contrôle que le thème positif n'est pas remonté et que le sentiment retenu est le négatif. **Référence mesurée : les bi-thèmes annotés sont négatifs à 72,6 % contre 25,5 % pour les mono-thèmes — la règle est déjà dans les labels.** *Version initiale (« chaque thème porte son propre sentiment ») abandonnée : sans annotation au niveau du thème, elle n'était ni entraînable ni mesurable.* |
| **EF-3** | Le sentiment n'est pas déductible de la seule note de satisfaction : il est déterminé par le texte. | Test de non-trivialité : la règle `note → sentiment` doit avoir une précision strictement inférieure à celle du modèle. **Mesurable et non trivial, confirmé le 09/09** : l'échelle réelle compte 4 modalités et la note 3 est authentiquement ambiguë (537 négatifs, 431 positifs, 71 neutres). R-5 ne se réalise pas ; l'exigence n'est plus conditionnelle. |
| **EF-4** | La distribution du nombre de thèmes en sortie est cohérente avec la distribution annotée. | Distribution `nb_themes` en sortie comparée à la distribution annotée du jeu de recette. **Référence de départ mesurée : 43,3 % de sorties bi-thèmes contre 0,4 % d'annotations bi-thèmes.** |
| **EF-5** | Le **modèle** ne produit jamais de couple (niv.1, niv.2) hors référentiel. | Garde-fou existant (masquage hiérarchique) reconduit ; test automatisé sur l'intégralité d'un lot. **Portée restreinte au modèle** : voir R-12, la revue humaine permet déjà d'enregistrer des couples hors référentiel via `taxonomy_entries`. |
| **EF-6** **[C]** | Le score de confiance est calibré : une confiance de *p* correspond à une justesse observée de ≈ *p*. | Courbe de fiabilité et ECE mesurées sur le jeu de recette. **Conditionnel à L7.** |
| **EF-7** **[C]** | Le seuil de revue humaine est réglable et produit un taux de revue monotone et exploitable entre 5 % et 30 %. | Table taux de revue / seuil sur au moins 6 seuils ; aucun saut de plus de 20 points entre deux seuils consécutifs. **Conditionnel à L7.** |
| **EF-8** | Les signaux produits correspondent à des définitions opérationnelles écrites, chacune associée à une action métier distincte. | `docs/DEFINITION_SIGNAUX.md` validé par le métier ; absence de deux signaux à métriques équivalentes. |
| **EF-9** | Le moteur LLM local reste sélectionnable et fonctionne avec le nouveau référentiel. | Recette du moteur LM Studio sur le nouveau référentiel ; switch de moteur testé en administration. |
| **EF-10** **[C]** | Les corrections saisies en revue humaine sont exportables en jeu d'entraînement, distinct d'un jeu de recette gelé. | Deux fichiers produits, schémas documentés, disjonction des identifiants vérifiée. **Conditionnel à L10.** |
| **EF-11** | Les volumes agrégés par (thème × sentiment) sont comparables aux volumes annotés, avec un écart mesuré. | Tableau d'écart par thème sur le jeu de recette. |
| **EF-12** | Le modèle est activable en production via l'administration, avec traçabilité. | Mécanisme existant (`sync_registry`, audit) reconduit et testé. |

---

## 5. Exigences non fonctionnelles

| # | Exigence | Valeur | Commentaire |
|---|---|---|---|
| **ENF-1** | Débit | 11 000 verbatims en **1 à 2 h** | D-4. Révise le DoD « < 1 h », jamais mesuré. Point dur : le sentiment par thème porte le nombre de passages transformer de 4 à **4 ou 5** par verbatim — 5 uniquement pour les verbatims bi-thèmes, dont la proportion réelle reste à mesurer (L1). |
| **ENF-2** | Matériel de production | Laptop macOS Apple Silicon, CPU seul, ≥ 16 Go RAM | Inchangé. |
| **ENF-3** | Réseau en production | Hors ligne strict, aucune télémétrie | Inchangé. |
| **ENF-4** | Matériel d'entraînement | Non contraint par l'architecture | L'entraînement est une opération CLI hors application. Une machine plus puissante est possible sans violer l'offline de production — voir Q-7. |
| **ENF-5** | RGPD | Anonymisation en tête de pipeline, base sans verbatim brut, rétention 13 mois | Inchangé. Voir R-14 : la qualité de l'anonymisation n'est mesurée par aucun lot. |
| **ENF-6** | Anonymisation | Identique à l'entraînement et à l'inférence | Mode dégradé silencieux si spaCy est absent (T5). Voir R-14. |
| **ENF-7** | Reproductibilité | Seed fixe, artefacts versionnés, carte d'entraînement par version | Mécanisme `CURRENT` + `training_card.json` reconduit. |
| **ENF-8** | Configuration | Aucun nombre magique dans le code ; tout dans `config/config.yaml` | Inchangé. |
| **ENF-9** | Résilience de lot | Un verbatim défaillant n'interrompt pas le lot ; annulation coopérative | Mécanisme existant reconduit. |
| **ENF-10** | Perf UI | Écran < 3 s, recherche/filtre < 2 s sur 11 000 | Inchangé. |

---

## 6. Contrat de sortie cible

**Point favorable majeur** : `theme2_sentiment` existe **déjà** dans `OUTPUT_COLUMNS`
(`src/inference/predictor.py`, l. 35), dans la table `results`, dans les exports CSV/XLSX et
dans le front. Les moteurs LLM (`app/worker/llm_common.py`, l. 54-57) produisent déjà un
sentiment propre à chaque thème dans leur schéma JSON, et un garde-fou déclenche la revue en
cas de divergence — précisément lorsque les deux sentiments diffèrent **et** que l'un est
Négatif (l. 342-344). **C'est uniquement CamemBERT qui recopie un sentiment unique sur les deux
thèmes** (l. 77-93).

Conséquence : l'exigence EF-2, cœur de la demande, a un **coût de propagation applicative nul**.

| Colonne | Aujourd'hui | Cible | Écart | Coût de propagation |
|---|---|---|---|---|
| `verbatim_analysé` | anonymisé + nettoyé | inchangé | – | nul |
| `nb_themes` | 0–2 | inchangé, mais **distribution corrigée** (EF-4) | comportement, pas schéma | nul |
| `theme1_niv1` / `theme1_niv2` | libellés référentiel | libellés du **nouveau** référentiel | dépend de Q-2 | nul si les libellés changent, **élevé si l'unicité niv.2 est cassée** (Q-5 → L11) |
| `theme1_sentiment` | sentiment du verbatim | sentiment **du thème 1** | changement de sémantique | nul sur le schéma ; à documenter pour le métier |
| `theme1_score_confiance` | proba sigmoïde niv.1 | inchangé | – | nul |
| `theme2_niv1` / `theme2_niv2` | libellés référentiel | idem thème 1 | – | nul |
| `theme2_sentiment` | **recopie de theme1** (0 divergence sur 52 cas mesurés) | sentiment **propre au thème 2** | changement de comportement | **nul** — la colonne existe déjà partout |
| `theme2_score_confiance` | `""` si mono-thème | `0.0` si mono-thème | correction d'incohérence de typage (T9) | faible ; à vérifier côté front et exports |
| `signal_rupture_client` | booléen | à confirmer (D-10) | dépend de Q-6 | nul si conservé, **modéré si supprimé** |
| `signal_churn` | booléen | à confirmer (D-10) | dépend de Q-6 | idem |
| `signal_insatisfaction_forte` | booléen | à confirmer (D-10) | dépend de Q-6 | idem |
| `confidence_globale` | moyenne non pondérée de 3 échelles incomparables | score **calibré** **[C, L7]** | changement de sémantique, mêmes bornes | nul sur le schéma ; les seuils en base et les **dashboards** doivent être revus — charge non provisionnée, voir Q-15 |
| `revue_humaine_requise` | booléen sur seuil 0,50 | booléen sur seuil calibré **[C, L7]** | – | nul |

**Aucune colonne ajoutée, aucune supprimée** dans la cible, sous réserve de D-10 (signaux) et
de Q-5 (unicité des libellés de niveau 2). C'est le résultat le plus rassurant du cadrage : le
nouveau comportement demandé tient dans le contrat existant.

---

## 7. Critères d'acceptation chiffrés

### 7.1 Jeu d'évaluation et protocole

Sans ce protocole, aucun chiffre ci-dessous n'a de sens. Il constitue le lot L2 du plan.

1. **Déduplication stricte** des textes avant tout split. Un texte apparaît dans un seul split.
2. **Split par texte unique**, pas par ligne. Vérification automatisée : l'intersection des
   ensembles de textes entre train, validation et test doit être **vide**. Ce test devient
   bloquant dans la chaîne de préparation.
3. **Jeu de recette gelé**, jamais utilisé pour l'entraînement ni pour le réglage des seuils,
   contenant obligatoirement :
   - des verbatims mono-thème et bi-thèmes dans leur proportion réelle observée ;
   - des cas à **sentiments divergents** entre les deux thèmes ;
   - des cas sur les frontières poreuses identifiées (retrait en magasin, rupture, annulation) ;
   - des verbatims vides, très courts et très longs.
4. **Évaluation séparée par source** (MDTC / Mopinion) — absente aujourd'hui (L9 de l'état
   des lieux), alors que les schémas et les styles rédactionnels diffèrent.
5. **Mesure du débit** sur un lot réel de 11 000 verbatims, chronométrée de bout en bout.
6. **Correction du calcul du F1-micro** : `evaluate.py` l'évalue aujourd'hui avant plafonnement
   à `max_themes`, ce qui masquait la sur-activation (§1.4 e). L'évaluation doit rejouer la
   décision réelle, plafond inclus.

### 7.2 Cibles

Deux familles de cibles, conformément à D-12. Les valeurs marquées *(à valider)* sont des
propositions eXalt argumentées, à confirmer par Cultura (Q-9).

**Famille A — justesse de la classification**

| Critère | Cible | Justification |
|---|---|---|
| F1-macro niveau 1 | **à fixer après la baseline honnête (L2)** | La valeur de 0,564 est invalide (fuite 99,6 %). Cible indicative *(à valider)* : progression relative de +20 % sur la baseline mesurée. |
| P(couple niv.1 + niv.2 correct) | ≥ baseline + 10 points *(à valider)* | Métrique la plus proche de l'usage. |
| Aucun couple hors référentiel **produit par le modèle** | **0, strict** | Garde-fou CDC, non négociable. Portée restreinte au modèle : voir R-12. |

**Famille B — le nouveau comportement (grief n°1)**

Cette famille a été **réécrite** après la correction du diagnostic (§1.4 e) : la priorité
n'est pas de faire apparaître un second thème, mais de le rendre juste et de lui donner son
propre sentiment.

| Critère | Cible | Justification |
|---|---|---|
| **Divergence de sentiment possible et produite** entre les deux thèmes | Strictement **> 0** sur les cas annotés divergents du jeu de recette | Point de départ mesuré : **0 sur 52**. C'est le critère binaire de réussite de EF-2. |
| Justesse du sentiment **par thème** | ≥ **0,75** *(à valider)* | À mesurer par thème, pas globalement. |
| **Précision du second thème** quand il est remonté | ≥ **0,70** *(à valider)* | **Le critère central du projet.** Point de départ : la précision micro implicite du niveau 1 est de **0,336** — le second thème est majoritairement parasite, et il pollue les volumes de priorisation. |
| Taux de faux second thème sur les verbatims réellement mono-thème | ≤ **15 %** *(à valider)* | Point de départ mesuré : 43,3 % de sorties bi-thèmes pour 0,4 % d'annotations bi-thèmes. |
| Rappel du second thème sur les verbatims réellement bi-thèmes | ≥ **0,60** *(à valider, sous réserve de mesurabilité)* | Complément du critère précédent. **Mesurabilité conditionnée à R-1 / Q-3** : si le jeu de recette contient trop peu de cas bi-thèmes annotés, ce critère devient indicatif et non contractuel. |
| **Non-trivialité du sentiment** (EF-3) | La règle `note → sentiment` doit être strictement moins bonne que le modèle | **Conditionnel à R-5.** Si les nouvelles données reproduisent la règle, ce critère est inatteignable et devient un constat à remonter à Cultura. |

**Famille C — exploitation**

| Critère | Cible | Justification |
|---|---|---|
| Erreur relative sur les volumes agrégés par (thème × sentiment) | ≤ **15 %** par thème *(à valider)* | C'est la maille de décision de Cultura (O-3). |
| Taux de revue humaine au seuil retenu **[C, L7]** | **10 à 15 %** | D-9. |
| Monotonie du seuil de revue **[C, L7]** | Aucun saut > 20 points entre deux seuils consécutifs | Corrige le défaut actuel (9,8 % à 0,50 puis 100 % à 0,65). |
| ECE **[C, L7]** | ≤ **0,10** *(à valider)* | Aucune calibration n'existe aujourd'hui. |
| Débit | 11 000 verbatims en **≤ 2 h**, mesuré | ENF-1. |
| Non-régression applicative | Recettes **V1, V3, V4, V5 et V6** au vert | 48/48, 13/13, 50/50, 112/112 aujourd'hui. **V6 (`app/tests/recette_v6.py`, saisie libre de thèmes en revue + export filtré) était absente de l'état des lieux et doit être intégrée au périmètre de non-régression.** |

---

## 8. Registre de décisions

Toutes prises le **30 juillet 2026** lors de l'entretien de cadrage, sauf mention contraire.

| # | Décision | Rationnel |
|---|---|---|
| **D-1** | **Chaque thème porte son propre sentiment.** | Conséquence logique de l'exemple fondateur du métier. Coût applicatif nul (`theme2_sentiment` existe déjà partout, les moteurs LLM le produisent déjà). Défaut mesuré : 0 divergence sur 52 sorties bi-thèmes. Écarte l'option « sentiment global unique », qui attribuerait un verbatim négatif à un thème dont le client est satisfait — faussant la priorisation. |
| **D-2** | **Plafond maintenu à 2 thèmes**, 1 ou 2 selon le verbatim. | *Rationnel révisé le 30/07 après §1.4(e).* Le plafond de 2 est déjà atteint dans 43,3 % des sorties mesurées : le problème n'est ni le plafond, ni son inatteignabilité, mais la **justesse** du second thème. Étendre à 3-4 thèmes aggraverait la sur-activation avant de l'avoir corrigée. Garder 2 évite toute évolution de `OUTPUT_COLUMNS`, de la table `results`, des exports et du front. |
| **D-3** | **Moteur principal = CamemBERT réentraîné.** Le moteur LLM local est conservé comme moteur alternatif, avec un prompt refait sur le nouveau référentiel. **Le switch multi-moteur reste en place.** | Imposé par D-4 : un LLM local ne tient pas 1-2 h sur 11 000 verbatims. Contrepartie assumée en R-1 : ce choix fait dépendre la qualité du résultat des nouvelles données. |
| **D-4** | **Débit cible : 1 à 2 h pour 11 000 verbatims.** Révise le DoD « < 1 h ». | Le « < 1 h » n'a jamais été mesuré, même à 4 passages transformer par verbatim. Le sentiment par thème en ajoute un cinquième **pour les seuls verbatims bi-thèmes**. 1-2 h est la contrainte métier réelle exprimée. |
| **D-5** | **Décision sur les frontières poreuses de niveau 1 reportée après l'audit (L1).** Elle doit être **prononcée au plus tard le 5 août**, à la clôture de L1 (jalon de décision du plan de lots). | La matrice de confusion sur les **vraies** données dira quelles frontières posent problème en production. Le report ne doit pas être sine die : sans décision au 5 août, le référentiel entre en entraînement avec ses ambiguïtés (R-9). |
| **D-6** | **Recommandation** : libellés de sous-thèmes **neutres**, la polarité étant portée par le sentiment (« Recherche produit » et non « Recherche peu efficace »). | Élimine `Facile` (F1 0,154) et les contradictions d'annotation du type « Recommandations non pertinentes / Positif », et évite de dédoubler le référentiel alors que D-1 fournit déjà l'axe de polarité. **Statut : recommandation, non décision** — voir D-7 et Q-4. |
| **D-7** | **Le référentiel de thèmes est fourni par Cultura.** eXalt ne le modifie pas unilatéralement. | Position confirmée par le PO. **Réserve identifiée** : le mécanisme de saisie libre de thèmes en revue (`taxonomy_entries`, recette V6) permet déjà à tout relecteur d'enregistrer un couple hors référentiel. La décision est donc déjà contournée dans l'application livrée — voir R-12. |
| **D-8** | **L'historique de 7 000 verbatims est écarté de l'entraînement et de l'évaluation.** Conservé uniquement comme jeu de fumée technique de la chaîne. | 403 textes uniques dupliqués 17,4 fois, fuite train/test de 99,6 %, sentiment réduit à une règle sur la note, labels de signaux contradictoires sur 213 des 403 textes, style artificiel (29-90 caractères, moyenne 61,6, aucune faute). Le conserver apprendrait au modèle à réciter et rendrait toute mesure de progrès impossible. Écarte aussi la fusion après déduplication : les 403 textes restants tireraient le modèle vers un français qui n'existe pas dans les vrais verbatims. *Note : `dataset_stats.json` recense 302 masquages `[NOM]` pour 0 email, 0 téléphone et 0 numéro de commande ; ces 302 détections sont vraisemblablement des faux positifs spaCy sur des majuscules de début de phrase, ce qui constitue une destruction de texte à l'entraînement — voir R-14.* |
| **D-9** | **Taux de revue humaine cible : 10 à 15 %, avec un seuil réellement pilotable.** | Soit 1 100 à 1 650 verbatims par mois. Exige que la confiance soit calibrée, ce qui n'est le cas nulle part aujourd'hui. **Porté par L7, lot conditionnel** : à ne pas présenter comme un engagement ferme du 30 août. |
| **D-10** | **Les signaux métier sont redéfinis depuis le besoin métier avant tout réentraînement.** | `churn` et `insatisfaction` sont le même signal dans les données (1 794 positifs communs, 2 exceptions sur 7 000 ; métriques identiques à deux décimales). `rupture` n'est pas évaluable (1 positif en test). Et 213 des 403 textes uniques portent des labels de signaux contradictoires : le bruit d'étiquetage est massif. Si deux signaux déclenchent la même action, un seul doit être produit. |
| **D-11** | **Les corrections de la revue humaine deviennent la source d'annotation du projet.** Réentraînement **manuel et validé** — jamais automatique. | D-8 supprime 7 000 exemples ; la revue produit 1 100 à 1 650 verbatims corrigés par mois, soit 13 000 à 20 000 exemples annotés par an, déjà payés, aujourd'hui jamais réutilisés. Le garde-fou CDC est maintenu. Biais d'auto-confirmation à traiter (R-11). **Porté par L10, lot conditionnel.** |
| **D-12** | **Les objectifs chiffrés sont adossés à l'usage réel**, en trois familles : justesse du thème, qualité du second thème et de son sentiment, erreur sur les volumes agrégés. | Écarte le maintien du seul « F1-macro niv.1 ≥ 0,70 » : ce chiffre est invalide faute de baseline, et une cible atteinte sur le thème principal serait compatible avec un second thème toujours parasite — donc avec le grief n°1 intact. |
| **D-13** | **Échéance : 30 août 2026. Livrable : le nouveau modèle en production, utilisé par le métier.** | Décision du PO. 22 jours ouvrés. **Réserve portée par eXalt** : le plan de lots démontre que cet engagement n'est pas tenable avec l'équipe décrite en D-14, sans seconde ressource technique (R-2, Q-14). Un scénario de repli est spécifié au §4.5 du plan de lots — livraison d'un modèle mesuré et présentable au 30/08, mise en production en septembre. Ce repli doit être arbitré avec Cultura, pas découvert le 27 août. |
| **D-14** | **Périmètre complet maintenu ; l'équipe est renforcée.** Équipe déclarée : 1 data scientist, le PO, l'agent, 2 personnes côté métier. | Décision du PO, contre l'alternative de reporter la calibration. **La prémisse n'est pas satisfaite** : l'équipe décrite ne comporte aucune seconde ressource technique, alors que le fil du data scientist est chiffré à ≈ 23,5 jours-homme sur 22 jours ouvrés. Voir R-2 et Q-14. |
| **D-15** | **Le grief n°1 est le multi-thème incorrect**, pas la performance brute du niveau 1. | *Formulation corrigée le 30/07 après §1.4(e) :* le second thème est produit, mais son sentiment est recopié et sa précision est faible. Réordonne les priorités du plan de lots vers L5. |
| **D-16** | **L'usage métier est la priorisation des chantiers e-commerce** par volumes de (thème × sentiment). | Détermine la famille C des critères d'acceptation et explique pourquoi un second thème parasite comme un sentiment recopié sont des préjudices, pas des défauts cosmétiques. |
| **D-17** *(12/08)* | **Un verbatim par champ libre rempli**, et non un verbatim concaténé par répondant. | Les nouveaux formulaires comportent jusqu'à 4 champs libres distincts, posés par des questions différentes (« Produits non trouvé », « Suggestions d'amélioration »…). Concaténer forcerait le modèle à redécouvrir dans le texte une séparation que le formulaire fournit déjà. **Une part du multi-thème devient structurelle plutôt qu'inférée** — c'est la voie la plus directe vers O-1. Coût : le nombre de lignes à traiter augmente (tension sur ENF-1), et le regroupement par répondant doit être géré en base et à l'export. |
| **D-18** *(12/08)* | **Ingestion restreinte des métadonnées** : `page_type`, `url` et `device` seulement. Les liens de rejeu de session Contentsquare, les captures d'écran, le HTML de page, l'agent utilisateur et la colonne e-mail sont **écartés dès le chargeur**. | `page_type` est la seule colonne renseignée à 100 % des lignes et localise directement l'irritant — valeur métier immédiate pour D-16. Les colonnes écartées sont des données personnelles indirectes sans usage pour la classification ; les stocker élargirait le périmètre RGPD sous rétention 13 mois, contre le principe « seul le verbatim anonymisé est en base ». La liste des colonnes ingérées doit rester configurable (Q-19). |
| **D-19** *(12/08)* | **Les sujets cochés par le client dans les formulaires Mopinion servent d'étiquettes de départ** pour l'entraînement. | Change l'économie du projet : chaque réponse Mopinion devient un exemple d'apprentissage sans annotation manuelle, ce qui neutralise en grande partie R-1 côté Mopinion et rend L13 optionnel sur cette source. **Deux garde-fous obligatoires, non négociables** : (i) mesurer le taux de désaccord entre le sujet coché et le texte écrit sur un échantillon relu à la main, faute de quoi on entraîne sur les erreurs de saisie des clients à grande échelle (R-15) ; (ii) **MDTC ne possède aucune de ces colonnes** — l'évaluation séparée par source devient obligatoire et non optionnelle (R-16). |
| **D-20** *(12/08)* | **Le niveau de satisfaction alimente le modèle, normalisé entre sources.** Le score RECO n'est pas retenu. | Le niveau de satisfaction porte sur l'expérience vécue ; le RECO mesure l'intention de recommander la marque, ce qui peut diverger du sentiment du verbatim. Trois échelles à réconcilier : 4 modalités textuelles (MDTC), 0-10 (RECO, écarté), 1-5 (Mopinion). Table de conversion à écrire et à faire valider (Q-17, sollicitation A6). Vigilance : ne pas reproduire la circularité du jeu actuel, où le sentiment était intégralement déductible de la note. *Confirmé le 09/09 : l'échelle réelle compte 4 modalités et la circularité ne se reproduit pas (§5.1 de l'audit).* |
| **D-21** *(12/08)* | **La démonstration du 28 août porte sur la non-régression applicative** : l'application reste fonctionnelle après changement de moteur ML, incluant le changement de structure des fichiers sources et l'ajout de fichiers. | Décision du PO. Recentre le livrable du **ML** vers l'**intégration**, et sort du périmètre tout ce qui relève de la qualité : calibration de la confiance, réglage fin du seuil, optimisation du débit. Une performance de modèle sur données factices n'aurait de toute façon rien démontré. |
| **D-22** *(12/08)* | **eXalt conçoit les jeux de données factices.** | Décision du PO. Livrables : `docs/SPEC_JEU_FACTICE.md`, `scripts/fake_textgen.py`, `scripts/generate_fake_dataset.py`. Porté hors du fil du data scientist. |
| **D-23** *(12/08)* | **L'annotation des données réelles se fait début septembre.** | Décision du PO. *Devenue sans objet le 09/09 : Cultura a livré des données déjà annotées — 7 068 annotations. Voir D-29.* |
| **D-24** *(12/08)* | **Jeu factice : ≈ 1 500 verbatims uniques, couverture complète du référentiel.** | Volume modeste assumé. L'objectif est la couverture et le fonctionnement, pas l'apprentissage : le modèle issu de ce jeu sera faible et doit être présenté comme tel. Entraînement et itérations rapides, ce qui protège le calendrier. Écarte 5 000 verbatims, qui auraient créé la tentation de communiquer des chiffres ne mesurant que notre capacité à générer des données apprenables. |
| **D-25** *(12/08)* | **Le jeu factice contient un lot de cas pièges explicite et documenté.** | 55 cas produits, chacun inscrit au manifeste avec son comportement attendu : verbatims vides, très longs, majuscules, fautes, emojis, PII au format `P########`, hors-sujet, homonymie de sous-thèmes, frontières poreuses, trois sujets, défauts de fichier. Une chaîne qui ne traite que des cas propres ne prouve rien — c'est la logique qui a masqué les défauts du prototype pendant deux mois. |
| **D-26** *(09/09)* | **Sur un verbatim à sentiments divergents, seul le thème négatif est retenu.** Le thème positif est écarté. Le sentiment reste **unique par verbatim**. | Décision du PO, **validée empiriquement** : les bi-thèmes annotés sont négatifs à **72,6 %** contre **25,5 %** pour les mono-thèmes — 47 points d'écart. La règle est donc **déjà appliquée par les annotateurs Cultura**, et le modèle l'apprendra par simple supervision, sans mécanisme spécifique. Cohérent avec D-16 : un thème positif n'appelle aucune action de priorisation. **Trois conséquences majeures** : (i) EF-2 est reformulée — plus de sentiment par thème, mais une règle de priorité au négatif ; (ii) **aucune annotation supplémentaire n'est nécessaire**, la réserve n°1 de l'audit tombe ; (iii) le lot L5 se réduit au seul recalibrage du seuil multi-label. **Contrepartie assumée** : Cultura perd l'information « ce qui fonctionne, ne pas y toucher » sur les verbatims mixtes. |
| **D-27** *(09/09)* | **La typo du référentiel est corrigée : « Attente commande »**, et non « Attente comm**m**ande ». | À faire **avant** tout entraînement : l'ordre du référentiel est figé et sert d'index d'encodage ; corriger après coup invaliderait les modèles. Aligne les 208 annotations déjà saisies dans la forme correcte. Le référentiel appartenant à Cultura (D-7), la correction doit leur être soumise pour validation. |
| **D-28** *(09/09)* | **La baseline est mesurée par tranche de longueur de verbatim**, et le périmètre du « classifiable » est négocié avec Cultura. | La médiane réelle est de **36 caractères et 6 mots**, le premier quartile à 18 caractères. Une métrique globale mélangerait des cas hors de portée (« nul », « très bien », « . ») et des cas traitables : elle ne piloterait rien, et fournirait un prétexte commode pour expliquer de mauvais résultats. Écarte le filtrage silencieux des verbatims courts, qui reviendrait à jeter une part importante du corpus sans décision de Cultura. |
| **D-30** *(09/09)* | **La composition du verbatim est définie par source, et non uniformément.** MDTC post-achat : concaténer `Justification` + `Suggestion d'amélioration`, **exclure** `Produits non trouvés`. MDTC post-réception : champ unique. Mopinion : un verbatim par champ (D-17 maintenue). | **Amende D-17.** Motif mesuré : **l'annotation Cultura porte sur le répondant, pas sur le champ**. Quand « Produits non trouvés » est rempli, le thème annoté est dispersé (Général 16, Choix produit 12, Cartes cadeaux 10 dont « Payer avec une carte cadeau » 6) — aucun lien avec un produit introuvable : l'annotateur a lu la Justification. Appliquer D-17 partout produirait **1 154 verbatims (14 % du corpus) à annotation recopiée**, dont 44 % de MDTC post-achat : du bruit d'étiquetage *cohérent*, donc invisible dans les métriques. `Produits non trouvés` est par ailleurs une **donnée structurée** — 104 valeurs, 100 % au format « Rayon : Produit », 8 seulement contenant un verbe d'opinion — et non un verbatim. **Résultat : 7 552 verbatims exploitables, zéro annotation recopiée.** Arbitrage assumé : 684 verbatims de moins contre 1 154 labels faux éliminés. |
| **D-31** *(09/09)* | **La normalisation des labels est portée par le chargeur, pas par un lot de nettoyage.** Le lot L14 disparaît et fusionne dans L1a. | Cultura re-livrera les fichiers (verbatims complémentaires pour les 7 sous-thèmes sans exemple). Un nettoyage manuel serait à refaire à chaque livraison ; une normalisation en code est écrite une fois et s'applique à toutes. Traite **233 lignes bloquantes** (dont les deux graphies « Attente comm(m)ande », 208 + 132) et **887 lignes de signaux** (« Insatisfaction » 519 + « Insatisfait » 368 → une seule classe au lieu de deux). **Rend D-27 optionnelle** : la transcription Cultura peut rester inchangée, le chargeur absorbe l'écart via une table de synonymes. En revanche les **18 couples (thème, sous-thème) invalides ne sont pas corrigés** — 0,25 % du corpus, jugement humain requis, à refaire à chaque livraison : écartés et journalisés, ils servent de matière première à l'atelier L3. Net : 1 jour récupéré. |
| **D-32** *(09/09)* | **Un sous-thème entre dans le périmètre du modèle à partir de 10 exemples annotés.** Les 16 sous-thèmes en dessous restent au référentiel mais sont **routés en validation humaine** : le modèle prédit le niveau 1, l'humain qualifie le niveau 2. | Généralise la proposition du PO sur Académie. **16 sous-thèmes sur 59 ne sont ni apprenables ni évaluables** (5 à zéro exemple, 11 entre 1 et 9). Le seuil à 10 les retire tous pour **0,8 % du corpus** — 7 000 annotations conservées sur 7 058. Écarte le seuil à 0 (11 classes à 1-9 exemples resteraient, où un seul verbatim de test fait basculer le score de 0 à 1, effondrant le F1-macro sans rapport avec la qualité du modèle) et le seuil à 30 (34 sous-thèmes sortiraient pour 6,1 % du corpus, avec une charge de revue nettement plus lourde). **Aucun développement nécessaire** : l'écran de revue et la table `taxonomy_entries` le permettent déjà (recette V6). Concerne les 3 sous-thèmes d'Académie sans exemple, les 2 sous-thèmes marketplace à 1 exemple, et 11 autres. |
| **D-33** *(09/09)* | **`Général / Autre` est conservé comme classe mais exclu des cibles de performance.** | Ce sous-thème capte **1 393 annotations, soit 19,7 % du corpus** — le thème aspirateur de l'ancien référentiel réapparaît, sous une forme plus honnête mais aussi problématique. Le garder est utile : c'est un aveu d'incertitude explicite plutôt qu'un faux thème, et l'exclure de l'entraînement forcerait le modèle à répartir ces verbatims dans les autres sous-thèmes, **gonflant artificiellement leurs volumes** — exactement le biais de priorisation que le projet cherche à éliminer (D-16). Mais ne pas l'exclure des cibles reviendrait à créditer un modèle qui prédirait « Autre » partout de 20 % de justesse sans aucun apport métier. **À signaler à Cultura** : un cinquième des verbatims ne rentre dans aucun de leurs 59 sous-thèmes. Concentration mesurée : `Général/Autre` (1 393), `Général/Ergonomie` (1 008), `Réception/Conformité commande` (1 273) et `Réception/Retrait magasin` (1 157) font **68 % du corpus** ; les 55 autres sous-thèmes se partagent le tiers restant. |
| **D-34** *(09/09)* | **Échéance reportée au mardi 6 octobre 2026.** Périmètre complet maintenu. | Le 22 septembre initialement annoncé n'offrait que **9 jours ouvrés pour un chemin critique de 19**. Le point dur n'est pas la capacité mais la **séquentialité** : L1a → L2 → L5' → L6 → L9 ne peuvent pas se chevaucher (il faut lire les fichiers pour les mesurer, une baseline pour calibrer un seuil, une architecture figée pour entraîner, un modèle pour recetter). **Ajouter des personnes ne raccourcit pas cette chaîne** ; même en comprimant chaque lot par parallélisation interne, le plancher est de 14 jours. Écarte la livraison d'un modèle non recetté (scénario du prototype, dont le F1 de 0,891 trompeur est resté invisible deux mois). Troisième date après le 30 août et le 22 septembre : **à poser explicitement à Cultura**. |
| **D-35** *(09/09)* | **Q-14 est levée : des ressources techniques supplémentaires sont affectées au projet.** | Débloque la parallélisation de L8 (débit), et rend **L7** (calibration de la confiance) et **L10** (boucle d'amélioration) logeables en parallèle de L9. **Les objectifs O-4 et O-6 ne sont plus sacrifiés** — c'est la première fois depuis le 30 juillet. Réserve : le chemin critique consomme exactement les 19 jours ouvrés disponibles, **sans aucune marge**. Toute dérive décale la livraison d'autant. |
| **D-29** *(09/09)* | **Les données d'entraînement sont celles livrées par Cultura le 09/09** : 26 826 lignes, **7 068 annotées**, 6 595 textes uniques, janvier à septembre 2026. | Rend D-23 sans objet : Cultura a livré des données déjà annotées en thème, sous-thème, second thème, signal et sentiment. R-1 et R-17 sont levés. Le jeu des 7 000 du prototype reste écarté (D-8). |

---

## 9. Hypothèses et questions ouvertes

Rien de ce qui suit n'est une exigence. Ce sont des points à confirmer, nommément.

### 9.1 Bloquant — à lever immédiatement

| # | Question | Bloque | Destinataire |
|---|---|---|---|
| **Q-1** | ~~Déposer les nouveaux fichiers~~ → **partiellement close le 12/08**. Quatre **maquettes de structure** déposées dans `data/raw/NEW_FILES/` : `MDTC-postachat-web.xlsx` (9 colonnes), `MDTC-postrecep-web.xlsx` (7), `mopinion_desktop-juin-24juil_26.xlsx` (25), `mopinion_mobilev2-20-24juillet_26.xlsx` (25). **Les exports réels restent attendus** — voir Q-1 bis. | Volet spécification de L1 : **débloqué** | Close le 12/08 |
| **Q-1 bis** 🔴 | **Quand recevons-nous les exports réels ?** Période, volume, formulaires couverts. Les maquettes comptent 11 à 16 lignes fictives : aucune mesure, aucun entraînement, aucune baseline n'est possible dessus (R-17). | Volet audit de L1, puis L2, L5, L6, L9 — **tout le chemin critique** | **Cultura — sollicitation A1, sous 48 h** |
| **Q-2** 🔴 | **Déposer le nouveau référentiel Cultura**, confirmé à disposition. **Toujours non reçu au 12/08** : les 4 fichiers déposés sont des maquettes de données, pas le référentiel. | L1, L2, L5, L6, L11, L12 | **Jonathan / Cultura — sollicitation B1, sous 48 h** |
| **Q-3** | Les nouveaux fichiers sont-ils **annotés en multi-thème**, avec un sentiment par thème ? Contiennent-ils des cas à **sentiments divergents** ? En quelle proportion ? | Mesurabilité de EF-1, EF-2, EF-3, EF-4 | Mesuré en L1 |
| **Q-5** | Le nouveau référentiel respecte-t-il l'**unicité globale des libellés de niveau 2** ? `src/utils/taxonomy.py` **lève une `ValueError` au chargement** si un même libellé apparaît sous deux parents — le message du code recommande déjà la clé composite. Si l'invariant est cassé, L11 s'active (+4 j non provisionnés). | L2, L6 ; déclenche L11 | Mesuré en L1 dès réception |
| **Q-14** | **Une seconde ressource technique est-elle disponible en août ?** L'équipe de D-14 ne comporte aucun développeur, alors que le plan attribue L8 à « DS ou dev » et conditionne la parallélisation à cette ressource. Sans elle, D-13 n'est pas tenable. | Faisabilité de D-13 | **Jonathan — cette semaine** |

### 9.2 À poser à Cultura — sollicitation groupée, semaine du 3 août

| # | Question | Impact |
|---|---|---|
| **Q-4** | Cultura accepte-t-il le principe de **libellés de sous-thèmes neutres** (D-6), la polarité étant portée par le sentiment ? | Conditionne la disparition de `Facile` et des contradictions d'annotation. À défaut, les retours positifs restent mal traités. |
| **Q-6** | **Que déclenche concrètement chaque signal** (rupture, churn, insatisfaction) ? Quelle action, quel destinataire, quel délai ? | Conditionne D-10 et le nombre de modèles de signaux à entraîner. |
| **Q-9** | Validation des **cibles chiffrées** de §7.2 marquées *(à valider)*. | Conditionne les critères d'acceptation contractuels. |
| **Q-10** | Le 30/08/2026 est un **dimanche**. Quelle est la date effective de mise en production, et qui la prononce ? Le dernier jour ouvré est le **vendredi 28 août**. | Conditionne D-13 et la DoD de L9. |
| **Q-11** | Qui **valide** le nouveau modèle, sur quel jeu de recette, dans quelle instance ? | Conditionne L9. |
| **Q-12** | Les **règles d'arbitrage** entre thèmes voisins existent-elles côté Cultura ? Exemple : un retard sur un retrait en magasin relève-t-il de *Suivi de commande* ou de *Click & Collect* ? | Conditionne L3 et la qualité des labels. |
| **Q-13** | Disponibilité effective de Cultura en **août** (congés). Un interlocuteur est confirmé joignable ; à confirmer sur les dates de L3 et de la recette de L9. | Conditionne L3 et L9. |
| **Q-16** | Cultura accepte-t-il le **scénario de repli** (modèle mesuré et présentable au 28/08, mise en production en septembre) si le jalon du 21 août n'est pas tenu ? | Évite un arbitrage en urgence fin août. Sollicitation E4. |
| **Q-17** *(12/08)* | **Table de conversion des échelles de satisfaction** : 4 modalités textuelles MDTC, échelle 1-5 Mopinion. Existe-t-il une conversion officielle chez Cultura ? | Conditionne D-20 et toute comparaison de volumes entre sources. Sollicitation A6. |
| **Q-18** *(12/08)* | **Liste complète des choix fermés** de chaque question de sujet Mopinion, et leur correspondance avec le référentiel. Quelle est la fiabilité observée par Cultura ? Le champ `tags` numéroté est-il une nomenclature Cultura en production, concurrente du référentiel ? | **Conditionne D-19 et R-15.** Question la plus rentable du projet : elle décide si l'étiquetage est gratuit ou s'il faut une campagne d'annotation. Sollicitations A3 et A4. |
| **Q-19** *(12/08)* | Confirmation du **périmètre d'ingestion restreint** (D-18) auprès de Cultura et, si nécessaire, du référent RGPD. La colonne e-mail est-elle renseignée dans les exports réels ? | Conditionne la spécification du chargeur et la posture RGPD. Sollicitations D1 et D2. |
| **Q-20** *(12/08)* | **Combien de formulaires au total ?** Les 4 maquettes sont suffixées *web*, *desktop*, *mobile V2* : existe-t-il des variantes application ? Les schémas sont-ils stables, et qui prévient d'un changement ? | Conditionne le nombre de chargeurs à développer (R-18). Sollicitation A2. |
| **Q-27** *(09/09)* | **Cultura peut-il faire relire les 1 393 verbatims classés `Général / Autre` ?** Un cinquième du corpus ne rentre dans aucun des 59 sous-thèmes : le référentiel ne couvre pas ce que les clients écrivent. | **La demande la plus rentable du moment.** Deux ou trois sous-thèmes manquants en émergeraient — bénéfice direct sur la qualité du modèle et sur la priorisation des chantiers (D-16, D-33). |
| **Q-22** *(09/09)* | Que signifie le sous-thème `SRC` (2 occurrences, hors référentiel) ? | Mineur. Hypothèse par défaut : écarté comme anomalie. |
| **Q-23** *(09/09)* | Validation de la **table de conversion des échelles** 1-5 (Mopinion) → 1-4 (MDTC), proposée en `SPEC_CHARGEUR.md` §7.1. Relance de la question A6 restée sans réponse. | Conditionne D-20 et toute comparaison de volumes entre sources (O-3). Hypothèse eXalt appliquée en attendant, marquée comme telle. |
| **Q-24** *(09/09)* | **Figer la graphie** de « Attente comm(m)ande » dans les prochaines livraisons. | Mineur depuis D-31 : le chargeur absorbe les deux graphies. Demande préventive, pour éviter qu'une troisième variante apparaisse. |
| **Q-25** *(09/09)* | Un répondant multi-champs peut-il être annoté **par champ** ? | **Sans objet depuis D-30** : la composition par source règle le problème sans intervention de Cultura. |
| **Q-26** *(09/09)* | La colonne `Client` (Nouveau / Ancien) sera-t-elle renseignée systématiquement ? Vide dans 4 fichiers sur 6. | Mineur. Non ingérée en l'état, à reconsidérer si elle se fiabilise. |
| **Q-28** *(09/09)* | Confirmer le libellé : le référentiel dit `Gérer ma réservation`, le PO cite « Gérer une activité ». | Mineur — les deux sont à 0 exemple et sortent du périmètre par D-32. À figer pour la cohérence du référentiel. |
| **Q-21** *(12/08)* | **Comment obtenir des étiquettes sur MDTC ?** Cette source ne comporte aucun champ de catégorisation par le client. Existe-t-il un historique classé, ou une équipe capable de classer quelques centaines de réponses ? | **Seule mitigation de R-16.** Sans échantillon MDTC classé, la qualité sur cette source n'est ni mesurable ni garantie. Sollicitation A5. |

### 9.3 Interne eXalt

| # | Question | Impact |
|---|---|---|
| **Q-7** | **Budget matériel pour l'entraînement.** L'entraînement est une opération CLI hors application ; une machine plus puissante ou un GPU ne violerait pas l'offline strict de la production (ENF-4). Sur CPU, une passe complète des trois modèles se compte en heures, et le plan ne tolère qu'un nombre très limité d'itérations. | Réduit fortement R-2. Levier le plus efficace pour sécuriser l'échéance. |
| **Q-8** | Les **2 personnes côté métier** sont-elles eXalt ou Cultura ? Sont-elles mobilisables pour **annoter**, et à quelle hauteur (verbatims/jour, jours disponibles) ? | **Seule porte de sortie de R-1.** Conditionne le lot L13 (campagne d'annotation), aujourd'hui non provisionné. |
| **Q-15** | Quelle **charge pour la mise à jour des dashboards** et des seuils en base rendus nécessaires par le changement de sémantique de `confidence_globale` et par une éventuelle suppression de signal ? La DoD de L9 l'exige, aucun lot ne la provisionne, et §3.2 met la refonte de l'interface hors périmètre. | Charge inconnue sur le chemin critique. |

### 9.4 Hypothèses de travail assumées

- ~~**H-1**~~ : **FALSIFIÉE le 12/08.** Les nouveaux fichiers ne suivent **aucun** schéma connu.
  **Zéro** mapping de `config.yaml → sources` ne survit : `Date de commande` → `Date d'achat`,
  `Niveau de satisfaction général` → `Niveau de satisfaction`, `Verbatim justification` →
  `Justification du niveau de satisfaction`, `Description du bug` → `Décrivez nous votre
  problème`. Il faut **4 chargeurs** (un par formulaire) produisant `__source__`,
  `__text_raw__`, `__satisfaction__`, et non une adaptation des deux existants. Charge
  reventilée sur L1 (volet spécification) et sur un lot de développement à cadrer. Voir R-17
  et R-18.
- **H-2** : le volume mensuel reste de l'ordre de 11 000 verbatims.
- **H-3** : le sentiment conditionné au thème peut être obtenu par préfixe textuel
  (`[THEME <libellé>] <verbatim>`), sur le modèle du préfixe de satisfaction déjà en place dans
  `src/utils/features.py`. Compatible ONNX, sans tête custom. **À valider techniquement en
  L5** ; à défaut, une tête custom serait nécessaire, au prix de l'export ONNX et donc du débit.
- **H-4** : l'annotation requise est du triplet *(verbatim, thème) → sentiment*, pas de la
  délimitation de segments de phrase. Allège considérablement l'effort d'annotation.

---

## 10. Risques

| # | Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|---|
| **R-1** | **Les nouvelles données ne contiennent pas assez d'exemples annotés en multi-thème avec sentiments divergents** pour entraîner et surtout pour **mesurer** le nouveau comportement. | **Forte** — 0 cas sur 7 000 aujourd'hui | **Élevé** *(reclassé depuis « critique » : le mécanisme multi-thème fonctionne déjà mécaniquement, cf. §1.4 e ; l'enjeu est la mesurabilité et la qualité, non la capacité)* | L1 est un **jalon de décision** : mesurer dès les 3 premiers jours la proportion de bi-thèmes et de sentiments divergents. Si insuffisant : campagne d'annotation ciblée (lot L13, conditionné à Q-8), ou bascule du seul jeu de recette sur une annotation manuelle de quelques centaines de cas. **Ne pas découvrir ce point le 25 août.** |
| **R-2** | **Le fil du data scientist est en dépassement de capacité avant toute dérive** : ≈ 23,5 jours-homme de tâches techniques pour 22 jours ouvrés, et c'est ce fil qui porte le chemin critique. | **Certaine** en l'état | **Élevé** : D-13 n'est pas tenable | Lever Q-14 (seconde ressource technique) ou Q-7 (machine d'entraînement plus rapide). À défaut, reporter L7 puis L10 — décision à prendre **avant** le 10 août, pas en fin de plan. Décharger le DS de tout ce qui peut l'être (audit et protocole portés par l'agent, définitions métier par le PO et le métier, recette par le métier). |
| **R-3** | **Le nouveau référentiel casse l'unicité globale des libellés de niveau 2** → l'application refuse de charger la taxonomie, refonte de l'encodage nécessaire (L11, +4 j non provisionnés). | **Moyenne** — le référentiel actuel a déjà dû différencier artificiellement « Erreur de prix » (*Annulation commande*) et « Erreur de prix affiché » (*Prix produit*) | **Élevé** | Vérifier l'invariant **dès réception** du fichier (Q-2), avant toute autre tâche. Lot L11 pré-cadré et prêt à activer. Noter que la table `taxonomy_entries` porte déjà une contrainte d'unicité sur le couple (niv1, niv2) : la couche applicative a déjà la clé composite que le ML n'a pas. |
| **R-4** | **Le débit de 1-2 h n'est pas tenu.** Le sentiment par thème porte à 5 le nombre de passages transformer pour les verbatims bi-thèmes ; l'`EmbeddingExtractor` des signaux n'est pas exporté en ONNX et force PyTorch ; la quantization cible `avx2` (x86, commentaire du code explicite) alors que le poste est arm64. Le « < 1 h » n'a jamais été mesuré, même à 4 passages. | **Moyenne à forte** | **Élevé** : bloque la mise en production | Mesurer le débit **tôt** (L8, dès L2 sur le modèle actuel) et non en fin de plan. Leviers : exporter l'`EmbeddingExtractor` en ONNX, revoir la cible de quantization pour arm64, réduire le nombre de signaux (D-10), mutualiser les passages. |
| **R-5** | **Le sentiment reste déductible de la note dans les nouvelles données.** Si les nouveaux fichiers reproduisent la règle `1-4 → Négatif, 5-7 → Neutre, 8-10 → Positif`, le sentiment par thème est **inapprenable** : une note unique ne peut pas justifier deux sentiments opposés. EF-3 devient alors inatteignable par construction. | **Moyenne** | **Critique** pour EF-2 et EF-3 | Test explicite en L1 : mesurer le taux d'accord entre la note et le sentiment annoté. Si l'accord est parfait, remonter immédiatement à Cultura : c'est un défaut de protocole d'annotation, pas un défaut de modèle. EF-3 est marquée conditionnelle à ce risque. |
| **R-6** | **Aucune baseline valide n'existe** : sans L2, tout gain annoncé est indémontrable et toute cible est arbitraire. | **Certaine si L2 est sacrifié** | **Élevé** | L2 est non négociable et placé sur le chemin critique. Le test de non-fuite devient bloquant dans la chaîne de préparation. Corriger aussi le calcul du F1-micro (§7.1 point 6), qui masquait la sur-activation. |
| **R-7** | **Toutes les recettes existantes tournent sur le moteur stub** : elles valident la plomberie applicative, jamais la qualité du modèle. Une mise en production « recette au vert » ne dit rien du modèle. | **Certaine** — c'est l'état actuel | **Moyen** | Ajouter à L9 une recette **métier** sur le jeu de recette gelé, distincte des recettes techniques, avec un verdict nommé (Q-11). |
| **R-8** | **Congés d'août** côté eXalt et côté Cultura : indisponibilité sur les jalons dépendants du client. | **Moyenne** — un interlocuteur Cultura est confirmé joignable | **Moyen** | Isoler et marquer les lots dépendants de Cultura comme conditionnels. Poser Q-4, Q-6, Q-9, Q-10, Q-11, Q-12, Q-13 et Q-16 en **une seule sollicitation groupée**, dès la première semaine. |
| **R-9** | **Les frontières poreuses du référentiel ne sont pas corrigées** (D-5 reporte, D-7 place la main chez Cultura). Le plafond de performance du niveau 1 reste structurel : `Click & Collect` absorbé par `Suivi de commande` dans 45 cas sur 62, sur des textes déjà vus à l'entraînement. | **Forte** | **Moyen à élevé** : plafonne la famille A, et fausse les volumes de priorisation (D-16) | Documenter le plafond plutôt que de promettre une cible inatteignable. Fournir à Cultura la matrice de confusion des **nouvelles** données comme pièce d'instruction (L1). Poser Q-12. **D-5 doit être prononcée au 5 août**, sans quoi le report devient sine die. |
| **R-10** | **Pas de règles d'arbitrage écrites** → les labels des nouveaux fichiers sont incohérents sur les cas limites, et le modèle apprend du bruit. Précédent mesuré : 213 des 403 textes uniques du jeu actuel portent des labels de signaux contradictoires. | **Moyenne à forte** | **Élevé** : plafonne la qualité indépendamment du modèle | L3 (règles + guide d'annotation) placé tôt, en parallèle de L2. Mesurer en L1 la cohérence des labels sur les paires de thèmes voisins **et** sur les signaux. |
| **R-11** | **Biais d'auto-confirmation de la boucle d'amélioration** (D-11) : seuls les verbatims de faible confiance sont relus, donc le jeu d'entraînement issu des corrections est structurellement biaisé vers les cas difficiles. | **Certaine si non traitée** | **Moyen** | Prévoir en L10 un échantillonnage aléatoire complémentaire de verbatims à haute confiance, et conserver un jeu de recette gelé indépendant des corrections. |
| **R-12** | **La revue humaine peut déjà enregistrer des couples hors référentiel.** `app/api/app/core/taxonomy.py` (`register_pair`, `pair_is_known`) et la table `taxonomy_entries` (migration `0009`, recette V6) permettent à tout relecteur, analyste inclus, d'enregistrer via `PATCH /api/results/{id}` un couple (niv.1, niv.2) absent du référentiel, réutilisable ensuite par `GET /api/taxonomy`. **EF-5 et le garde-fou « 0 couple hors référentiel, strict » sont donc déjà faux dans l'application livrée**, et D-7 est déjà contournée côté relecteur. Effet de bord sur L10 : l'export de corrections vers l'entraînement propagerait ces libellés hors référentiel. | **Certaine** — c'est l'état livré | **Moyen à élevé** | EF-5 et le critère de famille A sont explicitement restreints au **modèle**. Signaler l'écart à Cultura. Ajouter à la DoD de L10 un filtre ou un traitement explicite des couples hors référentiel. Étendre le périmètre de L11 à la couche API si activé. Intégrer V6 au périmètre de non-régression de L9. |
| **R-13** | **La campagne d'annotation, seule mitigation de R-1, n'est ni provisionnée en charge ni adossée à une ressource confirmée** (Q-8). | **Moyenne** | **Élevé** si R-1 se réalise | Lot L13 pré-cadré et conditionnel dans le plan de lots. Lever Q-8 avant le 5 août, pour pouvoir l'activer immédiatement à la clôture de L1. |
| **R-14** | **La qualité de l'anonymisation n'est mesurée par aucun lot**, alors que le mode dégradé de spaCy est silencieux (T5) et que les 302 masquages `[NOM]` du jeu actuel, pour 0 email et 0 téléphone, sont vraisemblablement des faux positifs sur des majuscules de début de phrase. Un masquage erroné détruit du texte **à l'entraînement**, pas seulement à l'inférence. **Aggravé le 12/08** : les nouveaux fichiers comportent une colonne e-mail dédiée et des numéros de commande au format `P########`, que le regex `ORDER_ID` actuel n'a jamais rencontré (0 masquage sur 7 000). | **Moyenne à forte** | **Moyen** (élevé sur le volet conformité) | Ajouter à L1 un contrôle du taux et de la nature des masquages, la vérification de la présence de spaCy, et le test du regex `ORDER_ID` sur le format `P########`. Si le taux de faux positifs est élevé, traiter la stoplist — charge à chiffrer, aujourd'hui non provisionnée. |
| **R-15** *(12/08)* | **Les sujets cochés par le client (D-19) sont des étiquettes bruitées.** Un client qui coche « problème de paiement » puis décrit un problème de livraison produit un label faux. Adopter ces étiquettes sans mesurer leur fiabilité reviendrait à entraîner le modèle sur les erreurs de saisie des clients, à l'échelle de tout le corpus Mopinion. | **Moyenne à forte** | **Élevé** : un modèle qui apprend un bruit systématique est pire qu'un modèle sous-entraîné, car ses erreurs sont cohérentes et donc invisibles | Garde-fou de D-19 : mesurer en L1 le taux de désaccord entre le sujet coché et le texte écrit, sur un échantillon relu à la main (quelques centaines de cas suffisent). Demander à Cultura son retour d'expérience sur la fiabilité observée (sollicitation A3). Si le désaccord dépasse un seuil à définir, rétrograder les sujets cochés du statut d'étiquette à celui de simple variable d'entrée. |
| **R-16** *(12/08)* | **Asymétrie d'étiquetage entre sources.** Mopinion fournit des étiquettes gratuites (D-19), MDTC n'en fournit aucune. Un modèle entraîné majoritairement sur Mopinion et appliqué à MDTC peut se dégrader fortement sans que rien ne le signale : les deux sources n'ont ni le même contexte, ni le même style rédactionnel, ni la même distribution de sujets. | **Forte** | **Élevé** : la qualité sur MDTC ne serait ni mesurée ni garantie | **L'évaluation séparée par source devient obligatoire** (§7.1 point 4), et non plus une simple amélioration du protocole. Obtenir de Cultura au moins un échantillon MDTC classé, destiné à l'évaluation même s'il ne sert pas à l'entraînement (sollicitation A5). À défaut, porter une réserve explicite à la mise en production. |
| **R-17** *(12/08)* | **Les fichiers reçus le 12/08 sont des maquettes de structure** (11 à 16 lignes fictives, marqueurs `(etc)`), non des exports réels. Aucune mesure statistique, aucun entraînement, aucune baseline n'est possible dessus. **H-1 est falsifiée** : aucun des mappings de colonnes de `config.yaml` ne survit, et il faut 4 chargeurs au lieu d'un. | **Certaine** — constatée | **Critique sur le calendrier** | L1 se scinde : un volet **spécification du contrat de données** réalisable immédiatement (chargeurs, composition du verbatim, colonnes ingérées, conversion des échelles), et un volet **audit statistique** qui reste bloqué sur A1. Le chemin critique ne redémarre qu'à réception des exports réels. Escalader A1 comme la question la plus urgente du projet. |
| **R-18** *(12/08)* | **Le nombre de formulaires n'est pas connu.** Les 4 maquettes sont suffixées *web*, *desktop* ou *mobile V2*, ce qui laisse supposer des variantes application non transmises. Chaque formulaire supplémentaire est un chargeur supplémentaire. Aucun mécanisme n'alerte si Cultura fait évoluer les colonnes d'un formulaire. | **Moyenne** | **Moyen** | Sollicitation A2. Développer pour 4 formulaires et traiter tout autre format comme hors périmètre. Ajouter au chargeur une validation de schéma qui **échoue explicitement** sur une colonne attendue manquante, plutôt que de dégrader en silence. |

---

## 11. Journal des corrections de ce document

> **v1.3 — 9 septembre 2026.** Les données réelles et le référentiel Cultura sont arrivés.
> Voir `docs/AUDIT_DONNEES_NOUVEAU_MODELE.md` pour le détail mesuré. Bilan : **L11 écarté
> (4 j), L5 réduit au seul seuil multi-label (3 j) — 7 jours-homme récupérés sur le fil du
> data scientist.** R-1, R-3, R-5 et R-17 sont levés. Deux réserves nouvelles : verbatims très
> courts (médiane 6 mots) et classe Neutre à 5,7 %.
>
> ⚠️ **L'échéance du 30 août 2026 est dépassée.** Le scénario de repli accepté par Cultura
> (Q-16 / sollicitation E4) s'applique de fait. Le plan de lots doit être redaté.

| Version | Date | Correction | Motif |
|---|---|---|---|
| v1.0 | 30/07/2026 | Version initiale issue de l'entretien de cadrage. | – |
| **v1.1** | **30/07/2026** | **Correction du diagnostic du grief n°1** (§1.1, §1.4 e, §1.5, D-2, D-15, R-1, §7.2 famille B) : le modèle **sur-active** les thèmes (≈ 2,5 activés au seuil 0,35 ; 43,3 % de sorties bi-thèmes mesurées) au lieu de les sous-activer. Le défaut réel est la recopie du sentiment (0 divergence sur 52 cas) et la précision du second thème. | Relecture critique. L'hypothèse initiale « 99,6 % de sorties mono-thème » n'était mesurée nulle part et est contredite par `_validation_classifications.csv` et par la précision micro implicite de 0,336. |
| v1.1 | 30/07/2026 | Ajout de §1.4(a bis) : 213 des 403 textes uniques portent des labels de signaux contradictoires. Correction de « 0 incohérence sur 403 », qui ne vaut que pour les thèmes et sentiments. | Recalcul sur `dataset.csv`. |
| v1.1 | 30/07/2026 | Corrections factuelles : 11 textes uniques bi-thèmes (et non ≈ 12) ; métriques de signaux identiques à **deux** décimales (et non trois) ; retrait de « aucune PII » dans D-8, remplacé par le constat des 302 faux positifs probables ; « 4 ou 5 passages transformer » selon le nombre de thèmes (et non « 4 à 5 » systématique). | Recalcul et relecture du code. |
| v1.1 | 30/07/2026 | Ajout de R-12 (`taxonomy_entries` / recette V6 invalidant EF-5 « 0 strict » et D-7), R-13 (campagne d'annotation non provisionnée), R-14 (qualité de l'anonymisation non mesurée). Ajout de la recette V6 au périmètre de non-régression. | Omission majeure : le mécanisme de saisie libre de thèmes en revue est en production et absent du socle de référence. |
| v1.1 | 30/07/2026 | Marquage **[C]** des exigences conditionnelles (EF-3, EF-6, EF-7, EF-10) et des critères de famille C. Ajout de EF-4 (distribution du nombre de thèmes). Traçabilité O-x → lots. Alerte sur O-4 et O-6, portés par les seuls lots abandonnables. | Des exigences fermes reposaient sur des lots déclarés abandonnables ou sur des hypothèses non levées. |
| v1.1 | 30/07/2026 | Réserve explicite ajoutée à D-13 et D-14 : l'engagement de mise en production au 30/08 n'est pas tenable avec l'équipe décrite. Ajout de Q-14 (seconde ressource technique), Q-15 (charge dashboards), Q-16 (acceptation du repli). Correction de R-2 : ≈ 23,5 jours-homme, non 20. | La prémisse de D-14 (« on renforce l'équipe ») n'est pas satisfaite par l'équipe décrite. Un cadrage qui la valide silencieusement serait complaisant. |
| v1.1 | 30/07/2026 | D-5 assortie d'une échéance de décision (5 août). Ajout du point 6 à §7.1 (correction du calcul du F1-micro). Q-8, Q-10, Q-13 rattachées à des lots ou à la sollicitation groupée. | Décisions et questions ouvertes sans porteur ni date. |
| **v1.2** | **12/08/2026** | **Profiling des 4 maquettes déposées dans `data/raw/NEW_FILES/`.** Ajout de **D-17** (un verbatim par champ libre), **D-18** (ingestion restreinte des métadonnées), **D-19** (sujets cochés comme étiquettes de départ), **D-20** (niveau de satisfaction normalisé, RECO écarté). | Réception des fichiers de structure et entretien du 12/08. |
| v1.2 | 12/08/2026 | **H-1 falsifiée** : aucun mapping de colonnes ne survit, 4 chargeurs nécessaires au lieu de 1. Ajout de **R-17** (les fichiers reçus sont des maquettes : aucune mesure possible, le chemin critique reste bloqué sur les exports réels) et **R-18** (nombre de formulaires inconnu, pas d'alerte sur évolution de schéma). | Constat de profiling. |
| v1.2 | 12/08/2026 | Ajout de **R-15** (les sujets cochés sont des étiquettes bruitées — garde-fou obligatoire de D-19) et **R-16** (asymétrie d'étiquetage Mopinion/MDTC — l'évaluation par source devient obligatoire). Aggravation de **R-14** (colonne e-mail dédiée, numéros de commande au format `P########` jamais rencontré par le regex actuel). | Conséquences directes de D-19 et du schéma réel. |
| v1.2 | 12/08/2026 | Q-1 close et scindée en **Q-1 bis** (exports réels). Ajout de **Q-17** à **Q-21**. Q-2 signalée **toujours non reçue** : les 4 fichiers déposés sont des maquettes de données, pas le référentiel. | Le référentiel reste le point bloquant n°1 avec les exports réels. |
| v1.2 | 12/08/2026 | Création de `docs/SOLLICITATION_CULTURA.md` : 20 questions groupées en 5 blocs, dont 6 bloquantes, formulées pour être posées directement à Cultura. | Demande du PO. |
| **v1.3** | **09/09/2026** | Ajout de **D-21** à **D-25** (démo de non-régression, conception des jeux factices, annotation, volumétrie, cas pièges) et de **D-26** à **D-29** (priorité au négatif, correction de la typo, mesure par tranche de longueur, données d'entraînement Cultura). | Décisions du PO des 12/08 et 09/09. |
| v1.3 | 09/09/2026 | **EF-2 reformulée** : la version initiale (« chaque thème porte son propre sentiment ») est abandonnée au profit de la règle de priorité au négatif (D-26). Sans annotation au niveau du thème, elle n'était ni entraînable ni mesurable. **EF-3 n'est plus conditionnelle** : R-5 ne se réalise pas. | Audit du 09/09, §5. |
| v1.3 | 09/09/2026 | **L11 écarté** (aucun libellé niv.2 dupliqué → R-3 ne se réalise pas) et **L5 réduit** au seul recalibrage du seuil multi-label (D-26 rend inutile le sentiment conditionné au thème). **7 jours-homme récupérés sur le fil du data scientist.** | Audit du 09/09, §2 et §10. |
| v1.3 | 09/09/2026 | **R-1, R-5, R-17 levés** ; **R-10 et R-18 confirmés et mesurés** ; **R-14 aggravé** (numéros `P########` réels, e-mails partiellement masqués). **D-6 satisfaite d'office** : le référentiel Cultura est déjà à libellés neutres. | Audit du 09/09. |
| v1.3 | 09/09/2026 | Réserves nouvelles portées : **verbatims très courts** (médiane 36 caractères / 6 mots, p25 à 18 caractères) ; **classe Neutre à 5,7 %** ; **7 sous-thèmes sans aucun exemple** donc inapprenables ; **signaux fournis comme un champ à valeur unique** et non trois booléens, Churn (64) et Rupture (32) non évaluables. | Audit du 09/09, §4 à §7. |
| v1.3 | 09/09/2026 | **Alerte de conformité traitée** : le `.gitignore` racine ne couvre pas `data/raw/` et le commente comme « données simulées, aucune PII réelle ». Un `.gitignore` protecteur a été déposé dans `data/raw/cultura_2026/`. Le commentaire racine reste à corriger. | Dépôt de verbatims clients réels contenant e-mails et numéros de commande. |

---

### Sources

Artefacts mesurés pendant le cadrage : `data/raw/historique_labels_poc.xlsx`,
`data/processed/dataset.csv`, `data/processed/dataset_stats.json`,
`data/processed/eval_report.json`, `data/output/_validation_classifications.csv`,
`data/raw/taxonomy_cultura_poc.json`.
Code lu : `src/inference/predictor.py`, `src/utils/taxonomy.py`, `src/utils/features.py`,
`src/evaluation/evaluate.py`, `src/modeling/architecture.py`, `app/worker/llm_common.py`,
`app/api/app/core/taxonomy.py`, `app/tests/recette_v6.py`, `config/config.yaml`.
Document de référence : `docs/ETAT_DES_LIEUX_ML.md` (v1.0, 30/07/2026) — **à corriger** : la
recette V6 et le mécanisme `taxonomy_entries` y sont absents.
Entretien de cadrage : Jonathan Dupau (eXalt), 30 juillet 2026.

*Projet interne Cultura / eXalt — usage confidentiel.*
