# Synthèse de cadrage — Nouveau modèle ML Cultura Verbatim Classifier

> **Document de référence transmissible.** Consolide le cadrage arrêté au 9 septembre 2026.
> Autonome : lisible sans les documents détaillés, auxquels il renvoie pour le détail.
>
> **Statut.** Cadrage **finalisé**. **Livraison cible : mardi 6 octobre 2026.**
> **Détail** : `CADRAGE_NOUVEAU_MODELE.md` (35 décisions), `AUDIT_DONNEES_NOUVEAU_MODELE.md`,
> `SPEC_CHARGEUR.md`, `PLAN_LOTS_NOUVEAU_MODELE.md`, `PROMPT_AGENT_IMPLEMENTATION.md`.

---

## 1. Le problème, en trois faits mesurés

**Le modèle actuel n'est pas « perfectible » : il n'a jamais été mesuré.**

1. Le jeu d'entraînement du prototype contenait **403 textes uniques** dupliqués 17 fois pour
   simuler 7 000 lignes. **99,6 % des lignes de test avaient un texte identique dans le train.**
   Toutes les métriques publiées sont invalides — y compris le F1-macro de 0,891 au niveau 2,
   qui mesurait de la mémorisation.
2. Le sentiment y était une **fonction déterministe de la note de satisfaction**, sans une seule
   exception sur 7 000 lignes. Il n'y avait aucune tâche de langage à apprendre.
3. Le grief métier — « le multi-thème ne fonctionne pas » — a été **mal diagnostiqué au
   départ**. Le modèle ne sous-active pas les thèmes : il en active trop (43,3 % de sorties
   bi-thèmes mesurées, précision micro implicite de 0,336) et **recopie le sentiment du premier
   thème sur le second** (0 divergence sur 52 cas).

**Enjeu métier.** Cultura priorise ses chantiers e-commerce à partir des volumes par couple
(thème × sentiment). Un second thème parasite crée du volume fictif ; un sentiment recopié
attribue un verbatim négatif à un thème dont le client est satisfait. Le préjudice n'est pas une
métrique dégradée, c'est une décision d'investissement prise sur des chiffres faux.

---

## 2. Ce qui a changé depuis le 30 juillet

| | Au cadrage initial | Aujourd'hui |
|---|---|---|
| Données | jeu synthétique, 403 textes uniques | **7 068 annotations réelles, 6 595 textes uniques**, jan.-sept. 2026 |
| Référentiel | 20 thèmes / 67 sous-thèmes, libellés polarisés | **11 / 59, libellés neutres**, charge sans exception |
| Sentiment par thème | demandé, sans donnée | **règle de priorité au négatif**, déjà présente dans les labels |
| Refonte de l'encodage | risquée, 4 j | **écartée** — aucun libellé de niveau 2 dupliqué |
| Campagne d'annotation | 4 j, ressource incertaine | **écartée** — Cultura a annoté |
| Ressources techniques | 1 data scientist | **renforcées** |
| Échéance | 30 août | **6 octobre** |

---

## 3. Ce que le nouveau modèle doit faire

| # | Objectif | Comment on le vérifie |
|---|---|---|
| **O-1** | Remonter le second thème quand il existe — et seulement alors | Précision du second thème, taux de faux second thème |
| **O-2** | Ne pas attribuer un sentiment négatif à un thème dont le client est satisfait | Règle de priorité au négatif, vérifiée sur cas mixtes |
| **O-3** | Fournir des volumes fiables pour prioriser | Erreur sur les volumes agrégés par (thème × sentiment) |
| **O-4** | Un taux de relecture pilotable | Confiance calibrée, cible 10-15 % |
| **O-5** | Un progrès démontrable | Baseline sans fuite, comparaison ancien/nouveau |
| **O-6** | Un modèle qui s'améliore | Corrections de revue exportables en jeu d'entraînement |

> O-4 et O-6 étaient sacrifiés dans toutes les versions précédentes du plan. **Les ressources
> supplémentaires les rendent atteignables pour la première fois.**

---

## 4. Périmètre

