# Spécification du chargeur de données — lot L1a

> **Objet.** Spécifier le module de lecture des fichiers Cultura : 4 sources, 5 schémas, avec
> normalisation des colonnes et des labels. Remplace le chargeur actuel
> (`src/preprocessing/loader.py`), dont **aucun mapping ne survit**.
>
> **Statut.** v1.0 — 9 septembre 2026. **Auteur.** Agent Product Owner.
> **Destinataire.** Data scientist. Ce document est exécutable en l'état.
> **Références.** `docs/AUDIT_DONNEES_NOUVEAU_MODELE.md`, `docs/CADRAGE_NOUVEAU_MODELE.md` (v1.3).
> **Décisions appliquées.** D-17, D-18, D-19 (annulée), D-20, D-26, D-27 (rendue optionnelle), D-29.

---

## 1. Pourquoi ce lot est le premier du chemin critique

`config.yaml → sources` mappe des colonnes qui **n'existent dans aucun fichier réel** :

| Ancien mapping | Colonne réelle |
|---|---|
| `Niveau de satisfaction général` | `Satisfaction` |
| `Verbatim justification` | `Justification niveau de satisfaction` |
| `Verbatim suggestion` | `Suggestion d'amélioration` |
| `Date de commande` | `Date d'achat` |
| `Description du bug` | `Décrivez nous votre problème` |

**Zéro survivant.** Par ailleurs les maquettes du 12 août ne sont pas fiables pour spécifier
(elles annonçaient `Niveau de satisfaction`, `score RECO`, `Ancienneté client`, absents du
réel) : **seuls les fichiers réels font foi.**

Ce lot absorbe aussi la normalisation des labels — précédemment prévue en lot L14 autonome.
Rationnel : Cultura re-livrera les fichiers (verbatims complémentaires pour les 7 sous-thèmes
sans exemple). Un nettoyage manuel serait à refaire à chaque livraison ; **une normalisation
dans le chargeur est écrite une fois et s'applique à toutes les livraisons.**

---

## 2. Contrat interne de sortie

Le chargeur produit un `DataFrame` **à une ligne par verbatim** (et non par répondant, cf. D-17),
avec les colonnes techniques préfixées pour éviter toute collision métier.

| Colonne | Type | Sémantique |
|---|---|---|
| `__source__` | texte | `MDTC-postachat` · `MDTC-postrecep` · `Mopinion-desktop` · `Mopinion-mobile` |
| `__respondent_id__` | texte | identifiant du répondant — **permet de regrouper les verbatims d'une même réponse** |
| `__field__` | texte | nom canonique du champ libre d'origine |
| `__text_raw__` | texte | verbatim brut, **avant** anonymisation |
| `__satisfaction__` | entier 1–4 ou vide | note normalisée (§7) |
| `__satisfaction_raw__` | texte | valeur brute, conservée pour traçabilité |
| `__date__` | date ISO | date de réponse |
| `__page_type__` | texte ou vide | métadonnée ingérée (D-18) |
| `__url__` | texte ou vide | métadonnée ingérée (D-18) |
| `__device__` | texte ou vide | métadonnée ingérée (D-18) |
| `theme1_niv1` · `theme1_niv2` | texte ou vide | annotation, **libellés canoniques** après normalisation |
| `theme2_niv1` · `theme2_niv2` | texte ou vide | annotation |
| `sentiment` | `Négatif` / `Neutre` / `Positif` ou vide | **unique par verbatim** (D-26) |
| `signal` | texte ou vide | valeur canonique unique (§8.3) |
| `__anomalies__` | liste | codes des anomalies détectées sur la ligne (§9) |

**Note sur `sentiment`** : une seule colonne, conformément à D-26. La règle « sur sentiments
divergents, seul le thème négatif est retenu » est **déjà présente dans les labels Cultura**
(bi-thèmes négatifs à 72,6 % contre 25,5 % pour les mono-thèmes) : le chargeur n'a **rien** à
faire de particulier, et le modèle l'apprendra par supervision.

---

## 3. Les 4 sources et leurs 5 schémas

