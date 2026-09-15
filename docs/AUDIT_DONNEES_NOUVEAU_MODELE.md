# Audit des données Cultura et du nouveau référentiel

> **Objet.** Lot **L1b** du plan. Auditer les données réelles et le référentiel livrés le
> 9 septembre 2026, et prononcer un verdict sur la faisabilité du périmètre.
>
> **Statut.** v1.0 — 9 septembre 2026.
> **Sources auditées.** 10 fichiers déposés dans `data/raw/cultura_2026/`.
> **Références.** `docs/CADRAGE_NOUVEAU_MODELE.md` (v1.2), `docs/PLAN_LOTS_NOUVEAU_MODELE.md` (v1.1).

---

## 1. Verdict

| Question | Réponse |
|---|---|
| Les données sont-elles réelles ? | **Oui.** 26 826 lignes de production, janvier à septembre 2026. |
| Sont-elles annotées ? | **Oui** — 7 068 lignes portent un thème (26,3 %). C'est le déblocage attendu : R-1 est levé. |
| Le référentiel charge-t-il ? | **Oui.** Aucun libellé de niveau 2 dupliqué → **L11 est écarté, 4 jours récupérés.** |
| Le sentiment est-il déductible de la note ? | **Non.** R-5 ne se réalise pas : la note à 3 est mélangée (537 négatifs, 431 positifs, 71 neutres). |
| **Le sentiment par thème est-il annoté ?** | **NON.** Une seule colonne `Sentiment` pour l'ensemble du verbatim. **D-1, la demande n°1, n'a ni donnée d'entraînement ni donnée d'évaluation.** |
| La qualité des labels est-elle exploitable ? | **Oui, après nettoyage.** ~3,4 % d'anomalies, dont une normalisation obligatoire sur 208 lignes. |

**Go sur le périmètre, avec deux réserves majeures** — le sentiment par thème (§5) et les
verbatims très courts (§7).

---

## 2. Le nouveau référentiel

`data/raw/cultura_2026/taxonomy_cultura_2026.json`, converti depuis le CSV Cultura.

**Ce n'est pas une évolution du 20/67 : c'est un remplacement total.** **11 thèmes, 59
sous-thèmes**, et **aucun libellé commun** avec l'ancien référentiel.

| # | Thème | Sous-thèmes |
|---|---|---|
| 0 | Académie | 4 |
| 1 | Attente commmande *(sic)* | 6 |
| 2 | Bug | 5 |
| 3 | Cartes cadeaux | 5 |
| 4 | Choix produit | 4 |
| 5 | Espace client | 6 |
| 6 | Général | 4 |
| 7 | Passer commande | 7 |
| 8 | Programme de fidélité | 3 |
| 9 | Réception commande | 10 |
| 10 | Recherche produit | 5 |

**Trois observations favorables :**

1. **L'invariant d'unicité est respecté.** `src/utils/taxonomy.py` lève une `ValueError`
   uniquement si un libellé de niveau 2 apparaît sous deux parents. Il n'y en a aucun — chaque
   thème dispose de son propre « Autre X ». **Le lot L11 (clé composite) est écarté :
   4 jours-homme récupérés, R-3 ne se réalise pas.** Note : Cultura avait répondu « oui » à la
   question B2 ; la réponse portait sur le principe, pas sur le fichier livré.
2. **Les libellés sont neutres** — « Suivi de commande », « Modes de paiement »,
   « Informations produit » — et non polarisés comme « Délai non respecté ». **La
   recommandation D-6 est donc satisfaite d'office** : la polarité sera portée par le sentiment,
   sans négociation. Le problème du sous-thème `Facile` (F1 0,154) et des contradictions
   d'annotation disparaît par construction.
3. **La structure suit le parcours client** (Recherche → Choix → Passer commande → Attente →
   Réception) plutôt que la nature de l'irritant. C'est plus cohérent, et les frontières sont a
   priori moins poreuses que dans l'ancien référentiel.

**Trois défauts à traiter :**