**Dans le périmètre** : chargeur pour les 5 schémas Cultura et normalisation des labels ·
protocole d'évaluation sans fuite et baseline honnête · recalibrage du seuil multi-label ·
réentraînement sur données réelles · redéfinition des signaux · règles d'arbitrage entre thèmes
voisins · calibration de la confiance · mesure et tenue du débit · mise à jour du prompt LLM et
du switch multi-moteur · recette comparative et mise en production · outillage de la boucle
d'amélioration.

**Hors périmètre, explicitement** : plus de 2 thèmes par verbatim · sortie « non classable »
côté CamemBERT · extraction d'entités · synthèse ou regroupement de verbatims · détection de
drift · refonte du référentiel par eXalt · réentraînement automatique · bascule du moteur
principal vers un LLM · sortie du mono-poste · refonte de l'interface.

---

## 5. Les décisions structurantes

Sur 35 décisions au registre, les neuf qui déterminent le résultat :

| # | Décision | Pourquoi |
|---|---|---|
| **D-3** | Moteur principal **CamemBERT réentraîné**, LLM local conservé en alternative | Le débit de 1-2 h exclut un LLM en production |
| **D-8** | Historique de 7 000 verbatims **écarté** | 403 textes uniques, 99,6 % de fuite : le conserver rendrait tout progrès indémontrable |
| **D-26** | Sentiment **unique par verbatim**, priorité au négatif sur les cas mixtes | Validé empiriquement : bi-thèmes négatifs à 72,6 % contre 25,5 % pour les mono-thèmes. La règle est **déjà dans les labels** |
| **D-28** | Baseline mesurée **par tranche de longueur** | Médiane réelle : 36 caractères, 6 mots. Une métrique globale mélangerait cas impossibles et cas traitables |
| **D-30** | Composition du verbatim **par source** | L'annotation porte sur le répondant, pas sur le champ. Évite 1 154 labels recopiés (14 % du corpus) |
| **D-31** | Normalisation des labels **dans le chargeur** | Cultura re-livrera : du code s'applique à toutes les livraisons, un nettoyage manuel serait à refaire |
| **D-32** | Seuil de **10 exemples** pour qu'un sous-thème soit modélisé | 16 sous-thèmes sur 59 ne sont ni apprenables ni évaluables ; les retirer coûte 0,8 % du corpus |
| **D-33** | `Général / Autre` conservé mais **exclu des cibles** | 19,7 % du corpus : un modèle qui prédit « Autre » partout afficherait 20 % de justesse sans valeur métier |
| **D-34** | Échéance au **6 octobre** | 9 jours ouvrés au 22 septembre pour un chemin critique **séquentiel** de 19 |

---

## 6. Critères d'acceptation

**Protocole d'abord.** Déduplication stricte, split **par texte unique**, test de non-fuite
**bloquant**, jeu de recette gelé, évaluation **par source** et **par tranche de longueur**,
correction du calcul du F1-micro (aujourd'hui évalué avant plafonnement, ce qui masquait la
sur-activation).

| Famille | Critère | Cible |
|---|---|---|
| **Justesse** | F1-macro niveau 1 | à fixer après la baseline — la valeur de 0,564 est invalide |
| | Couple (niveau 1 + niveau 2) correct | baseline + 10 points *(à valider)* |
| | Couple hors référentiel | **0, strict** |
| **Comportement** | Divergence de sentiment produite sur cas mixtes | **> 0** (départ : 0 sur 52) |
| | **Précision du second thème** | **≥ 0,70** *(à valider)* — critère central |
| | Taux de faux second thème | ≤ 15 % (départ : 43,3 % de bi-thèmes pour 4,4 % réels) |
| | Non-trivialité du sentiment | la règle note → sentiment doit être **moins bonne** que le modèle |
| **Exploitation** | Erreur sur volumes agrégés | ≤ 15 % par thème *(à valider)* |
| | Taux de relecture | **10 à 15 %**, seuil pilotable |
| | Débit | **11 000 verbatims ≤ 2 h**, mesuré |
| | Non-régression | recettes V1, V3, V4, V5 **et V6** au vert |