| Source | Schéma | Fichiers de référence | Colonnes | Champs libres |
|---|---|---|---|---|
| `MDTC-postachat` | A | `MDTC-postachat-juil26-nouveauancien.csv`, `MDTC-postachat3108-week35.csv`, `MDTCPostachatW34.csv`, `PostachatW32-TRANSMIS.csv` | 14 | **3** |
| `MDTC-postrecep` | B | `postRécep-W32.csv`, `MDTC-postrécep-juil26-anciennouveau-2.xlsx` | 12 | **1** |
| `Mopinion-desktop` | C | `Mopinion-Desktop-0101au13052026.csv` | 31 | **2** |
| `Mopinion-mobile` | D | `mopinion-mobile-0101au13052026.csv`, `mopinion_Mobile-aout2026.csv` | 33 | **4** |

**Formats de fichier** : CSV séparateur `;`, encodage à détecter dans l'ordre `utf-8-sig`,
`cp1252`, `iso-8859-1` ; et XLSX. Les deux doivent être pris en charge pour une même source
(`MDTC-postrecep` existe dans les deux formats).

**Détection de la source** : par correspondance du jeu de colonnes normalisées, **jamais par le
nom du fichier** (les noms sont libres : `PostachatW32-TRANSMIS`, `MDTCPostachatW34`…).

---

## 4. Normalisation des noms de colonnes — R-18

Les libellés varient entre exports d'une même source. Divergences mesurées sur
`Mopinion-mobile` :

| jan-mai 2026 | août 2026 |
|---|---|
| `Avez-vous une remarque ou des idées à nous partager ?\x0b` | `… partager ??` |
| `Ce n'est pas cela ? Décrivez-nous le problème.\x0b` | `… le problème.?` |

> ⚠️ **Le caractère `\x0b`** (tabulation verticale) est présent en fin de libellé dans l'export
> jan-mai. Il est **invisible** à l'affichage et casse tout appariement littéral. C'est la cause
> réelle de la divergence, pas seulement le `?` final.

**Fonction de normalisation à appliquer avant tout appariement :**

1. Supprimer les **caractères de contrôle** (`\x00`–`\x1f`) et l'espace insécable (`\xa0`).
2. Remplacer l'apostrophe typographique `’` par `'`.
3. Réduire toute suite d'espaces à un espace unique.
4. Supprimer la ponctuation et les espaces **en fin** de libellé : `[?!.\s]+$`.
5. Passer en minuscules.

> ⚠️ **Ne pas toucher aux traits d'union.** `Dites-nous en plus :` et `Dites nous en plus :`
> sont **deux colonnes distinctes coexistant dans le même fichier** Mopinion mobile. Une
> normalisation qui les fusionnerait perdrait des verbatims.

**Contrôle obligatoire** : après normalisation, vérifier qu'aucune collision ne s'est produite à
l'intérieur d'un même fichier. Si deux colonnes distinctes obtiennent le même nom normalisé,
**échouer** (§9).

---

## 5. Composition du verbatim — D-17 amendée par D-30

> **D-30 (09/09).** La règle de composition est **définie par source**, et non uniformément.
> Motif mesuré : **l'annotation Cultura porte sur le répondant, pas sur le champ.** Preuve —
> quand « Produits non trouvés » est rempli, le thème annoté est dispersé (Général 16, Choix
> produit 12, Cartes cadeaux 10, dont « Payer avec une carte cadeau » 6) : aucun lien avec un
> produit introuvable. L'annotateur a lu la *Justification*.
>
> Appliquer D-17 uniformément produirait **1 154 verbatims (14 % du corpus) porteurs d'une
> annotation recopiée depuis un autre champ** — 44 % de MDTC post-achat. C'est du bruit
> d'étiquetage *cohérent*, donc invisible dans les métriques : le pire type.

### 5.1 Règle par source

| Source | Règle | Verbatims | Annotation recopiée |
|---|---|---|---|
| `MDTC-postachat` | **Concaténer** `Justification niveau de satisfaction` + `Suggestion d'amélioration`. **Exclure** `Produits non trouvés`. | 1 928 | **0** |
| `MDTC-postrecep` | Champ unique, rien à décider | 3 869 | 0 |
| `Mopinion-desktop` | **Un verbatim par champ** (D-17) | 537 | 0 (2 cas) |
| `Mopinion-mobile` | **Un verbatim par champ** (D-17) | 1 218 | 0 (4 cas) |
| **Total** | | **7 552** | **0** |

**Rationnel MDTC post-achat** : `Justification` et `Suggestion d'amélioration` sont deux
formulations du même retour, par le même client, sur la même commande — c'est exactement ce que
faisait l'ancien chargeur (« concaténation `justification. suggestion` »). Séparation par
`". "`.