| Défaut | Détail | Conséquence |
|---|---|---|
| **Typo dans un libellé de thème** | « Attente comm**m**ande » (trois *m*) | L'ordre du JSON est figé et sert d'index d'encodage. Corriger le libellé **après** entraînement invaliderait les modèles. À trancher **avant** le lot L6. Voir §4 : les annotateurs ont déjà écrit la forme correcte 208 fois. |
| Espace parasite | « Perception  » (Programme de fidélité) | Rupture d'appariement silencieuse. À nettoyer au chargement. |
| 17 lignes vides | fin du CSV source | Écartées à la conversion. |

---

## 3. Volumétrie et taux d'annotation

| Fichier | Lignes | Annotées | % | Bi-thèmes | Champs libres |
|---|---|---|---|---|---|
| MDTC-postachat juil26 | 1 689 | 748 | 44,3 % | 90 | 3 |
| MDTC-postachat W35 | 575 | 376 | 65,4 % | 46 | 3 |
| MDTC-postachat W34 | 631 | 154 | 24,4 % | 27 | 3 |
| MDTC-postachat W32 | 560 | 376 | 67,1 % | 65 | 3 |
| MDTC-postrécep W32 | 899 | 481 | 53,5 % | 14 | 1 |
| MDTC-postrécep juil26 | 6 847 | 3 388 | 49,5 % | 17 | 1 |
| Mopinion desktop | 904 | 654 | 72,3 % | **0** | 2 |
| Mopinion mobile jan-mai | 13 720 | 679 | 4,9 % | 27 | 4 |
| Mopinion mobile août | 1 001 | 212 | 21,2 % | 28 | 4 |
| **Total** | **26 826** | **7 068** | **26,3 %** | **314** | – |

**Le taux de 26,3 % ne traduit pas un défaut d'annotation.** La majorité des lignes non
annotées sont des réponses **sans texte libre** : le répondant a donné une note et n'a rien
écrit. Sur Mopinion mobile jan-mai, 13 720 lignes ne produisent que 733 textes. L'annotation
couvre donc bien l'essentiel du texte disponible.

**Textes exploitables : 8 236 occurrences, 6 595 uniques** (1 641 doublons, soit 19,9 % —
principalement des réponses très courtes répétées : « nul », « aucun », « très bien »).

> **Comparaison avec le prototype.** Le POC comptait 403 textes uniques dupliqués 17 fois pour
> simuler 7 000 lignes. Ici : **6 595 textes uniques réels**. C'est un ordre de grandeur
> au-dessus, et cette fois la mesure aura un sens.

**Bi-thèmes : 314, soit 4,4 % des annotations.** Dix fois plus que le prototype (0,4 %), mais
toujours faible — et **Mopinion desktop n'en compte aucun** (0 sur 654), ce qui suggère une
consigne d'annotation différente selon les sources.

---

## 4. Qualité des labels

**~240 anomalies sur 7 068 annotations, soit 3,4 %.** Exploitable après nettoyage, mais le
détail confirme R-10 : il n'existe ni règle d'arbitrage écrite, ni contrôle de saisie.

### 4.1 Thèmes hors référentiel

| Valeur observée | Occurrences | Nature |
|---|---|---|
| **« Attente commande »** | **208** | Les annotateurs ont spontanément corrigé la typo du référentiel. **Normalisation obligatoire.** |
| « Recherche » | 1 | libellé tronqué |
| « réception commande » | 1 | casse |
| « Autre programme fidélité » | 1 | **sous-thème saisi dans la colonne thème** |
| « Modes de livraison » | 1 | **sous-thème saisi dans la colonne thème** |
| « Insatisfaction » | 1 | **valeur de signal saisie dans la colonne thème** — décalage de colonnes |

### 4.2 Sous-thèmes hors référentiel

« Suivi commande » (5, pour « Suivi de commande ») · « Gestion des points » (1, pour « Gestion
de points ») · « SRC » (2) · « Passer commande » (1, thème saisi comme sous-thème) ·
**« Négatif » (1, valeur de sentiment saisie comme sous-thème)**.

### 4.3 Couples (thème, sous-thème) invalides — 8 cas

Le sous-thème existe, le thème existe, mais l'appariement est faux :

| Couple | Occurrences |
|---|---|
| (Général, Retrait magasin) | **11** |
| (Recherche produit, Satisfaction produit) | 1 |
| (Réception commande, Filtres/tris des pages liste) | 1 |
| (Réception commande, Commande annulée) | 1 |
| (Réception commande, Ergonomie/utilisabilité) | 1 |
| (Choix produit, Assortiment) | 1 |

