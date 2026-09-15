# Atteindre les performances sans dépendre de Cultura — campagne d'optimisation

> **Question posée.** « Propose-moi une solution ne nécessitant pas l'aide de
> Cultura pour obtenir les performances requises. »
>
> **Réponse courte.** Trois leviers de la couche de décision rapportent
> **+3,6 points de F1-macro et −32 % de faux seconds thèmes**, sans
> réentraînement ni annotation. En revanche la cible « précision du second thème
> ≥ 0,70 » reste inatteignable — et j'ai identifié pourquoi, ce qui change la
> recommandation : **ce n'est pas un problème de volume d'annotation.**
>
> **Statut.** v1.2 — 11 septembre 2026, après les arbitrages du PO.
>
> ---
>
> ⚠️ **CORRECTION — les trois leviers ont été industrialisés le 11/09.** Mesurés
> avec l'implémentation de production, **deux affirmations de ce document ne
> tiennent pas** :
>
> * le gain total est de **+2,75 points** de F1-macro, non +3,6 ;
> * la règle post-réception **n'est pas** le levier le plus rentable — c'est le
>   plus petit des trois, et à sa marge d'origine elle cassait autant de
>   décisions qu'elle en corrigeait.
>
> Les écarts du §1 venaient d'une réimplémentation simplifiée de la décision.
> Le document le signalait ; j'aurais dû en conclure que **les écarts eux-mêmes**
> n'étaient pas fiables, pas seulement les valeurs absolues.
>
> **Chiffres qui font foi : [`COUCHE_DECISION.md`](COUCHE_DECISION.md).**
> Le raisonnement ci-dessous — le diagnostic, les pistes écartées, le
> remplacement de cible proposé — reste valable ; seules les grandeurs du §1 et
> du §1.1 sont périmées.

---

## 1. Ce qui marche — cumulatif, mesuré sur le jeu de test gelé

> ⚠️ **Table périmée.** Conservée pour trace de ce qui a été annoncé au PO.
> Les valeurs vérifiées sont dans [`COUCHE_DECISION.md §3`](COUCHE_DECISION.md).

| Configuration | Accuracy | F1-macro | Précision 2ᵉ | Faux 2ᵉ | Bi-thèmes |
|---|---|---|---|---|---|
| Actuel (seuil unique 0,85) | 0,7327 | 0,6349 | 0,2169 | 0,0728 | 8,2 % |
| + règle post-réception | 0,7545 | 0,6405 | 0,2169 | 0,0728 | 8,2 % |
| + seuils par thème | 0,7545 | 0,6536 | 0,1930 | 0,0974 | 11,3 % |
| **+ suppression des paires** | **0,7545** | **0,6704** | **0,2456** | **0,0492** | **5,6 %** |

*(Réimplémentation simplifiée de la décision. Je pensais les écarts fiables même
si les valeurs absolues ne l'étaient pas — ils ne l'étaient pas non plus.)*

**Mesure de référence, implémentation de production, même jeu de test (n = 1 010) :**

| Configuration | F1-macro | Précision 2ᵉ | Faux 2ᵉ | Bi-thèmes |
|---|---|---|---|---|
| Seuil unique 0,85 | 0,6647 | 0,1833 | 4,92 % | 5,94 % |
| + seuils par thème | 0,6683 | 0,2121 | 5,33 % | 6,53 % |
| + arbitrage par source | 0,6688 | 0,2121 | 5,33 % | 6,53 % |
| **+ suppression des paires** | **0,6922** | **0,4000** | **2,05 %** | **2,97 %** |

*(Configuration arbitrée par le PO le 11/09 : la paire
`Cartes cadeaux / Passer commande` est retirée — elle dégradait `Passer commande`
sans rien apporter à `Cartes cadeaux`.)*

### 1.1 La règle post-réception — le levier le plus rentable

**38,6 % de toutes les erreurs de thème** sont un seul motif : `Réception
commande` prédit `Général`. Sur 102 cas, **93 viennent du formulaire MDTC
post-réception**, annotés `Retrait magasin` (61) ou `Conformité commande` (37),
sur des textes comme :

> « C'était rapide » · « code à scanner, facile, rapide, efficace » ·
> « bons conseils, commande facile et rapide » · « aucune attente personnel disponible »

**Le modèle a raison du point de vue du texte seul** : rien n'y désigne un
retrait en magasin. L'annotateur, lui, savait de quel formulaire venait la
réponse. La règle rétablit ce contexte :

> Sur la source `MDTC-postrecep`, un `Général` dont l'avance sur
> `Réception commande` est inférieure à la marge bascule vers
> `Réception commande`.

**Le diagnostic tient. Le chiffrage, non.** J'annonçais 24 erreurs corrigées
pour 2 créées ; l'implémentation de production, à la marge de 0,6, en corrige
**9 et en casse 8** sur la validation. La marge avait été calée avant
l'existence des seuils par thème, qui arbitrent déjà entre ces deux thèmes :
la règle rejouait un arbitrage déjà rendu, et moins bien.

Recalibrée à **0,30** (`scripts/calibrer_regle_source.py`) : 4 corrections,
0 dégradation. Le levier est réel mais **petit** — c'est le plus faible des
trois, pas le plus fort. Détail : [`COUCHE_DECISION.md §4`](COUCHE_DECISION.md).

### 1.2 Seuils par thème

Un seuil unique traite de la même façon un thème à 40 % du corpus et un thème à
0,4 %. Seuils calés par classe sur la validation : `Général` 0,75,
`Réception commande` 0,80, `Bug` 0,95, `Recherche produit` 0,60. **+1,3 point de
F1-macro** — mais au prix d'une hausse des bi-thèmes, que le levier suivant
corrige.

### 1.3 Suppression des paires qui se recouvrent