**Rationnel de l'exclusion de `Produits non trouvés`** : 104 valeurs, **100 % au format
« Rayon : Produit »** (« Jouets & Activités : Lego », « Livre : Dictionary of colors »),
médiane 8 mots, et seulement 8 sur 104 contiennent un verbe d'opinion. Ce n'est pas un verbatim
mais une **donnée structurée**. À conserver en colonne de contexte
(`__produit_non_trouve__`) si Cultura y voit un usage, jamais comme texte à classer.

**Rationnel Mopinion** : D-17 s'applique, le multi-champs y est marginal (6 répondants annotés
sur 1 545).

**Arbitrage assumé** : 684 verbatims de moins qu'en appliquant D-17 partout, contre
l'élimination de 1 154 labels potentiellement faux.

### 5.2 Règles communes

### Champs libres par schéma (noms canoniques)

**Schéma A — MDTC post-achat** *(concaténés en un seul verbatim, cf. §5.1)*
- `Justification niveau de satisfaction`
- `Suggestion d'amélioration`
- ~~`Produits non trouvés`~~ — **exclu**, donnée structurée « Rayon : Produit »

**Schéma B — MDTC post-réception**
- `Justification niveau de satisfaction`

**Schéma C — Mopinion desktop**
- `Merci ! Avez vous tout de même une remarque ou un message pour nos équipes ?`
- `Décrivez nous votre problème`

**Schéma D — Mopinion mobile**
- `Avez-vous une remarque ou des idées à nous partager ?`
- `Ce n'est pas cela ? Décrivez-nous le problème.`
- `Décrivez-nous le problème.?`
- `Dites-nous en plus sur votre problème.?`

### Règles

1. Un champ vide, ou ne contenant que des espaces, de la ponctuation seule ou `nan`, **ne
   produit aucune ligne**.
2. `__field__` porte le nom canonique du champ, `__respondent_id__` l'identifiant du répondant.
3. **Aucune annotation n'est recopiée** : c'est l'objet de D-30. Sur MDTC la concaténation
   ramène le verbatim au niveau du répondant, qui est le niveau de l'annotation ; sur Mopinion
   les 6 cas de multi-champs annotés sont marqués `ANNOTATION_RECOPIEE` et écartés de
   l'entraînement.
4. Sur les répondants **non annotés**, la règle de composition s'applique à l'identique : ces
   verbatims servent à l'inférence, pas à l'entraînement.

### Identifiant du répondant

| Schéma | Source de `__respondent_id__` |
|---|---|
| C, D (Mopinion) | colonne `id` (unique : 904/904, 13 720/13 720, 1 001/1 001) |
| A, B (MDTC) | **aucun identifiant** → générer `<source>-<fichier>-<index de ligne>` |

---

## 6. Colonnes ingérées et écartées — D-18

### Ingérées

| Colonne interne | Schémas A, B | Schémas C, D |
|---|---|---|
| `__page_type__` | absente | `Website data:window.tc_vars.page_type` — **rempli à 100 %** |
| `__url__` | absente | `url` |
| `__device__` | absente | `Device` |
| `__date__` | `Date de réponse` | `Datetime` |

### Écartées — ne doivent jamais atteindre la base

`User Agent` · `Contentsquare session recording` · `Selected screenshot HTML` · `Une image vaut
mille mots…` (URL de capture) · `Pour identifier les problèmes, votre adresse email…` ·
`Viewport` · `Browser` · `OS` · `Form trigger` · `Form completion percentage` · `Page title` ·
`Ending element` · `tags` · `survey` · `Website data:tc_vars. page_cat1_name`