> Le cas (Général, Retrait magasin) revient 11 fois : ce n'est pas une faute de frappe mais
> une **divergence d'interprétation** sur la frontière entre « Général » et « Réception
> commande ». Matière première de l'atelier de règles d'arbitrage (lot L3).

### 4.4 Couverture du référentiel

**52 des 59 sous-thèmes sont représentés.** Sept ne le sont jamais :

- **Les 4 sous-thèmes d'Académie** : Rechercher / Réserver / Gérer / Offrir une activité
- **Les 2 sous-thèmes marketplace** : Attente commande marketplace, Commande marketplace reçue
- Expérience personnalisée

**Un modèle supervisé ne peut pas apprendre une classe sans exemple.** Ces sept sous-thèmes
sont, en l'état, inatteignables. Deux options : les sortir du périmètre mesuré, ou demander à
Cultura des exemples ciblés.

---

## 5. Le sentiment — réserve majeure

### 5.1 Bonne nouvelle : le sentiment n'est pas une règle

Contrairement au prototype, où la note prédisait le sentiment sur 7 000 lignes sans une seule
exception, l'échelle réelle compte **4 modalités** et la correspondance est partielle :

| Note | Négatif | Neutre | Positif |
|---|---|---|---|
| 1 | 312 | 2 | 0 |
| 2 | 397 | 3 | 1 |
| **3** | **537** | **71** | **431** |
| 4 | 86 | 69 | **3 600** |

Les notes 1-2 et 4 sont quasi déterministes, mais **la note 3 est réellement ambiguë** : elle
se répartit entre négatif et positif. Il y a donc de l'information dans le texte que la note ne
porte pas. **R-5 ne se réalise pas, et EF-3 (non-trivialité du sentiment) devient mesurable.**

### 5.2 Réserve n°1 : aucun sentiment par thème

**Les fichiers ne contiennent qu'une seule colonne `Sentiment`, au niveau du verbatim.**

Conséquence directe et sévère : **la décision D-1 — chaque thème porte son propre sentiment,
la demande n°1 du métier — n'a ni donnée d'entraînement, ni donnée d'évaluation.** Sur les
314 verbatims bi-thèmes, il est impossible de savoir si les deux sujets portent des polarités
opposées : l'information n'a pas été saisie.

C'est exactement la situation du prototype (0 sentiment divergent sur 28 bi-thèmes), à ceci
près qu'elle est **identifiée maintenant, avant l'entraînement**, et non découverte après.

Trois voies, à trancher :

| Voie | Coût | Effet |
|---|---|---|
| Faire annoter le sentiment par thème sur les 314 bi-thèmes existants | faible — 314 cas, quelques heures | Rend EF-2 **mesurable**. Insuffisant pour entraîner, suffisant pour un jeu de recette. |
| Annoter au niveau du thème sur un échantillon plus large | moyen | Rend EF-2 entraînable |
| Renoncer à EF-2 pour cette itération | nul | La demande n°1 n'est pas livrée |

**Recommandation eXalt : la première voie, immédiatement.** 314 verbatims à relire est un
effort de quelques heures, et c'est la différence entre « on ne sait pas » et « on sait ».

### 5.3 Réserve n°2 : distribution très déséquilibrée

| Sentiment | Effectif | Part |
|---|---|---|
| Positif | 4 177 | **64,3 %** |
| Négatif | 1 948 | 30,0 % |
| **Neutre** | **371** | **5,7 %** |

La classe **Neutre est structurellement minoritaire** (371 exemples pour 3 classes). Dans le
prototype elle était à 33 % et plafonnait déjà à F1 0,360. À 5,7 %, elle sera plus difficile
encore. À anticiper dans les critères d'acceptation : une cible de F1-macro sur 3 classes sera
tirée vers le bas par Neutre, indépendamment de la qualité du modèle.

La dominance du positif s'explique : `MDTC-postrécep` pèse 3 388 annotations sur 7 068, et
c'est un questionnaire de satisfaction après réception, où les répondants sont majoritairement
contents. **L'évaluation séparée par source (R-16) est donc indispensable** : un modèle qui
apprend « positif par défaut » sur postrécep sera mauvais sur Mopinion mobile.