---

## 7. Planning

**19 jours ouvrés, du 10 septembre au 6 octobre. Deux fils techniques.**

| Semaine | Chemin critique | En parallèle |
|---|---|---|
| 10-11 sept | L1a chargeur | Poser la date à Cultura, relancer Q-6/9/11/12 |
| 14-18 sept | L1a fin · L2 baseline | L3 règles d'arbitrage · L4 signaux |
| 21-25 sept | L2 fin · L5' seuil · L6 début | L8 débit · L15 périmètre · L12 prompt LLM |
| 28 sept-2 oct | **L6 réentraînement** | Préparation recette métier |
| 5-6 oct | L9 activation | L9 recette métier · L7 calibration · L10 boucle |

> ⚠️ **Zéro marge.** Le chemin critique fait exactement 19 jours pour 19 disponibles.
> **Point de non-retour : si L6 n'est pas terminé le vendredi 2 octobre, la livraison glisse.**

---

## 8. Risques ouverts

| Risque | Probabilité | Mitigation |
|---|---|---|
| **Aucune marge sur le chemin critique** | forte | Jalon de contrôle au 25 septembre (fin de L5') |
| **Verbatims très courts** — médiane 6 mots | certaine | Mesure et négociation du périmètre classifiable (D-28, lot L15) |
| **Classe Neutre à 5,7 %** | certaine | Plafond structurel sur le F1-macro sentiment : à annoncer avant, pas après |
| **Concentration** — 4 sous-thèmes font 68 % du corpus | certaine | `Général / Autre` exclu des cibles ; relecture demandée à Cultura (Q-27) |
| **Débit de 1-2 h non tenu** | moyenne | Mesure précoce en L8, leviers identifiés (ONNX embeddings, quantization arm64) |
| **Labels incohérents sur frontières voisines** | moyenne | 18 couples invalides écartés et journalisés ; atelier L3 |
| **Recettes sur moteur stub** | certaine | Recette métier distincte, verdict nommé |

---

## 9. Ce qui reste à obtenir de Cultura

Aucune de ces questions ne bloque le démarrage. Les quatre premières transforment des hypothèses
en contraintes et doivent être posées cette semaine.

| # | Question | Impact |
|---|---|---|
| **Q-6** | Que déclenche chaque signal ? Churn (64) et Rupture (32) sont-ils évaluables ? | Nombre de modèles de signaux à entraîner |
| **Q-9** | Validation des cibles chiffrées | Critères d'acceptation contractuels |
| **Q-11** | Qui prononce l'accord de mise en service ? | Gouvernance de la livraison |
| **Q-12** | Règles d'arbitrage entre thèmes voisins | Plafond de performance du niveau 1 |
| **Q-27** | Relire les 1 393 verbatims `Général / Autre` | **La demande la plus rentable** : un cinquième des verbatims ne rentre dans aucun des 59 sous-thèmes |
| Q-7, Q-15, Q-17, Q-19, Q-22, Q-24, Q-26, Q-28 | matériel, dashboards, échelles, RGPD, libellés | documentées avec hypothèse par défaut |

---

## 10. Livrables du cadrage

| Document | Objet |
|---|---|
| `CADRAGE_NOUVEAU_MODELE.md` | Contrat complet : 35 décisions, exigences, critères, risques |
| `AUDIT_DONNEES_NOUVEAU_MODELE.md` | État mesuré des données et du référentiel |
| `SPEC_CHARGEUR.md` | Spécification exécutable du premier lot |
| `PLAN_LOTS_NOUVEAU_MODELE.md` | Découpage, charges, chemin critique, points de non-retour |
| `PROMPT_AGENT_IMPLEMENTATION.md` | Instruction de l'agent chargé de l'implémentation |
| `SPEC_JEU_FACTICE.md` + `scripts/generate_fake_dataset.py` | Jeu de test technique et son générateur |
| `SOLLICITATION_CULTURA.md` | Questions groupées au client |

---

*Projet interne Cultura / eXalt — usage confidentiel.*