**Également écartées, par la réponse A5 de Cultura** (« ne pas prendre en compte les étiquettes,
s'appuyer uniquement sur les commentaires pour les 2 outils ») — les sujets cochés par le client :

`Quel problème avez-vous rencontré ?` · `Quel est le problème que vous rencontrez ?` ·
`Sur quel sujet porte votre question ?` · `Dites-nous en plus :` · `Dites nous en plus :` ·
`Concernant votre commande déjà passée, quel est votre besoin ?` ·
`Aidez-nous à améliorer l'expérience sur le site. Qu'est ce qui vous pose problème ?`

> **D-19 est annulée** par cette réponse. Ces colonnes ne sont ni des étiquettes, ni des
> variables d'entrée. Conséquence favorable : **un seul modèle, même comportement sur MDTC et
> Mopinion** — R-15 et R-16 disparaissent en tant que risques d'asymétrie.

### Cas particulier — `Client`

`Client` (`Nouveau` / `Ancien`) existe dans les schémas A et B, mais est **vide dans 4 fichiers
sur 6**. Non ingérée : trop lacunaire pour être exploitable. À reconsidérer si Cultura la
renseigne systématiquement.

### Liste configurable

La liste des colonnes ingérées doit être **déclarée en configuration**, non codée en dur
(ENF-8), pour que Q-19 (validation RGPD) puisse être tranchée sans modifier le code.

---

## 7. Échelles de satisfaction — D-20

Trois échelles hétérogènes. **Le score de recommandation n'est pas retenu** (il mesure
l'intention de recommander la marque, pas le vécu de l'expérience décrite).

| Schéma | Colonne retenue | Valeurs observées | Normalisation |
|---|---|---|---|
| A, B | `Satisfaction` | 1, 2, 3, 4 | identité |
| C | `Quel est votre degré de satisfaction concernant Cultura ?` | 1 à 5 | → 1–4 (§7.1) |
| D | `Quel est votre degré de satisfaction concernant le site de Cultura ?` | 1 à 5 | → 1–4 (§7.1) |

`Recommandation` (0–10, schémas A et B) est conservée en traçabilité seulement, jamais utilisée
comme entrée modèle.

### 7.1 Conversion 1–5 → 1–4

**Aucune table officielle Cultura n'existe** (question A6 restée sans réponse). Proposition
eXalt, à faire valider (Q-17) :

| Mopinion (1–5) | MDTC (1–4) |
|---|---|
| 1 | 1 |
| 2 | 2 |
| 3 | 2 |
| 4 | 3 |
| 5 | 4 |

**Rationnel** : l'échelle MDTC à 4 modalités est symétrique sans point neutre
(« Pas du tout satisfait » → « Très satisfait ») ; l'échelle Mopinion à 5 a un point milieu.
Le 3 de Mopinion est rabattu vers l'insatisfaction plutôt que vers la satisfaction, cohérent
avec le fait que ces formulaires recueillent des irritants.

> ⚠️ **Cette conversion est une hypothèse eXalt, marquée comme telle.** Elle influence
> directement la comparaison de volumes entre sources (O-3). À faire valider avant de
> communiquer le moindre chiffre agrégé à Cultura.

### 7.2 Le préfixe de satisfaction

`src/utils/features.py` produit `[SATISFACTION 3/10]`. **L'échelle est désormais sur 4, pas
sur 10.** Le préfixe doit devenir `[SATISFACTION 3/4]`, et la fonction doit être appelée à
l'identique à l'entraînement et à l'inférence — le code le signale déjà en capitales.

---

## 8. Normalisation des labels

C'est la partie absorbée depuis l'ancien lot L14. **233 lignes bloquantes et 887 lignes de
signaux** sont concernées.

### 8.1 Thèmes de niveau 1

| Valeur observée | Occurrences | Traitement |
|---|---|---|
| `Attente commande` | **208** | → libellé canonique du référentiel |
| `Attente commmande` | **132** | → libellé canonique du référentiel |
| `réception commande` | 1 | → `Réception commande` (casse) |
| `Recherche` | 1 | → `Recherche produit` |
| `Autre programme fidélité` | 1 | **sous-thème dans la colonne thème** → anomalie, ligne écartée |
| `Modes de livraison` | 1 | **sous-thème dans la colonne thème** → anomalie, ligne écartée |
| `Insatisfaction` | 1 | **valeur de signal dans la colonne thème** → anomalie, ligne écartée |

> **Les deux graphies « Attente comm(m)ande » coexistent** — 208 contre 132. Quelle que soit
> celle que Cultura retient dans son référentiel, **il faut un mapping** : sans lui, on perd
> 208 ou 132 lignes selon le choix. C'est ce qui rend **D-27 optionnelle** : la transcription
> Cultura peut rester inchangée, le chargeur absorbe l'écart.
>
> Le libellé canonique est **celui du référentiel** (D-7). Le mapping est une table de synonymes
> déclarée en configuration, pas une correction du fichier Cultura.

**À demander à Cultura** : figer la graphie dans les prochaines livraisons, pour éviter qu'une
troisième variante apparaisse.