### 5.4 572 verbatims annotés en thème mais sans sentiment

À traiter explicitement : exclure de l'entraînement du sentiment, ou faire compléter.

---

## 6. Les signaux — changement de contrat

**Une seule colonne `Signaux`**, à valeur unique, avec un vocabulaire non normalisé :

| Valeur | Occurrences |
|---|---|
| Insatisfaction | 519 |
| **Insatisfait** | **368** |
| Churn | 64 |
| Rupture | 32 |

**« Insatisfaction » et « Insatisfait » sont le même signal**, écrit de deux façons selon les
fichiers. Après fusion : Insatisfaction 887, Churn 64, Rupture 32.

Deux écarts avec l'existant :

1. Le contrat actuel prévoit **trois booléens indépendants** (`signal_rupture_client`,
   `signal_churn`, `signal_insatisfaction_forte`). Les données fournissent **un champ à valeur
   unique** : un verbatim ne porte qu'un signal. Il faut trancher — cumul possible ou exclusif ?
2. **Churn (64) et Rupture (32) sont trop rares pour être évaluables.** Le prototype avait le
   même problème sur Rupture (1 positif en test). Avec 64 et 32 cas sur 7 068, les intervalles
   de confiance seront inexploitables. C'est un argument mesuré pour le lot L4 (redéfinition
   des signaux, D-10).

---

## 7. Les textes — réserve majeure

| Indicateur | Valeur |
|---|---|
| Caractères — min / p25 / médiane / p75 / p95 / max | 1 / 18 / **36** / 73 / 201 / 1 251 |
| Mots — médiane / max | **6** / 192 |

**La médiane est de 36 caractères et 6 mots.** Le premier quartile est à 18 caractères. Des
exemples réels observés : « nul », « aucun », « , très bien », « . », « Musique Abba ».

C'est la réserve la plus sous-estimée de cet audit. Un verbatim de 6 mots porte très peu
d'information : attribuer un thème **et** un sous-thème **et** un sentiment sur « très bien »
est hors de portée de tout modèle, et l'était aussi pour l'annotateur humain.

Conséquences à porter aux critères d'acceptation :

- Le filtre `cleaning.min_tokens: 5` écarterait une part importante du corpus. À mesurer et à
  arbitrer explicitement plutôt qu'à subir.
- Les cibles de performance doivent être **conditionnées à la longueur du verbatim**. Une
  métrique globale mélangera des cas impossibles et des cas traitables, et ne pilotera rien.
- **Recommandation** : mesurer la baseline par tranche de longueur, et négocier avec Cultura le
  périmètre des verbatims réellement classifiables.

Le prototype avait des textes de 29 à 90 caractères, médiane 63 — **plus longs et plus réguliers
que la réalité**. Ses métriques étaient donc optimistes pour cette raison aussi.

---

## 8. Données personnelles

| Motif | Textes concernés | Part |
|---|---|---|
| Adresse e-mail | 10 | 0,1 % |
| Téléphone | 1 | 0,0 % |
| Numéro de commande `P######` | 7 | 0,1 % |
| Numéro long (7+ chiffres) | 5 | 0,1 % |
| Majuscules d'intensité (4+ lettres) | 123 | 1,5 % |

**Volume faible mais non nul.** Trois points :

1. Certains e-mails sont **déjà partiellement masqués par Cultura** (`******@free.fr`) — le
   masquage amont existe mais est incomplet.
2. Le format de numéro de commande observé est **`P########`**, que le regex `ORDER_ID` du
   projet n'a jamais rencontré (0 masquage sur les 7 000 du prototype). **À tester
   explicitement.**
3. Les 123 verbatims en majuscules confirment l'intérêt de tester `lowercase: false` : le
   réglage actuel détruit ce signal d'intensité avant le modèle de sentiment.

### 8.1 Alerte de conformité — traitée

Le `.gitignore` racine **ne couvre pas `data/raw/`** et porte le commentaire « données
simulées, aucune PII réelle » — qui n'est plus vrai. Un `.gitignore` protecteur a été déposé
dans `data/raw/cultura_2026/` pour empêcher tout versionnement de ces données. **Le commentaire
du `.gitignore` racine doit être corrigé**, sans quoi le prochain contributeur reproduira le
risque.