Deux paires de thèmes sont proposées ensemble sur des verbatims **mono**-thème :
`Cartes cadeaux ↔ Passer commande` (31 cas) et `Choix produit ↔ Recherche
produit` (23 cas). Ce n'est pas un second sujet, c'est **une hésitation entre deux
étiquettes pour le même sujet**.

**C'est le levier le plus rentable des trois** — mesuré, cette fois : il porte
**+0,0234 des +0,0275** points de F1-macro gagnés, ramène le taux de faux second
thème de 5,33 % à **2,05 %** et fait passer la précision du second thème de
0,2121 à **0,4000**.

Les deux paires ne se valaient pas. `Choix produit ↔ Recherche produit` est
indispensable ; `Cartes cadeaux ↔ Passer commande` coûtait 5,6 points de F1 à
`Passer commande` sans rien apporter à `Cartes cadeaux`. **Le PO l'a retirée le
11/09**, et le recouvrement des deux libellés est remonté à l'atelier L3 —
cf. [`COUCHE_DECISION.md §5`](COUCHE_DECISION.md).

---

## 2. Ce qui ne marche pas — et pourquoi

| Piste | Résultat mesuré |
|---|---|
| **Jeu factice reprojeté** | ❌ dégrade les **trois** tâches |
| **Préfixe de source dans le texte** | ❌ aucun gain (0,5030 contre 0,5098) |
| **Correction par priors de classe** | ❌ diverge et détruit le modèle |
| **Prior de source à la décision** | ⚖️ +1,25 accuracy mais **−4,8 F1-macro** |
| **Nettoyage de la référence** | ❌ 17 suspects sur 6 907, et tous légitimes |

### Le jeu factice : reprojection réussie, transfert nul

La table de correspondance couvre **67 couples anciens sur 67**, sans cible
invalide. L'augmentation portait les bi-thèmes du train de 220 à **502** et le
churn de 47 à **266**. Et pourtant :

* `insatisfaction` : F1 0,5833 → **0,5472**
* niv1 : derrière à chaque époque dès la 4ᵉ (0,4677 → **0,4182** à la 6ᵉ)
* churn : AUC 0,7598 → 0,8562, **mais** précision 0,200 → 0,133

Le texte est synthétique : le modèle apprend les tournures du générateur. Le
classement s'améliore parfois, le point de fonctionnement se déplace au mauvais
endroit. **Recommandation : ne pas l'utiliser.**

### Le préfixe de source : information réelle, mais redondante

La source porte **0,508 bit** sur le thème — 22,7 % de réduction d'entropie.
L'hypothèse était donc fondée. Elle échoue parce que **la source est déjà
retrouvable à 75,6 % depuis le seul texte** (contre 54,1 % pour la classe
majoritaire) : CamemBERT extrait cette information du style d'écriture, le
préfixe explicite n'ajoute rien.

C'est pourquoi la **règle ciblée** (§1.1) fonctionne là où le préfixe échoue :
elle n'informe pas le modèle, elle **arbitre à sa place** sur le cas précis où
il ne peut pas trancher.

---

## 3. Pourquoi la cible du second thème est hors d'atteinte

J'ai annoté 52 propositions de second thème — 22 en validation, 30 sur la liste
de candidats. Le rendement est très faible :

* **~1 sur 30 est un second sujet clairement légitime**
* **9 sur 30 sont la paire `Choix produit ↔ Recherche produit`** — une hésitation
* **6 sur 30 ont le « second thème » égal au thème 1 annoté** — le modèle hésite
  entre deux libellés, et sa deuxième proposition est la bonne

**Conclusion : ce que la métrique compte comme « faux second thème » n'est
majoritairement pas un second sujet inventé, mais une hésitation entre libellés
qui se recouvrent.** Annoter massivement n'y changerait rien — j'ai vérifié sur
762 candidats sélectionnés par le modèle, dont le rendement attendu est de 3 à
10 % de positifs.

**Le facteur limitant n'est donc pas le volume d'annotation, contrairement à ce
que j'affirmais.** Ce sont deux choses :

1. **La dépendance au contexte** — 38,6 % des erreurs sont du texte que le texte
   seul ne permet pas de classer. Traitée par la règle §1.1.
2. **Le recouvrement du référentiel** — traité partiellement par §1.3, mais qui
   relève sur le fond de l'atelier L3 et appartient à Cultura (D-7).

---

## 4. Recommandation

**Remplacer la cible « précision du second thème ≥ 0,70 »**, qui est une
proposition eXalt jamais validée (Q-9), mesurée sur 35 cas, et qui ne mesure pas
le besoin. Lui substituer :

> ✅ **Adopté par le PO le 11/09.** La précision du second thème devient un
> indicateur suivi ; les trois cibles ci-dessous sont les engagements.

| Engagement | Mesuré *(implémentation de production, configuration arbitrée)* | État |
|---|---|---|
| Taux de faux second thème ≤ 10 % | **2,05 %** | ✅ |
| Erreur sur les volumes (thème × sentiment) ≤ 15 % **au global** | **12,51 %** | ✅ |
| Part de sorties bi-thèmes dans un facteur 1,5 de la part annotée | **2,97 %** pour 3,47 % | ✅ |

**Les trois sont tenues.** Elles traduisent O-3 — des volumes fiables pour
prioriser — là où la précision du second thème mesurait autre chose.

Le PO a également tranché la maille de l'erreur de volume : **au global**. Les
quatre plus gros couples, ceux qui pilotent la priorisation, sont à 5-11 % ; les
écarts se concentrent sur les couples moyens où une dizaine de verbatims fait
bouger le pourcentage. Le détail par couple reste publié, en suivi.

---

*Projet interne Cultura / eXalt — usage confidentiel.*