### 8.2 Sous-thèmes de niveau 2

| Valeur observée | Occurrences | Traitement |
|---|---|---|
| `Suivi commande` | 5 | → `Suivi de commande` |
| `Gestion des points` | 1 | → `Gestion de points` |
| `SRC` | 2 | inconnu → anomalie, ligne écartée. **À faire expliciter par Cultura.** |
| `Passer commande` | 1 | thème dans la colonne sous-thème → anomalie, ligne écartée |
| `Négatif` | 1 | valeur de sentiment dans la colonne sous-thème → anomalie, ligne écartée |

Rapprochement à appliquer **avant** la table de synonymes : appariement tolérant sur la forme
normalisée (casse, accents, espaces, apostrophes) contre les libellés du référentiel — mécanisme
déjà éprouvé dans `app/worker/llm_common.py → map_llm_response()`.

### 8.3 Signaux — la normalisation la plus rentable

Les données fournissent **un champ à valeur unique**, et non trois booléens comme le contrat
actuel.

| Valeur observée | Occurrences | Valeur canonique |
|---|---|---|
| `Insatisfaction` | 519 | `insatisfaction` |
| **`Insatisfait`** | **368** | `insatisfaction` |
| `Churn` | 64 | `churn` |
| `Rupture` | 32 | `rupture` |

> **887 lignes, soit 90 % des signaux annotés.** Sans cette fusion, le modèle apprend **deux
> classes de 519 et 368** au lieu d'une seule de 887. C'est une ligne de configuration contre
> une division par deux du volume d'apprentissage du signal principal.

**Churn (64) et Rupture (32) restent trop rares pour être évaluables** : à porter au lot L4
(redéfinition des signaux, D-10) comme argument mesuré.

**Point de contrat à trancher en L4** : le champ est-il exclusif (un seul signal par verbatim,
ce que suggèrent les données) ou cumulable (trois booléens, ce que prévoit `OUTPUT_COLUMNS`) ?
Le chargeur produit `signal` (valeur unique) ; la conversion vers le contrat de sortie relève de
la couche de décision, pas du chargeur.

### 8.4 Couples (thème, sous-thème) invalides — non corrigés

**18 lignes, 0,25 % du corpus.** Le sous-thème et le thème existent, mais l'appariement est faux :
(Général, Retrait magasin) ×11, plus 7 cas isolés.

**Décision : ces lignes sont écartées de l'entraînement et journalisées, pas corrigées.** La
correction demande un jugement humain cas par cas, elle serait à refaire à chaque livraison, et
son gain est négligeable. Ces cas ont plus de valeur comme **matière première de l'atelier de
règles d'arbitrage** (L3) : les 11 occurrences de (Général, Retrait magasin) ne sont pas une
faute de frappe mais une divergence d'interprétation réelle.

### 8.5 Périmètre des sous-thèmes — D-32

Le chargeur marque, sans les supprimer, les annotations portant un sous-thème **sous le seuil de
10 exemples**. La liste des sous-thèmes hors périmètre est **calculée sur le corpus, puis figée
en configuration** — elle ne doit pas varier d'une exécution à l'autre, sinon l'espace de labels
change et invalide les modèles entraînés.

**16 sous-thèmes concernés** sur la livraison du 09/09 :

| Effectif | Sous-thèmes |
|---|---|
| 0 | `Académie / Rechercher une activité` · `Académie / Gérer ma réservation` · `Académie / Offrir une activité` · `Général / Expérience personnalisée` · `Réception commande / Commande marketplace reçue` |
| 1 | `Attente commmande / Attente commande marketplace` |
| 3 | `Cartes cadeaux / Retrouver ma carte cadeau Cultura` · `Cartes cadeaux / Autre carte cadeau` · `Recherche produit / Classification produits` |
| 5 | `Choix produit / Autre choix produit` · `Espace client / Autre espace client` |
| 6 | `Réception commande / Autre réception commande` |
| 7 | `Espace client / Données personnelles` · `Programme de fidélité / Perception` |
| 9 | `Espace client / Favoris` · `Réception commande / Retour produit` |

**Comportement attendu** : code d'anomalie `SOUSTHEME_HORS_PERIMETRE`, ligne **conservée** pour
l'entraînement du niveau 1 et **exclue** de l'entraînement du niveau 2. À l'inférence, ces
sous-thèmes ne sont jamais prédits : le modèle produit le thème de niveau 1 et le niveau 2 est
routé en validation humaine.