---

## 9. Schémas de fichiers

**Quatre sources, cinq schémas distincts** — et les noms de colonnes ne sont pas stables entre
exports de la même source :

| Source | Colonnes | Champs libres |
|---|---|---|
| MDTC post-achat | 14 | 3 |
| MDTC post-réception | 12 | 1 |
| Mopinion desktop | 31 | 2 |
| Mopinion mobile (jan-mai) | 33 | 4 |
| Mopinion mobile (août) | 33 | 4, **aux libellés différents** |

Divergences mesurées entre les deux exports Mopinion mobile :

| jan-mai 2026 | août 2026 |
|---|---|
| `Avez-vous une remarque ou des idées à nous partager ?` | `… partager ??` |
| `Ce n'est pas cela ? Décrivez-nous le problème.` | `… le problème.?` |

**R-18 est confirmé et mesuré.** Le chargeur doit **normaliser** les noms de colonnes (espaces,
ponctuation finale) et **échouer explicitement** sur une colonne attendue manquante, plutôt que
de dégrader en silence. C'est une exigence du lot L1a.

Autres écarts par rapport aux maquettes du 12 août : les colonnes réelles diffèrent des
maquettes (`Satisfaction` et non `Niveau de satisfaction`, `Recommandation` et non
`score RECO`, `Justification niveau de satisfaction` et non `Justification du niveau de
satisfaction`, `Client` et non `Ancienneté client`). **Les maquettes ne sont pas fiables pour
spécifier le chargeur : seuls les fichiers réels font foi.**

Enfin, `Client` (Nouveau / Ancien) est renseigné dans deux fichiers et **vide dans quatre
autres**.

---

## 10. Ce que cet audit change au plan

| Élément | Avant | Après |
|---|---|---|
| **L11** clé composite | conditionnel, 4 j, bloquant | **écarté** — invariant respecté |
| **R-3** référentiel non chargeable | moyenne / élevé | **ne se réalise pas** |
| **R-5** sentiment déductible de la note | moyenne / critique | **ne se réalise pas** |
| **R-1** absence de données annotées | forte / élevé | **levé** — 7 068 annotations réelles |
| **R-17** fichiers non représentatifs | certaine / critique | **levé** |
| **D-6** libellés neutres | recommandation à porter | **satisfaite d'office** |
| **EF-2** sentiment par thème | conditionnel à la donnée | **sans vérité terrain — réserve n°1** |
| **R-18** schémas instables | moyenne | **confirmé et mesuré** |
| **R-10** labels incohérents | moyenne à forte | **confirmé** — 3,4 % d'anomalies |
| Nouveau | – | **Verbatims très courts** (médiane 6 mots) — réserve n°2 |
| Nouveau | – | **Classe Neutre à 5,7 %** — plafond structurel sur le F1-macro sentiment |
| Nouveau | – | **7 sous-thèmes sans aucun exemple** — inapprenables |
| Nouveau | – | **Signaux : un champ à valeur unique**, pas trois booléens ; Churn et Rupture non évaluables |

**Bilan de charge : 4 jours récupérés** (L11 écarté), à réinvestir dans le nettoyage et la
normalisation des labels, non provisionnés jusqu'ici.

---

## 11. Actions immédiates recommandées

1. **Faire annoter le sentiment par thème sur les 314 bi-thèmes.** Quelques heures de travail,
   et c'est la seule voie pour rendre la demande n°1 mesurable.
2. **Trancher la typo « Attente commmande »** avant tout entraînement. Les annotateurs ont
   déjà écrit la forme correcte 208 fois.
3. **Normaliser le vocabulaire des signaux** (Insatisfaction / Insatisfait) et décider du
   caractère cumulable ou exclusif.
4. **Corriger le commentaire du `.gitignore` racine** sur `data/raw/`.
5. **Arbitrer les 7 sous-thèmes sans exemple** : hors périmètre mesuré, ou exemples à fournir.
6. **Mesurer la baseline par tranche de longueur de verbatim**, et non globalement.
7. **Spécifier le chargeur sur les fichiers réels**, pas sur les maquettes du 12 août.

---

*Projet interne Cultura / eXalt — usage confidentiel.*