> `Académie` conserve `Réserver une activité` (24 exemples) et reste donc dans le périmètre au
> niveau 1. Seuls ses 3 sous-thèmes vides en sortent.

### 8.6 Sentiment

Trois valeurs attendues : `Négatif`, `Neutre`, `Positif`. Appariement tolérant. **572
verbatims sont annotés en thème sans sentiment** : `sentiment` reste vide, la ligne est
conservée pour l'entraînement thématique et exclue de l'entraînement du sentiment.

---

## 9. Validation et règles d'échec

**Principe : échouer bruyamment sur un défaut de structure, journaliser sur un défaut de
contenu.** Le chargeur actuel dégrade en silence — c'est ce qui a permis aux défauts du
prototype de rester invisibles deux mois.

### 9.1 Échec immédiat — la lecture s'arrête

| Condition | Motif |
|---|---|
| Aucun schéma ne correspond au jeu de colonnes normalisées | Un cinquième schéma est apparu (R-18) |
| Une colonne attendue par le schéma est absente | Le fichier n'est pas celui annoncé |
| Deux colonnes distinctes obtiennent le même nom normalisé | La normalisation est trop agressive (§4) |
| Le référentiel ne charge pas | À vérifier au démarrage, jamais en cours de traitement |
| Encodage indétectable | Éviter tout remplacement silencieux de caractères |

### 9.2 Anomalie journalisée — la ligne est écartée ou marquée

Codes à porter dans `__anomalies__` :

| Code | Signification | Volume mesuré |
|---|---|---|
| `THEME_INCONNU` | thème absent du référentiel après synonymes | 5 |
| `SOUSTHEME_INCONNU` | sous-thème absent après synonymes | 5 |
| `COUPLE_INVALIDE` | thème et sous-thème valides, appariement faux | 18 |
| `SENTIMENT_ABSENT` | thème annoté sans sentiment | 572 |
| `SIGNAL_INCONNU` | valeur de signal non répertoriée | 0 |
| `TEXTE_VIDE` | champ libre vide après nettoyage | – |
| `TEXTE_COURT` | sous le seuil `cleaning.min_tokens` | à mesurer (médiane 6 mots) |
| `ANNOTATION_RECOPIEE` | répondant Mopinion multi-champs annoté — écarté de l'entraînement | 6 |
| `SOUSTHEME_HORS_PERIMETRE` | sous-thème sous le seuil de 10 exemples (D-32) — conservé pour le niveau 1, exclu du niveau 2 | 58 lignes / 16 sous-thèmes |

### 9.3 Rapport de chargement — livrable obligatoire

Chaque exécution produit un rapport JSON : fichiers lus, schéma reconnu, lignes lues, verbatims
produits, décompte par code d'anomalie, synonymes appliqués et leur volume. **C'est ce rapport
qui rend la prochaine livraison Cultura indolore** : un simple diff dira si un nouveau défaut
est apparu.

---

## 10. Anonymisation

Inchangée dans son principe (ENF-5, ENF-6), avec trois points à traiter :

1. **Numéros de commande au format `P########`** — 7 occurrences mesurées. Le regex `ORDER_ID`
   actuel n'a **jamais** rencontré ce format (0 masquage sur les 7 000 du prototype). **À tester
   explicitement.** Un format long sans préfixe existe aussi (5 occurrences).
2. **E-mails partiellement masqués par Cultura** (`******@free.fr`) — 10 occurrences. Le masquage
   amont existe mais est incomplet. Le regex doit accepter les astérisques dans la partie locale.
3. **Mode dégradé de spaCy silencieux** (T5, R-14). Le chargeur doit **vérifier explicitement la
   présence de spaCy au démarrage** et échouer si `anonymization.enabled` est vrai sans spaCy —
   plutôt que de continuer avec les regex seules en émettant un avertissement que personne ne lit.

---

## 11. Tests d'acceptation du lot

Le chargeur est réputé conforme quand :

- ☐ Les 9 fichiers réels sont lus, schéma correctement reconnu pour chacun
- ☐ **7 552 verbatims produits** : 1 928 MDTC post-achat + 3 869 MDTC post-réception + 537 Mopinion desktop + 1 218 Mopinion mobile (D-30)
- ☐ `Produits non trouvés` ne produit **aucun** verbatim, et ses 104 valeurs sont conservées en colonne de contexte
- ☐ Sur MDTC post-achat, `Justification` et `Suggestion d'amélioration` sont concaténées par `". "`
- ☐ Les deux exports Mopinion mobile sont lus **malgré** leurs libellés divergents (§4)
- ☐ `Dites-nous en plus :` et `Dites nous en plus :` restent **deux colonnes distinctes**
- ☐ Un fichier amputé d'une colonne attendue **échoue explicitement**
- ☐ Un fichier avec un cinquième schéma **échoue explicitement**
- ☐ Les 340 lignes « Attente comm(m)ande » sont toutes rattachées au libellé canonique
- ☐ Les 887 lignes `Insatisfaction` / `Insatisfait` produisent une seule valeur canonique
- ☐ Les 18 couples invalides sont écartés et journalisés, non corrigés
- ☐ Aucune colonne écartée par D-18 n'apparaît en sortie
- ☐ Le rapport de chargement est produit et ses décomptes correspondent à l'audit
- ☐ `P########` est effectivement masqué
- ☐ spaCy absent → échec explicite, pas de mode dégradé silencieux
- ☐ Le jeu factice (`scripts/generate_fake_dataset.py`) est lu par le même chargeur
- ☐ Les recettes existantes V1, V3, V4, V5, V6 restent au vert

---

## 12. Charge et dépendances

| Élément | Valeur |
|---|---|
| **Charge** | **4 j** (± 1) — 3 j de chargeur, 1 j de normalisation des labels absorbée depuis L14 |
| Dépendances | Aucune. **Réalisable immédiatement**, sans attendre la re-livraison Cultura. |
| Bloque | L2 (protocole et baseline), puis tout le chemin critique |
| Porteur | Data scientist. Les tables de synonymes et de conversion peuvent être fournies en configuration par l'agent. |

---

## 13. Questions ouvertes créées par cette spécification

| # | Question | Destinataire |
|---|---|---|
| **Q-22** | Que signifie le sous-thème `SRC` (2 occurrences) ? | Cultura |
| **Q-23** | Validation de la table de conversion 1–5 → 1–4 (§7.1) | Cultura — relance de A6 |
| **Q-24** | Figer la graphie de « Attente comm(m)ande » dans les prochaines livraisons | Cultura |
| **Q-25** | Un répondant multi-champs peut-il être annoté **par champ** plutôt qu'une fois pour tous ? Volume à mesurer d'abord (§5). | Cultura, après mesure en L2 |
| **Q-26** | La colonne `Client` sera-t-elle renseignée systématiquement ? | Cultura |
| **Q-27** | **Un cinquième des verbatims (1 393, 19,7 %) est classé `Général / Autre`** : le référentiel ne couvre pas ce que les clients écrivent. Cultura peut-il faire relire ces verbatims pour en faire émerger les sous-thèmes manquants ? | Cultura — c'est le travail le plus rentable pour la qualité du modèle **et** pour la priorisation des chantiers (D-33) |
| **Q-28** | Confirmer le libellé : le référentiel dit `Gérer ma réservation`, le PO cite « Gérer une activité ». Écart sans conséquence sur D-32 (les deux sont à 0 exemple) mais à figer. | Cultura |

---

## 14. Journal des mises à jour

| Version | Date | Modification |
|---|---|---|
| v1.0 | 09/09/2026 | Version initiale, sur la livraison Cultura du 09/09 (10h27). |
| **v1.1** | **09/09/2026** | **Livraison v2 (14h17)** enregistrée sous `data/raw/cultura_2026/v2_20260909/`, la v1 conservée pour audit. Delta mesuré : **zéro annotation supplémentaire** (7 068 → 7 068), uniquement des réaffectations — 23 annotations basculées de `Passer commande / Autre passer commande` vers `Académie / Réserver une activité`, 1 exemple ajouté à chacun des 2 sous-thèmes marketplace, 1 correction ponctuelle. Couverture : 52/59 → **56/59**. Référentiel **inchangé** (md5 identique). |
| v1.1 | 09/09/2026 | Ajout du §8.5 (périmètre des sous-thèmes, D-32) et du code d'anomalie `SOUSTHEME_HORS_PERIMETRE`. Ajout de Q-27 (le fourre-tout `Général / Autre`) et Q-28 (libellé Académie). |

---

*Projet interne Cultura / eXalt — usage confidentiel.*
