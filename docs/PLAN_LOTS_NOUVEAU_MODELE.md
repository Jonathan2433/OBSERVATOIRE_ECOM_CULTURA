# Plan de lots — Nouveau modèle ML Cultura Verbatim Classifier

> **Document jumeau** de `docs/CADRAGE_NOUVEAU_MODELE.md` (v1.1). Les références `D-x`,
> `Q-x`, `R-x`, `EF-x`, `ENF-x`, `O-x`, `H-x` renvoient à ce document.
>
> **Statut.** v1.1 — 30 juillet 2026. Révisé après relecture critique : correction du
> diagnostic du grief n°1, de l'arithmétique de capacité et du séquencement.
> **Échéance.** 30 août 2026 (dimanche). **Dernier jour ouvré : vendredi 28 août.**
> **Capacité.** 22 jours ouvrés : 2 en semaine 31 (30-31 juillet), puis 5 par semaine en
> semaines 32, 33, 34 et 35. Le 15 août tombe un samedi — aucun jour ouvré perdu.
> **Équipe** (D-14) : 1 data scientist · 1 PO (Jonathan) · 1 agent · 2 personnes métier.
> **Aucune ressource de développement n'est identifiée** — voir §5 et Q-14.

---

## 0 bis. Mise à jour du 9 septembre — le plan change de phase

**Les données réelles et le référentiel Cultura sont arrivés.** Détail mesuré dans
`docs/AUDIT_DONNEES_NOUVEAU_MODELE.md`. **L'échéance du 30 août est dépassée** : le scénario de
repli accepté par Cultura (E4) s'applique de fait, et le projet entre dans sa phase de
réentraînement sur données réelles.

### Ce qui disparaît

| Lot | Sort | Motif |
|---|---|---|
| **L11** — clé composite | **écarté** | Aucun libellé de niveau 2 dupliqué dans le référentiel livré. `taxonomy.py` chargera. **R-3 ne se réalise pas : 4 j récupérés.** |
| **L13** — campagne d'annotation | **écarté** | Cultura a livré 7 068 annotations. **R-1 est levé.** |
| **L1b** — audit des données réelles | **fait** | `docs/AUDIT_DONNEES_NOUVEAU_MODELE.md`. |
| **L5** — volet sentiment par thème | **écarté** | D-26 : le sentiment reste unique par verbatim, et la règle de priorité au négatif est **déjà dans les labels** (bi-thèmes négatifs à 72,6 % contre 25,5 % pour les mono-thèmes). Aucun mécanisme spécifique, aucune annotation. **3 j récupérés.** L5 se réduit au recalibrage du seuil multi-label. |

**Bilan : 7 jours-homme récupérés sur le fil du data scientist**, qui passe de 20,5 j à 13,5 j
pour les lots fermes.

### Ce qui apparaît

| Lot | Titre | Charge | Motif |
|---|---|---|---|
| ~~**L14**~~ | ~~Nettoyer et normaliser les labels~~ | ~~2 j~~ | **Supprimé le 09/09 (D-31).** La normalisation est portée par le chargeur, donc par **L1a** : Cultura re-livrera les fichiers, un nettoyage manuel serait à refaire à chaque fois, du code s'applique à toutes les livraisons. L1a passe de 3 à 4 j. **Net : 1 j récupéré.** |
| **L15** | **Arbitrer le périmètre du classifiable** | 1 j | D-28 : baseline par tranche de longueur, puis négociation avec Cultura. Médiane réelle : 36 caractères, 6 mots. Inclut l'arbitrage des 7 sous-thèmes sans aucun exemple — que Cultura s'est engagé à alimenter en verbatims. |

### Ce qui change dans les lots existants

- **L1a** (chargeurs) : **spécifié — `docs/SPEC_CHARGEUR.md`, prêt à implémenter.** Charge portée
  à **4 j** (3 j de chargeur + 1 j de normalisation absorbée depuis L14). À bâtir sur les
  **fichiers réels**, pas sur les maquettes du 12 août — les noms de colonnes diffèrent
  (`Satisfaction` et non `Niveau de satisfaction`, `Recommandation` et non `score RECO`).
  Contient la composition par source (D-30), la normalisation des libellés instables — dont un
  **caractère de contrôle `\x0b` invisible** en fin de libellé, cause réelle de la divergence
  entre exports Mopinion mobile — et l'échec explicite sur colonne manquante. **Aucune
  dépendance : réalisable immédiatement, sans attendre la re-livraison Cultura.**
- **L2** (baseline) : ajouter la mesure **par tranche de longueur** (D-28) et **par source**
  (R-16 : Mopinion desktop n'a aucun bi-thème, MDTC post-réception pèse 3 388 des 7 068
  annotations et est massivement positif).
- **L4** (signaux) : les données fournissent **un champ à valeur unique**, pas trois booléens.
  Churn (64) et Rupture (32) sont trop rares pour être évaluables — argument mesuré pour la
  redéfinition.
- **L6** (réentraînement) : la classe **Neutre ne pèse que 5,7 %** (371 exemples). Le F1-macro
  sentiment sera tiré vers le bas indépendamment de la qualité du modèle : à porter aux
  critères d'acceptation avant, non après.
- **L9** (recette) : conserver le contrôle que les colonnes écartées par D-18 n'atteignent pas
  la base.

### Nouveau chemin critique

```
L1a (4 j) ──► L2 (4 j) ──► L5' (2 j) ──► L6 (5 j) ──► L9 (4 j)
 chargeurs    protocole     seuil        réentraî-    recette
 + normali-   + baseline    multi-label  nement       + prod
 sation       par tranche
```

**19 jours ouvrés** de chemin critique. L15 (1 j), L3 (2 j) et L4 (2 j) sont parallélisables et
hors fil du data scientist.

### Séquencement arrêté — livraison le mardi 6 octobre 2026 (D-34, D-35)

**19 jours ouvrés du jeudi 10 septembre au mardi 6 octobre.** Deux fils techniques, rendus
possibles par les ressources supplémentaires (D-35).

| Semaine | Jours | Fil technique 1 — chemin critique | Fil technique 2 + métier |
|---|---|---|---|
| **10-11 sept** | 2 | **L1a** chargeur (démarrage) | Poser la date à Cultura · relancer Q-6, Q-9, Q-11, Q-12 |
| **14-18 sept** | 5 | **L1a** (fin, j4) · **L2** protocole + baseline (j1-3) | **L3** règles d'arbitrage · **L4** définition des signaux |
| **21-25 sept** | 5 | **L2** (fin, j4) · **L5'** seuil multi-label (2 j) · **L6** (démarrage) | **L8** débit · **L15** périmètre du classifiable · **L12** prompt LLM |
| **28 sept-2 oct** | 5 | **L6** réentraînement et itérations | Préparation du jeu de recette métier |
| **5-6 oct** | 2 | **L9** activation et non-régression | **L9** recette métier · **L7** calibration · **L10** boucle |

> ⚠️ **Zéro marge.** Le chemin critique fait exactement 19 jours pour 19 disponibles. Point de
> non-retour : **si L6 n'est pas terminé le vendredi 2 octobre, la livraison du 6 glisse.**
> À surveiller dès le jalon du 25 septembre (fin de L5' attendue).

### Capacité — historique du point dur

| Périmètre | Fil data scientist | Capacité 19 j |
|---|---|---|
| Lots fermes **hors L8** (L1a 4 + L2 4 + L5' 2 + L6 5 + L9 2 + L12 0,5) | **17,5 j** | 1,5 j de marge |
| + **L8** débit (3 j) si non parallélisé | **20,5 j** | **−1,5 j** |
| + L7 calibration (3 j) | 23,5 j | −4,5 j |
| + L10 boucle (1 j DS) | 24,5 j | −5,5 j |

> **Correction d'une erreur de ce document (v1.2).** Une version antérieure annonçait 12,5 j de
> fil DS et concluait que L7 et L10 redevenaient logeables. **C'est faux.** Les gains réels
> portent sur le **chemin critique** (21 j → 19 j) et sur l'évitement des lots conditionnels
> L11 et L13 (8 j qui n'ont pas à être activés), non sur le fil DS des lots fermes : L5 a
> perdu 3 j, mais L1a en a gagné 3 (le chargeur est un développement de 4 j là où l'audit L1 ne
> coûtait qu'1 j de DS).

**Conclusion honnête** : le périmètre ferme tient **si et seulement si L8 est parallélisé**,
ce qui suppose Q-14 (seconde ressource technique) — **toujours ouverte**. Et **L7 et L10 ne sont
pas logeables** sur cette échéance : les objectifs **O-4** (taux de revue pilotable) et **O-6**
(boucle d'amélioration) restent sacrifiés, sauf à décaler la date d'environ une semaine
(21 jours ouvrés permettraient de loger L7).

**Une date de livraison reste à fixer avec Cultura** (Q-10 devenue caduque). Sur la base de
19 jours ouvrés à compter du 10 septembre, la cible se situe au **mardi 6 octobre 2026** —
périmètre ferme uniquement. Loger la calibration porterait la cible à la mi-octobre.

**Le lot L1a est spécifié et sans dépendance : il peut démarrer immédiatement**, pendant que
Cultura complète les verbatims des 7 sous-thèmes manquants. Cette re-livraison n'invalidera
rien, puisque la normalisation est en code (D-31).

**Le lot L1a est spécifié et sans dépendance : il peut démarrer immédiatement**, pendant que
Cultura complète les verbatims des 7 sous-thèmes manquants. Cette re-livraison n'invalidera
rien, puisque la normalisation est en code (D-31).

---

## 0. Mise à jour du 12 août — ce qui a changé

**Quatre maquettes de structure ont été déposées** dans `data/raw/NEW_FILES/` : MDTC post-achat
web (9 colonnes), MDTC post-réception web (7), Mopinion desktop (25), Mopinion mobile V2 (25).
Ce sont des **fichiers de structure**, pas des exports : 11 à 16 lignes fictives, marqueurs
`(etc)`. Aucune mesure statistique, aucun entraînement, aucune baseline n'est possible dessus
(R-17).

**L1 se scinde en deux volets :**

| Volet | Contenu | Statut |
|---|---|---|
| **L1a — Spécifier le contrat de données** | 4 chargeurs (H-1 falsifiée : aucun mapping de colonnes ne survit), règle de composition du verbatim (D-17), colonnes ingérées (D-18), conversion des échelles de satisfaction (D-20), extraction des sujets cochés comme étiquettes (D-19), validation de schéma qui échoue explicitement sur colonne manquante (R-18) | **Réalisable immédiatement** — 3 j |
| **L1b — Auditer les données réelles** | Tout le profiling statistique du lot L1 initial, plus la **mesure du taux de désaccord entre sujet coché et texte écrit** (garde-fou de D-19, R-15) et l'évaluation séparée par source (R-16) | **Bloqué sur les exports réels** (Q-1 bis) — 2 j |

**Conséquence sur le calendrier.** Le chemin critique ne redémarre qu'à réception des exports
réels. Les 3 jours de L1a peuvent être consommés dès maintenant sans attendre, ce qui limite la
perte — mais **L2 reste bloqué**, et avec lui tout le reste. Au 12 août, il reste **13 jours
ouvrés** jusqu'au vendredi 28 août, pour un chemin critique de 21 jours.

**Le scénario de repli du §5.6 n'est plus une option de précaution : c'est le scénario
nominal.** Il doit être présenté à Cultura maintenant (sollicitation E4), et non arbitré fin
août.

---

## 1. Avertissement liminaire

Ce plan **ne démontre pas** que la mise en production du 30 août (D-13) est atteignable. Il
démontre l'inverse, et le chiffre :

- Le **chemin critique nominal est de 21 jours ouvrés** pour 22 disponibles.
- Mais il ne peut commencer qu'au dépôt des fichiers (Q-1, Q-2). **Si les fichiers arrivent le
  lundi 3 août, il ne reste que 20 jours ouvrés : le chemin critique est déjà plus long que le
  temps disponible.**
- Le **fil du data scientist est chiffré à ≈ 23,5 jours-homme pour 22 jours ouvrés**, avant
  toute dérive — et c'est ce fil qui porte le chemin critique.
- L'équipe décrite en D-14 ne comporte aucune seconde ressource technique, alors que le plan en
  a besoin pour paralléliser L8 (Q-14).

**Trois issues, à arbitrer avant le 10 août, pas fin août :**

| Issue | Effet |
|---|---|
| **A** — Lever Q-14 : une seconde ressource technique en août | Rend le périmètre complet plausible. L8, L12 et une partie de L9 sortent du fil DS. |
| **B** — Lever Q-7 : une machine d'entraînement plus rapide | Réduit l'incertitude de L6 (± 2 j), qui est le premier poste de dérive. Ne résout pas seul le dépassement. |
| **C** — Reporter L7 puis L10 | Ramène le fil DS à ≈ 20,5 j puis 20,5 j. Coût : les objectifs **O-4** et **O-6** tombent, ainsi que EF-6, EF-7 et EF-10. À annoncer à Cultura, pas à découvrir. |

À défaut, le scénario de repli du §4.6 s'applique : modèle mesuré et présentable au 30 août,
mise en production en septembre (Q-16).

---

## 2. Règles de découpage appliquées

1. **Un lot livre un artefact vérifiable.** Aucun lot « étude » sans fichier, métrique ou
   document produit.
2. **Le lot 1 réduit l'incertitude la plus coûteuse** : la nature réelle des nouvelles données.
   Tout le reste en dépend, et un mauvais lot 1 rend les lots suivants ininterprétables.
3. **Ce qui relève du référentiel est séparé de ce qui relève du modèle.** L'absorption de
   `Click & Collect` par `Suivi de commande` (45 cas sur 62) ne se règle pas par du
   réentraînement.
4. **Une baseline mesurée précède toute amélioration.** Sans référence, aucun gain n'est
   démontrable (R-6).
5. **La calibration de la confiance est un lot dédié** : elle pilote le taux de revue, donc la
   charge du métier, et elle est indépendante de la qualité de classification.
6. **Un lot de recette comparative** réutilise le dispositif V5 existant (comparaison
   multi-moteur avec juge aveuglé, admin only, tracé à l'audit).
7. **Les lots sont dimensionnés entre 2 et 5 jours.** Les lots à 2 jours (L3, L4, L10, L12) sont
   des lots courts assumés : L3 et L4 ne consomment pas de capacité technique ; L10 et L12 sont
   des lots techniques courts, dont la finesse est volontaire pour qu'ils restent coupables sans
   casser le reste.

---

## 3. Vue d'ensemble

| Lot | Titre | Charge | Dont fil DS | Porteur principal | Statut |
|---|---|---|---|---|---|
| **L1** | **Auditer les nouvelles données et le nouveau référentiel** | 3 j (± 1) | 1 j | Agent, avec le DS | **Jalon de décision** |
| **L2** | Reconstruire le protocole d'évaluation et mesurer la baseline honnête | 4 j (± 1) | 4 j | DS | Ferme |
| **L3** | Écrire les règles d'arbitrage et le guide d'annotation | 2 j | 0 | PO + métier + Cultura | Ferme, parallèle |
| **L4** | Définir opérationnellement les signaux métier | 2 j | 0 | PO + métier + Cultura | Ferme, parallèle |
| **L5** | Corriger le sentiment par thème et recalibrer le seuil multi-label | 5 j (± 2) | 5 j | DS | Ferme |
| **L6** | Réentraîner et itérer | 5 j (± 2) | 5 j | DS | Ferme |
| **L7** | Calibrer la confiance et régler le taux de revue | 3 j (± 1) | 3 j | DS | **Conditionnel — 1ᵉʳ à couper** |
| **L8** | Mesurer et tenir le débit de 1-2 h | 3 j (± 1) | 3 j *(ou 0 si Q-14 levée)* | DS ou 2ᵈᵉ ressource | Ferme, parallélisable |
| **L9** | Recette comparative et mise en production | 4 j (± 1) | 2 j | Métier + DS | Ferme |
| **L10** | Outiller la boucle corrections → jeu d'entraînement | 2 j | 1 j | Agent + DS | **Conditionnel — 2ᵈ à couper** |
| **L11** | Refondre l'encodage vers une clé composite (niv1, niv2) | 4 j (± 2) | 4 j | DS | **Conditionnel à Q-5** |
| **L12** | Actualiser le prompt LLM et vérifier le switch multi-moteur | 2 j | 0,5 j | Agent, revue DS | Ferme |
| **L13** | Conduire une campagne d'annotation ciblée | 4 j (± 3) | 0,5 j | Métier | **Conditionnel à R-1 et Q-8** |

### 3.1 Convention de charges

| Périmètre | Charge totale | Dont fil DS |
|---|---|---|
| **Lots fermes** (L1, L2, L3, L4, L5, L6, L8, L9, L12) | **30 j** | **20,5 j** |
| + L7 (calibration) | 33 j | 23,5 j |
| + L10 (boucle d'amélioration) | 35 j | 24,5 j |
| + L11 (clé composite, si Q-5 négative) | 39 j | 28,5 j |
| + L13 (campagne d'annotation, si R-1 se réalise) | 43 j | 29 j |

**Le périmètre complet retenu en D-14 (lots fermes + L7 + L10) représente 24,5 jours-homme sur
le seul fil du data scientist, pour 22 jours ouvrés disponibles.** C'est le chiffre qui fonde
R-2 et l'avertissement du §1. Les lots fermes seuls tiennent à 20,5 j, soit 1,5 j de marge —
consommée par la moindre dérive.

---

## 4. Description des lots

### L1 — Auditer les nouvelles données et le nouveau référentiel

| Champ | Contenu |
|---|---|
| **Objectif** | Savoir, avant d'engager quoi que ce soit, ce que contiennent réellement les fichiers, et si la promesse multi-thème est mesurable au 30 août. |
| **Contenu** | Profiling des nouveaux fichiers : schéma, volume, période, sources, taux de vide par colonne, longueurs de texte, doublons exacts et quasi-doublons, distribution des thèmes et sous-thèmes, **distribution du nombre de thèmes par verbatim**, **proportion de verbatims à sentiments divergents entre thèmes**, PII réellement présentes, verbatims vides ou trop courts. Mesure du **taux d'accord entre la note de satisfaction et le sentiment annoté** (test de R-5). **Contrôle de cohérence des labels de signaux sur textes identiques** — précédent mesuré : 213 des 403 textes uniques du jeu actuel portent des labels contradictoires (R-10). **Contrôle du taux et de la nature des masquages d'anonymisation**, et vérification explicite de la présence de spaCy (R-14). Contrôle de l'**unicité globale des libellés de niveau 2** du nouveau référentiel (Q-5, R-3). Comparaison du nouveau référentiel à l'ancien : thèmes ajoutés, supprimés, renommés ; libellés neutres ou polarisés (D-6). Matrice de confusion du modèle **actuel** appliqué aux **nouvelles** données, comme pièce d'instruction pour Cultura. |
| **Livrable vérifiable** | `docs/AUDIT_DONNEES_NOUVEAU_MODELE.md` : tableau de profiling chiffré, verdict d'unicité niv.2 (oui/non), proportion mesurée de bi-thèmes, proportion mesurée de sentiments divergents, taux d'accord note/sentiment, taux de contradiction des labels de signaux, taux de masquage PII, matrice de confusion sur nouvelles données, et **recommandation Go / No-Go sur le périmètre du 30 août**. Plus les scripts de profiling, dans `scripts/` ou `notebooks/`. |
| **Definition of Done** | ☐ Nouveaux fichiers et nouveau référentiel présents dans `data/raw/` (Q-1, Q-2) · ☐ profiling exécuté et reproductible · ☐ **verdict Q-5 prononcé, L11 activé ou écarté** · ☐ proportion de bi-thèmes chiffrée · ☐ proportion de sentiments divergents chiffrée (Q-3) · ☐ taux d'accord note/sentiment chiffré (R-5) · ☐ cohérence des labels de signaux mesurée (R-10) · ☐ taux de masquage PII mesuré et présence de spaCy vérifiée (R-14) · ☐ matrice de confusion produite · ☐ **D-5 prononcée** (frontières poreuses : traitées ou explicitement laissées en l'état, avec le plafond documenté) · ☐ **L13 activé ou écarté** (R-1, R-13) · ☐ recommandation de périmètre écrite et transmise au PO · ☐ R-1, R-3, R-5, R-10, R-14 réévalués avec leur probabilité mise à jour |
| **Dépendances** | Q-1 et Q-2 (dépôt des fichiers). **Bloque tous les autres lots.** |
| **Charge** | **3 j** (dont 1 j de fil DS), incertitude ± 1 j selon le nombre et la propreté des fichiers. Le +1 j couvre le cas H-1 (schéma inconnu → nouveau chargeur). |
| **Risques du lot** | Les fichiers arrivent tard : chaque jour de retard sur Q-1/Q-2 est un jour perdu sans rattrapage. Les fichiers ne sont pas annotés en multi-thème → activation de L13, sous réserve de Q-8. |

> **Ce lot est un jalon de décision, pas seulement un audit.** À son issue, le PO tranche le
> périmètre du 30 août, prononce D-5, et active ou écarte L11 et L13. C'est le seul moment du
> plan où l'on peut encore arbitrer sans coût.

---

### L2 — Reconstruire le protocole d'évaluation et mesurer la baseline honnête

| Champ | Contenu |
|---|---|
| **Objectif** | Disposer d'un point de départ mesuré et d'un protocole qui ne peut plus produire de fuite ni masquer la sur-activation. |
| **Contenu** | Déduplication stricte des textes avant tout split. Passage à un **split par texte unique** et non par ligne. Ajout d'un **test bloquant** dans la chaîne de préparation : l'intersection des ensembles de textes entre train, validation et test doit être vide. **Correction du calcul du F1-micro** dans `src/evaluation/evaluate.py`, qui évalue aujourd'hui `niv1_probs >= 0.35` **avant** application de `max_themes` et masquait donc la sur-activation (§1.4 e du cadrage). Construction du **jeu de recette gelé** conforme à §7.1 du cadrage. Évaluation du modèle **actuel** sur ce protocole, y compris **par source** (MDTC / Mopinion). Ajout des mesures manquantes : **distribution du nombre de thèmes en sortie** (EF-4), précision et rappel du second thème, taux de faux second thème, nombre de cas à sentiments divergents produits, erreur sur les volumes agrégés par (thème × sentiment). **Première mesure de débit du modèle actuel**, pour donner à L8 son point de départ. |
| **Livrable vérifiable** | `data/processed/eval_report_baseline.json` · le jeu de recette gelé, versionné et documenté · le test de non-fuite intégré et passant · le calcul du F1-micro corrigé · une note d'une page comparant les métriques publiées aux métriques honnêtes, avec l'écart chiffré. |
| **Definition of Done** | ☐ Test de non-fuite implémenté et bloquant · ☐ intersection des textes entre splits vérifiée vide · ☐ F1-micro recalculé après plafonnement, écart avec la valeur publiée de 0,479 documenté · ☐ jeu de recette gelé constitué et sa composition documentée · ☐ baseline du modèle actuel mesurée sur nouvelles données · ☐ évaluation par source produite · ☐ **distribution du nombre de thèmes en sortie mesurée** (EF-4, point de départ : 43,3 % de bi-thèmes) · ☐ précision et rappel du second thème mesurés · ☐ nombre de sentiments divergents produits mesuré (point de départ : 0 sur 52) · ☐ erreur sur volumes agrégés mesurée · ☐ débit du modèle actuel chronométré · ☐ écart avec les métriques publiées chiffré et expliqué |
| **Dépendances** | L1. Bloqué par L11 si activé. |
| **Charge** | **4 j** (fil DS intégral), incertitude ± 1 j. |
| **Risques du lot** | Le volume de bi-thèmes est trop faible pour constituer un jeu de recette statistiquement exploitable → le rappel du second thème ne sera pas mesurable avec confiance, et la famille B des critères devient partiellement indicative (R-1). À signaler immédiatement au PO si c'est le cas. |

> **Non négociable.** Sans ce lot, aucun gain n'est démontrable et toute cible est arbitraire
> (R-6). Il porte l'objectif O-5.

---

### L3 — Écrire les règles d'arbitrage et le guide d'annotation

| Champ | Contenu |
|---|---|
| **Objectif** | Supprimer l'ambiguïté d'annotation, pour que le modèle apprenne du signal et non du bruit. |
| **Contenu** | Atelier avec Cultura, préparé avec la matrice de confusion de L1 et une liste de cas limites réels extraits des nouveaux fichiers. Rédaction de règles de décision explicites sur les paires connues comme poreuses : *Suivi de commande* / *Click & Collect*, *Disponibilité & Stock* / *Annulation commande*, *Retour / Remboursement* / *Tunnel de vente*, *Carte cadeau physique* / *Compte client*. Rédaction du guide d'annotation pour le sentiment **par thème** (D-1) et pour le triplet *(verbatim, thème) → sentiment* (H-4). **Règles d'étiquetage des signaux**, au vu du taux de contradiction mesuré en L1. Portage à Cultura de la recommandation de libellés neutres (D-6, Q-4). |
| **Livrable vérifiable** | `docs/REGLES_ARBITRAGE_ANNOTATION.md` : une règle par paire ambiguë, chacune illustrée d'au moins deux exemples tirés des données réelles ; protocole d'annotation du sentiment par thème ; règles d'étiquetage des signaux. |
| **Definition of Done** | ☐ Atelier tenu avec un interlocuteur Cultura (Q-13) · ☐ au moins les 4 paires poreuses traitées par une règle écrite · ☐ chaque règle illustrée par des exemples réels · ☐ protocole d'annotation du sentiment par thème rédigé · ☐ règles d'étiquetage des signaux rédigées · ☐ Q-4 posée et réponse consignée · ☐ Q-12 close |
| **Dépendances** | L1 (pour arriver à l'atelier avec des mesures). Parallélisable avec L2. **Prérequis de L13 si activé.** |
| **Charge** | **2 j** dont environ une demi-journée d'atelier. **Ne consomme aucune capacité du data scientist.** |
| **Risques du lot** | Indisponibilité Cultura en août (R-8) → l'atelier glisse et les labels restent ambigus. Cultura refuse D-6 → les retours positifs restent mal traités, à porter au registre. |

---

### L4 — Définir opérationnellement les signaux métier

| Champ | Contenu |
|---|---|
| **Objectif** | Ne pas réentraîner deux modèles qui produisent la même information, ni un modèle sur du bruit d'étiquetage. |
| **Contenu** | Faire expliciter par le métier, pour chaque signal, l'action déclenchée, son destinataire et son délai (Q-6). Confronter aux mesures : `churn` et `insatisfaction` partagent 1 794 positifs avec 2 exceptions sur 7 000 et des métriques identiques à deux décimales ; `rupture` compte 0,41 % de positifs et 1 seul cas dans le test ; **213 des 403 textes uniques portent des labels de signaux contradictoires**. Décider du nombre de signaux à produire et de l'arbitrage précision / rappel de chacun — aujourd'hui tous « ratissent large » (rappel 0,99 pour environ 26 % de faux positifs). Chiffrer le volume minimal de cas positifs annotés nécessaire pour qu'un signal soit évaluable. |
| **Livrable vérifiable** | `docs/DEFINITION_SIGNAUX.md` : un signal par section, avec sa définition opérationnelle, l'action déclenchée, l'arbitrage précision/rappel retenu, le volume minimal de positifs nécessaire, et la décision de le conserver, fusionner ou supprimer. Plus le chiffrage de l'impact sur `OUTPUT_COLUMNS`, la base, les exports et les dashboards. |
| **Definition of Done** | ☐ Une action métier distincte identifiée par signal conservé (EF-8) · ☐ décision prise sur la fusion de `churn` et `insatisfaction` · ☐ décision prise sur `rupture` compte tenu de sa non-évaluabilité · ☐ arbitrage précision/rappel fixé par signal · ☐ impact sur `OUTPUT_COLUMNS` et sur les dashboards chiffré (alimente Q-15) · ☐ D-10 close, Q-6 close |
| **Dépendances** | L1 (taux de positifs et taux de contradiction mesurés). Parallélisable avec L2 et L5. |
| **Charge** | **2 j**. **Ne consomme aucune capacité du data scientist.** |
| **Risques du lot** | Si un signal est supprimé, propagation sur la base, les exports, le front et les dashboards : à chiffrer dans le lot, pas après. |

---

### L5 — Corriger le sentiment par thème et recalibrer le seuil multi-label

| Champ | Contenu |
|---|---|
| **Objectif** | Corriger les deux défauts réels du grief n°1 : le sentiment recopié et la sur-activation du second thème. Porte O-1 et O-2. |
| **Contenu** | **(a) Sentiment par thème.** Valider H-3 : sentiment conditionné au thème par préfixe textuel `[THEME <libellé>] <verbatim>`, sur le modèle du préfixe de satisfaction déjà en place dans `src/utils/features.py`. Vérifier la compatibilité ONNX et l'absence de tête custom. Adapter la chaîne de préparation pour produire des exemples *(verbatim, thème) → sentiment*. Modifier `build_output` (`src/inference/predictor.py`, l. 77-93) pour appeler le sentiment **une fois par thème retenu** et cesser la recopie — point de départ mesuré : 0 divergence sur 52 sorties bi-thèmes. **(b) Seuil multi-label.** Recalibrer le seuil d'activation du niveau 1, aujourd'hui à 0,35 et démontré sur-déclenchant : précision micro implicite de 0,336, soit ≈ 2,5 thèmes activés par verbatim, et 43,3 % de sorties bi-thèmes pour 0,4 % d'annotations bi-thèmes. Balayage du seuil sur la validation, avec l'arbitrage précision du second thème contre taux de faux second thème. |
| **Livrable vérifiable** | Code de préparation et d'inférence modifié · tests unitaires de `build_output` couvrant le cas à deux sentiments divergents · courbe seuil multi-label / (précision du second thème, taux de faux second thème, rappel) · note de validation de H-3 avec verdict ONNX. |
| **Definition of Done** | ☐ H-3 validée ou infirmée, verdict écrit · ☐ export ONNX vérifié fonctionnel sur la nouvelle entrée · ☐ `build_output` produit deux sentiments **distincts** sur un cas de test · ☐ **test unitaire du cas « paiement KO / recherche facile » passant, avec sentiments opposés** · ☐ seuil multi-label choisi sur la validation, avec la courbe à l'appui · ☐ taux de faux second thème mesuré au seuil retenu et comparé au point de départ · ☐ aucun couple hors référentiel produit par le modèle (EF-5) |
| **Dépendances** | L1, L2. Bénéficie de L3 mais n'en dépend pas techniquement. Bloque L12 (contrat de sortie stabilisé). |
| **Charge** | **5 j** (fil DS intégral), incertitude ± 2 j. Le ± 2 est réel : si H-3 tombe, une tête custom devient nécessaire, au prix de l'export ONNX et donc du débit (ENF-1, R-4). |
| **Risques du lot** | H-3 infirmée → arbitrage entre le sentiment par thème et le débit, à remonter immédiatement au PO. Nombre insuffisant d'exemples *(verbatim, thème) → sentiment* pour entraîner (R-1). |

---

### L6 — Réentraîner et itérer

| Champ | Contenu |
|---|---|
| **Objectif** | Produire le modèle candidat et mesurer ce qu'il vaut réellement. |
| **Contenu** | Réentraînement complet sur les nouvelles données : niveau 1 multi-label, niveau 2 multi-classes, sentiment conditionné au thème, signaux selon L4. Test de `lowercase: false` — CamemBERT est un modèle sensible à la casse et le réglage actuel détruit les majuscules d'intensité émotionnelle ; gain potentiel quasi gratuit (L10 de l'état des lieux). Évaluation sur le protocole de L2. Une à deux itérations d'ajustement. Export ONNX int8 et carte d'entraînement par version. |
| **Livrable vérifiable** | Les modèles versionnés sous `data/models/<tâche>/<horodatage>/` avec `training_card.json` · `data/processed/eval_report.json` régénéré sur le protocole sans fuite · `training_logs.json` · comparaison `lowercase` vrai/faux chiffrée. |
| **Definition of Done** | ☐ Modèles entraînés et versionnés · ☐ pointeur `CURRENT` à jour · ☐ export ONNX int8 réussi · ☐ évaluation produite sur le jeu de recette gelé · ☐ **précision du second thème mesurée et comparée à la baseline de L2** · ☐ **nombre de sentiments divergents produits > 0** sur les cas annotés divergents · ☐ justesse du sentiment par thème mesurée · ☐ distribution du nombre de thèmes en sortie mesurée (EF-4) · ☐ test de non-trivialité du sentiment exécuté, **avec statut conditionnel à R-5 explicitement consigné** (EF-3) · ☐ erreur sur volumes agrégés mesurée (EF-11, O-3) · ☐ arbitrage `lowercase` tranché sur mesure |
| **Dépendances** | L5, et L4 pour les signaux. |
| **Charge** | **5 j** (fil DS intégral), incertitude ± 2 j. Sur CPU, une passe complète des trois modèles se compte en heures ; le plan ne tolère qu'un nombre très limité d'itérations. **Q-7 est le levier direct sur cette incertitude.** |
| **Risques du lot** | Une itération ratée coûte 2 à 3 jours et fait sauter l'échéance (R-2). Volume d'entraînement insuffisant après l'écartement des 7 000 (D-8). Classes rares sous le seuil d'évaluabilité. |

---

### L7 — Calibrer la confiance et régler le taux de revue **[CONDITIONNEL]**

| Champ | Contenu |
|---|---|
| **Objectif** | Rendre le curseur de revue humaine utilisable, et atteindre les 10 à 15 % visés (D-9). Porte **O-4**, EF-6 et EF-7. |
| **Contenu** | Remplacer la moyenne non pondérée de trois échelles incomparables (sigmoïde multi-label, softmax masqué sur 67 classes, softmax sur 3 classes ; `predictor.py` l. 110) par un score calibré. Appliquer une calibration probabiliste sur la validation — température, Platt ou isotonique, selon ce que les données permettent. Recomposer `confidence_globale` avec des composantes comparables. Produire la table taux de revue par seuil sur au moins 6 seuils, et vérifier la monotonie et l'absence de saut supérieur à 20 points. Choisir le seuil opérationnel avec le métier. |
| **Livrable vérifiable** | Courbe de fiabilité et ECE avant/après · table taux de revue / seuil sur au moins 6 points · seuil retenu inscrit dans `config/config.yaml` avec son rationnel · note d'une demi-page pour le métier expliquant ce que signifie désormais une confiance de 0,80. |
| **Definition of Done** | ☐ Méthode de calibration choisie et justifiée · ☐ ECE mesurée avant et après, cible ≤ 0,10 · ☐ table taux de revue produite, monotone, sans saut > 20 points (EF-7) · ☐ taux au seuil retenu entre 10 % et 15 % (D-9) · ☐ seuil et rationnel inscrits en configuration · ☐ note métier rédigée · ☐ impact sur les seuils en base et les dashboards chiffré (Q-15) |
| **Dépendances** | L6. |
| **Charge** | **3 j** (fil DS intégral), incertitude ± 1 j. |
| **Statut** | **Conditionnel — premier lot à couper** si le fil DS déborde (R-2). Rationnel : la calibration se pose **par-dessus** un modèle déjà entraîné ; la reporter ne fait refaire aucun travail, contrairement à L5. **Conséquence à annoncer si coupé : O-4, EF-6, EF-7 et les critères de famille C liés au taux de revue tombent.** |
| **Risques du lot** | Jeu de validation trop petit après déduplication pour calibrer de façon stable. |

---

### L8 — Mesurer et tenir le débit de 1-2 h

| Champ | Contenu |
|---|---|
| **Objectif** | Vérifier ENF-1, jamais mesuré à ce jour, et l'atteindre. |
| **Contenu** | Chronométrer de bout en bout un lot réel de 11 000 verbatims sur le poste cible. Instrumenter par étape : anonymisation, nettoyage, niveau 1, niveau 2, sentiment (désormais **1 à 2 fois par verbatim selon le nombre de thèmes**), embeddings des signaux. Traiter les goulots connus : `EmbeddingExtractor` non exporté en ONNX et donc forcé en PyTorch (`architecture.py` l. 236-252) ; quantization ciblée `AutoQuantizationConfig.avx2`, explicitement x86 dans le commentaire du code (l. 300), alors que le poste est arm64. Réduction du nombre de signaux si L4 le permet. |
| **Livrable vérifiable** | `docs/MESURE_DEBIT.md` : temps total mesuré, décomposition par étape, comparaison avant/après optimisation, verdict sur la tenue de la cible 1-2 h · la ou les optimisations implémentées. |
| **Definition of Done** | ☐ Lot de 11 000 chronométré sur le poste cible · ☐ décomposition par étape produite · ☐ verdict sur la cible 1-2 h prononcé · ☐ si hors cible, optimisations appliquées et regain mesuré · ☐ décision `avx2` / arm64 tranchée sur mesure · ☐ export ONNX de l'`EmbeddingExtractor` traité ou explicitement écarté avec justification |
| **Dépendances** | L5 pour l'architecture définitive. **Le point de départ est mesuré dès L2** sur le modèle actuel — ne pas attendre L5 pour avoir un chiffre. |
| **Charge** | **3 j**, incertitude ± 1 j. **Fil DS si Q-14 n'est pas levée ; hors fil DS si une seconde ressource technique est disponible.** C'est le lot dont la parallélisation change l'arithmétique du plan. |
| **Risques du lot** | Découverte tardive d'un dépassement → impossible de livrer en production (R-4). D'où la mesure précoce dès L2. **La ressource « dev » attribuée à ce lot n'existe pas dans l'équipe décrite (Q-14).** |

---

### L9 — Recette comparative et mise en production

| Champ | Contenu |
|---|---|
| **Objectif** | Démontrer le progrès et basculer en production avec un verdict nommé. Porte **O-5**. |
| **Contenu** | Comparaison ancien / nouveau modèle sur le jeu de recette gelé, en réutilisant la page Comparaison V5 existante (échantillon rejoué sur 2 à 3 moteurs, juge aveuglé avec ordre permuté, mode dégradé sans clé). Recette **métier** distincte des recettes techniques (R-7) : les 2 personnes métier relisent un échantillon et prononcent un verdict. Exécution des recettes V1, V3, V4, V5 **et V6** pour la non-régression applicative. Activation du modèle en administration, tracée à l'audit. Vérification de la chaîne complète : lot, exports CSV/XLSX, écran de revue, dashboards. |
| **Livrable vérifiable** | `docs/RECETTE_NOUVEAU_MODELE.md` : tableau comparatif ancien/nouveau sur tous les critères de §7.2 du cadrage, verdict du juge aveuglé, verdict métier signé, résultats des **5** recettes techniques, procès-verbal d'activation. |
| **Definition of Done** | ☐ Comparaison ancien/nouveau produite sur le jeu de recette gelé · ☐ recette métier tenue et verdict prononcé par une personne nommée (Q-11) · ☐ recettes **V1 48/48, V3 13/13, V4 50/50, V5 112/112 et V6** au vert · ☐ débit vérifié sur un lot réel (ENF-1) · ☐ exports et écran de revue vérifiés avec le nouveau contrat de sortie · ☐ dashboards affichant les nouveaux KPI — **sous réserve de Q-15, charge non provisionnée** · ☐ modèle activé et activation tracée à l'audit (EF-12) · ☐ aucun couple hors référentiel produit par le modèle sur l'intégralité d'un lot · ☐ date effective de mise en production confirmée (Q-10) |
| **Dépendances** | L6, L8, et L7 si activé. |
| **Charge** | **4 j** (dont 2 j de fil DS pour l'activation et la non-régression), incertitude ± 1 j. |
| **Risques du lot** | Les recettes existantes tournent sur le moteur stub et ne valident que la plomberie (R-7) — d'où la recette métier obligatoire. Verdict métier négatif en fin de plan, sans temps de correction : atténué par le fait que L6 mesure déjà tous les critères. **Charge dashboards inconnue sur le chemin critique (Q-15).** |

---

### L10 — Outiller la boucle corrections → jeu d'entraînement **[CONDITIONNEL]**

| Champ | Contenu |
|---|---|
| **Objectif** | Faire des corrections de la revue humaine la source d'annotation du projet (D-11). Porte **O-6** et EF-10. |
| **Contenu** | Spécifier et implémenter l'export des corrections au format du jeu d'entraînement. Séparer un **jeu de recette gelé** qui n'alimente jamais l'entraînement. Traiter le biais d'auto-confirmation (R-11) : échantillonnage aléatoire complémentaire de verbatims à **haute** confiance, puisque seuls les cas de faible confiance sont relus. **Traiter les couples hors référentiel** issus de `taxonomy_entries` (R-12) : les corrections peuvent contenir des libellés absents du référentiel, saisis librement en revue — les filtrer, les remonter à Cultura, ou les traiter explicitement, mais jamais les propager silencieusement à l'entraînement. Documenter la procédure de réentraînement manuel validé. |
| **Livrable vérifiable** | Script d'export produisant deux fichiers de schémas documentés, avec disjonction des identifiants vérifiée · `docs/BOUCLE_AMELIORATION.md` : cadence, gouvernance, procédure, traitement du biais, traitement des couples hors référentiel. |
| **Definition of Done** | ☐ Export fonctionnel sur les corrections existantes · ☐ jeu de recette gelé disjoint, vérifié par test · ☐ échantillonnage complémentaire haute confiance spécifié (R-11) · ☐ **couples hors référentiel détectés et traités explicitement** (R-12) · ☐ procédure de réentraînement manuel documentée · ☐ garde-fou « pas de réentraînement automatique » explicitement reconduit |
| **Dépendances** | L2 pour la définition du jeu de recette gelé. |
| **Charge** | **2 j** (dont 1 j de fil DS). |
| **Statut** | **Conditionnel — deuxième lot à couper** après L7. Rationnel : aucune valeur immédiate au 30 août, puisqu'il n'existera pas encore de corrections sur le nouveau modèle. **Conséquence si coupé : O-6 et EF-10 tombent.** |

---

### L11 — Refondre l'encodage vers une clé composite (niv1, niv2) **[CONDITIONNEL À Q-5]**

| Champ | Contenu |
|---|---|
| **Objectif** | Permettre au nouveau référentiel de charger si l'unicité globale des libellés de niveau 2 n'est pas respectée. |
| **Contenu** | `src/utils/taxonomy.py` **lève une `ValueError` au chargement** si un même libellé de niveau 2 apparaît sous deux parents — le message du code recommande déjà explicitement la clé composite. Basculer l'encodage sur une clé (niv1, niv2) : module d'encodage, `encoders.json`, chaîne de préparation, masquage hiérarchique, chargement de l'historique. **Étendre à la couche API** : `app/api/app/core/taxonomy.py` et la table `taxonomy_entries`, qui porte déjà une contrainte d'unicité sur le couple — l'asymétrie entre la couche applicative (clé composite) et la couche ML (libellé seul) doit être résorbée, pas contournée. |
| **Livrable vérifiable** | Module d'encodage refondu, tests unitaires sur des libellés dupliqués entre parents, `encoders.json` au nouveau format, chargement du nouveau référentiel réussi, cohérence ML ↔ API vérifiée. |
| **Definition of Done** | ☐ Le nouveau référentiel charge sans exception · ☐ tests unitaires sur libellés dupliqués passant · ☐ masquage hiérarchique vérifié sur la clé composite · ☐ aucun couple hors référentiel produit · ☐ cohérence avec `taxonomy_entries` et `GET /api/taxonomy` vérifiée · ☐ rétrocompatibilité de lecture des anciens artefacts traitée ou explicitement abandonnée |
| **Dépendances** | L1 (verdict Q-5). **Bloque L2 et L6** si activé. |
| **Charge** | **4 j** (fil DS intégral), incertitude ± 2 j. |
| **Statut** | **Conditionnel à Q-5.** S'il est activé, le fil DS passe à 28,5 j pour 22 jours ouvrés et **le périmètre du 30 août doit être renégocié le jour même** (R-3). |

---

### L12 — Actualiser le prompt LLM et vérifier le switch multi-moteur

| Champ | Contenu |
|---|---|
| **Objectif** | Tenir EF-9 : le moteur LLM local reste sélectionnable et fonctionne avec le nouveau référentiel (D-3). |
| **Contenu** | Réécrire les prompts proposeur et raffineur de `app/worker/llm_common.py` sur le nouveau référentiel, en incrémentant `prompt_version`. Vérifier que le sentiment par thème du schéma JSON (l. 54-57) reste cohérent avec le nouveau contrat, et que la revalidation contre la taxonomie fonctionne sur les nouveaux libellés. Vérifier les garde-fous : repli `Autre / Non classé`, plafonds de confiance (0,40 et 0,30), et revue sur sentiment divergent — en notant que celle-ci ne se déclenche que si les deux sentiments diffèrent **et** que l'un est Négatif (l. 342-344), ce qui devient discutable dès lors que D-1 rend la divergence normale et non plus exceptionnelle. Tester le switch de moteur en administration. |
| **Livrable vérifiable** | Prompts versionnés · recette du moteur LM Studio sur le nouveau référentiel · procès-verbal du test de switch · note sur le comportement de `review_on_sentiment_conflict` sous D-1. |
| **Definition of Done** | ☐ Prompts réécrits et `prompt_version` incrémentée · ☐ taxonomie injectée à jour · ☐ revalidation contre le nouveau référentiel testée · ☐ garde-fous vérifiés · ☐ **pertinence de `review_on_sentiment_conflict` réévaluée sous D-1** et décision consignée · ☐ switch CamemBERT ↔ LLM testé en administration · ☐ un lot traité de bout en bout par le moteur LLM |
| **Dépendances** | L1 (nouveau référentiel) **et L5** (contrat de sortie stabilisé). Ne peut donc pas commencer avant la fin de L5. |
| **Charge** | **2 j**, dont 0,5 j de fil DS (revue). Portable par l'agent. |
| **Risques du lot** | Faible. Le mécanisme est éprouvé (recettes V4 50/50, V5 112/112). |

---

### L13 — Conduire une campagne d'annotation ciblée **[CONDITIONNEL À R-1 ET Q-8]**

| Champ | Contenu |
|---|---|
| **Objectif** | Combler le déficit d'exemples multi-thèmes à sentiments divergents, si L1 le révèle. **Seule mitigation opérationnelle de R-1.** |
| **Contenu** | Sélection ciblée de verbatims candidats au multi-thème (heuristiques : présence de connecteurs adversatifs « mais », « par contre », « en revanche » ; longueur ; désaccord entre note et polarité lexicale). Annotation par les 2 personnes métier selon le guide de L3, en priorité sur les cas à **sentiments divergents**, qui sont le point de départ à 0. **Double annotation sur un sous-ensemble** et calcul d'un accord inter-annotateurs — sans quoi la qualité des labels reste une hypothèse. Constitution prioritaire du **jeu de recette** avant le jeu d'entraînement : sans cas annotés divergents, EF-2 n'est pas seulement inatteignable, elle est **non mesurable**. |
| **Livrable vérifiable** | Fichier d'annotations au schéma du jeu d'entraînement · note d'accord inter-annotateurs chiffré · volume annoté par catégorie (mono, bi, divergent). |
| **Definition of Done** | ☐ Ressource confirmée et volume journalier établi (Q-8) · ☐ heuristiques de sélection documentées · ☐ jeu de recette divergent constitué en priorité · ☐ accord inter-annotateurs calculé sur un sous-ensemble double-annoté · ☐ volumes par catégorie chiffrés · ☐ verdict sur la mesurabilité de EF-1, EF-2 et de la famille B |
| **Dépendances** | L1 (déclenchement), L3 (guide d'annotation). Bloque partiellement L2 (jeu de recette) et L6. |
| **Charge** | **4 j** (dont 0,5 j de fil DS pour l'intégration), incertitude ± 3 j — entièrement dépendante de Q-8. Charge portée par le métier. |
| **Statut** | **Conditionnel.** Activé ou écarté à la clôture de L1. **Q-8 doit être levée avant le 5 août** pour que l'activation soit immédiate (R-13). |
| **Risques du lot** | Q-8 non levée → R-1 sans mitigation. Congés d'août côté métier (R-8). Annotation trop lente pour alimenter L6 dans les délais. |

---

## 5. Chemin critique, capacité et séquencement

### 5.1 Chemin critique

```
L1 (3 j) ──► L2 (4 j) ──► L5 (5 j) ──► L6 (5 j) ──► L9 (4 j)
   audit      protocole   sentiment    réentraî-    recette
   + gate     + baseline  par thème    nement       + prod
                          + seuil
```

**Longueur nominale : 21 jours ouvrés.**

| Scénario | Départ | Jours ouvrés restants | Verdict |
|---|---|---|---|
| L1 démarre le **30 juillet** (fichiers déposés aujourd'hui) | 30/07 | 22 | Tenable avec **1 jour** de marge |
| L1 démarre le **3 août** | 03/08 | 20 | **Dépassement de 1 jour dès le nominal** |
| L1 démarre le **5 août** | 05/08 | 18 | **Dépassement de 3 jours** |

Avec les incertitudes déclarées (± 1 sur L1, ± 1 sur L2, ± 2 sur L5, ± 2 sur L6, ± 1 sur L9),
la fourchette **arithmétique** est de 14 à 28 jours. Cette fourchette est à lire avec prudence :
la borne basse de 14 j suppose les cinq lots simultanément au plus favorable, ce qui n'est pas
un scénario planifiable. Le scénario réaliste à retenir est **21 à 25 jours**, soit un
dépassement probable de 0 à 3 jours même avec un départ le 30 juillet.

Le chemin critique ne contient ni L7, ni L8, ni L10, ni L12 — mais **L8 et L12 sont des
conditions de la mise en production** : ils doivent être parallélisés, pas reportés.

### 5.2 Contrainte de capacité — le point dur

| Fil | Charge | Capacité | Écart |
|---|---|---|---|
| **Data scientist** — lots fermes (L1 1 j, L2 4 j, L5 5 j, L6 5 j, L8 3 j, L9 2 j, L12 0,5 j) | **20,5 j** | 22 j | +1,5 j de marge |
| **Data scientist** — périmètre D-14 (fermes + L7 3 j + L10 1 j) | **24,5 j** | 22 j | **−2,5 j de déficit** |
| **Data scientist** — si L11 activé | **28,5 j** | 22 j | **−6,5 j de déficit** |
| PO, agent, métier (L3, L4, L9 recette, L13) | ≈ 12 j répartis sur 4 personnes | large | – |

**Le périmètre décidé en D-14 est en déficit de 2,5 jours-homme sur le seul fil qui porte le
chemin critique.** Les leviers, par ordre d'efficacité :

1. **Q-14** — une seconde ressource technique reprend L8 (−3 j) et une partie de L9 : le fil DS
   revient à 21,5 j. Levier suffisant.
2. **Q-7** — une machine d'entraînement plus rapide réduit l'incertitude de L6, premier poste de
   dérive. Ne résout pas le déficit nominal mais sécurise le plus gros risque.
3. **Couper L7** (−3 j) : fil DS à 21,5 j. Coût : O-4, EF-6, EF-7 tombent.
4. **Couper L10** (−1 j) : coût O-6 et EF-10.

### 5.3 Séquencement proposé

Hypothèse : fichiers déposés le **30 ou 31 juillet**. Capacité respectée semaine par semaine.

| Semaine | Jours | Fil data scientist (5 j/sem.) | Fil PO / métier / agent |
|---|---|---|---|
| **S31** — 30-31 juil. | 2 | **L1** : appui au profiling (1 j) · démarrage **L2** (1 j) | **Q-1 et Q-2 : déposer fichiers et référentiel** · lever **Q-14** et **Q-7** · sollicitation groupée Cultura (Q-4, Q-6, Q-9, Q-10, Q-11, Q-12, Q-13, Q-16) · lever **Q-8** · agent : profiling L1 (2 j) |
| **S32** — 3-7 août | 5 | **L2** (3 j restants) dont première mesure de débit · démarrage **L5** (2 j) | Clôture **L1** et **jalon de décision du 5 août** (D-5, L11, L13) · **L3** atelier règles d'arbitrage (2 j) · **L4** définition des signaux (2 j) |
| **S33** — 10-14 août | 5 | **L5** (3 j restants) · démarrage **L6** (2 j) | **L13** si activé (métier) · préparation de la recette métier · agent : rédaction de **L12** (2 j, validation différée après la fin de L5) |
| **S34** — 17-21 août | 5 | **L6** (3 j restants) · validation **L12** (0,5 j) · **L8** (1,5 j) *ou 0 j si Q-14 levée* | **L8** porté par la 2ᵈᵉ ressource si Q-14 levée (3 j) · préparation du jeu de recette métier |
| **S35** — 24-28 août | 5 | **L8** (1,5 j restants si non parallélisé) · **L9** activation et non-régression (2 j) · **L7** *(3 j, uniquement si Q-14 levée et L6 sans dérive)* | **L9** recette métier (2 j, 2 personnes) · verdict et procès-verbal d'activation · **L10** si activé (agent) |

**Cohérence de capacité, fil data scientist** : S31 = 2 j · S32 = 5 j · S33 = 5 j · S34 = 5 j ·
S35 = 3,5 j hors L7 → **20,5 j au total, égal à la charge des lots fermes**, avec 1,5 j de marge
sur les 22 disponibles. Si Q-14 est levée, L8 sort du fil DS (−3 j) et **L7 devient logeable en
S35**. Sinon, L7 et L10 ne rentrent pas — ce qui est exactement la conclusion du §5.2.

### 5.4 Parallélisations possibles

| Peut tourner en parallèle | Avec | Condition |
|---|---|---|
| L3 et L4 | L2 | Aucune. Ne consomment pas la capacité du data scientist. |
| L13 | L2, L5 | Q-8 levée. Porté par le métier. |
| L8 | L6 | **Q-14 levée.** Sinon L8 retombe dans le fil DS en S34-S35 et devient le point de tension. |
| L12 (rédaction) | L5 | Rédaction par l'agent dès S33 ; validation DS après la fin de L5. |
| L10 | L9 | Conditionnel de toute façon. Portable par l'agent. |
| L9 recette métier | L9 activation | Deux porteurs distincts (métier et DS). |
| **Non parallélisable** | L1 → L2 → L5 → L6 → L9 | Dépendances strictes de données puis d'architecture. C'est la contrainte dure du plan. |

### 5.5 Points de non-retour

| Date | Point de non-retour |
|---|---|
| **Vendredi 31 juillet** | Si les fichiers et le référentiel ne sont pas déposés, le chemin critique nominal (21 j) dépasse le temps restant. **Q-1 et Q-2 sont l'action la plus urgente du projet.** |
| **Vendredi 31 juillet** | Q-14 (seconde ressource technique) et Q-7 (machine d'entraînement) doivent être tranchées, faute de quoi le périmètre D-14 est arithmétiquement hors d'atteinte et la coupe de L7 devient automatique. |
| **Mercredi 5 août** | **Jalon de décision, clôture de L1.** Si la proportion de bi-thèmes ou de sentiments divergents est insuffisante, activer L13 (Q-8) ou renoncer à la mesurabilité de la famille B. Si Q-5 est négative, L11 s'active et **le périmètre doit être renégocié le jour même**. D-5 doit être prononcée. |
| **Vendredi 14 août** | Fin de L5 attendue. Au-delà, L7 est reportée et L10 abandonnée pour cette échéance. |
| **Vendredi 21 août** | Fin de L6 attendue. **Au-delà, la mise en production du 30 août n'est plus tenable** et le scénario de repli du §5.6 doit être déclenché — le 21 août, pas le 27. |

### 5.6 Scénario de repli

Si L6 n'est pas terminé le 21 août, ou si le fil DS a dérivé de plus de 2 jours :

**Livrer au 30 août** un modèle entraîné, mesuré sur un protocole sans fuite, comparé à
l'ancien via le dispositif V5, avec verdict métier et plan de mise en production daté —
**mais sans bascule en production**. Celle-ci est reportée à la première semaine de septembre.

C'est le repli le moins coûteux : il préserve la totalité du travail et n'exige aucune reprise.
Il doit être **présenté et accepté par Cultura à l'avance** (Q-16), et non subi fin août. Il est
référencé dans le cadrage à D-13.

---

## 6. Traçabilité objectifs → lots

| Objectif | Lots porteurs | Fragilité |
|---|---|---|
| O-1 — voir les deux sujets, et seulement quand c'est vrai | L5, L6 | Mesurabilité conditionnée à R-1 / L13 |
| O-2 — voir deux sentiments opposés | L5, L6 | Conditionnée à R-5 (sentiment déductible de la note) |
| O-3 — volumes fiables pour prioriser | L2, L6 | – |
| **O-4 — taux de revue pilotable** | **L7 uniquement** | **Lot conditionnel, 1ᵉʳ à couper** |
| O-5 — progrès démontrable | L2, L9 | – |
| **O-6 — amélioration continue** | **L10 uniquement** | **Lot conditionnel, 2ᵈ à couper** |

---

## 7. Ce que le plan ne couvre pas

Rappel de §3.2 du cadrage : plus de 2 thèmes, sortie « hors sujet » côté CamemBERT, extraction
d'entités, synthèse ou regroupement de verbatims, détection de drift, refonte du référentiel par
eXalt, réentraînement automatique, bascule du moteur principal vers un LLM, sortie du
mono-poste, refonte de l'interface.

**Non couvert et signalé comme tel :**

- La **correction du mécanisme de saisie libre de thèmes en revue** (R-12) : le défaut est
  identifié, seule sa prise en compte défensive dans L10 et L11 est prévue.
- La **charge de mise à jour des dashboards** (Q-15), exigée par la DoD de L9 mais non chiffrée.
- Le **traitement de la stoplist d'anonymisation** si L1 révèle un taux élevé de faux positifs
  (R-14) : seule la mesure est provisionnée, pas la correction.
- La **mise à jour de `docs/ETAT_DES_LIEUX_ML.md`**, où la recette V6 et le mécanisme
  `taxonomy_entries` sont absents.

Toute demande relevant de ces listes **ajoute au périmètre et retire à l'échéance**. Compte tenu
du déficit de capacité établi au §5.2, elle doit être refusée ou faire l'objet d'un arbitrage
explicite avec Cultura.

---

## 8. Journal des corrections de ce document

| Version | Date | Correction |
|---|---|---|
| v1.0 | 30/07/2026 | Version initiale. |
| **v1.1** | **30/07/2026** | **L5 réécrit** : l'objectif n'est plus de faire apparaître le second thème mais de corriger la recopie du sentiment et la sur-activation du seuil (correction du diagnostic, §1.4 e du cadrage). |
| v1.1 | 30/07/2026 | **Arithmétique de capacité corrigée** : le fil DS inclut désormais les parts de L1 et L9 précédemment omises. 20,5 j pour les lots fermes, 24,5 j pour le périmètre D-14, contre 22 j disponibles. La « marge de 1 jour » annoncée en v1.0 était fondée sur un compte incomplet. |
| v1.1 | 30/07/2026 | Convention de charges unifiée (§3.1) : les options L7, L10, L11 et L13 sont désormais cumulatives et explicites. |
| v1.1 | 30/07/2026 | **Séquencement corrigé** : surcapacité de S32 et S35 résorbée ; « Fin de L6 en S35 » supprimé, car il contredisait le point de non-retour du 21 août ; dépendance L12 → L5 respectée (rédaction en S33, validation après L5). |
| v1.1 | 30/07/2026 | Chemin critique assorti d'une **analyse de date de départ** : un démarrage au 3 août produit déjà un dépassement au nominal. Fourchette d'incertitude requalifiée (21-25 j réaliste, 14-28 j arithmétique). |
| v1.1 | 30/07/2026 | **L13 ajouté** (campagne d'annotation ciblée) : seule mitigation opérationnelle de R-1, précédemment non provisionnée (R-13). |
| v1.1 | 30/07/2026 | Recette **V6** ajoutée au périmètre de non-régression de L9. Traitement des couples hors référentiel ajouté à la DoD de L10, extension à la couche API ajoutée à L11 (R-12). |
| v1.1 | 30/07/2026 | EF-4 (distribution du nombre de thèmes en sortie) rattachée à L2 et L6. Correction du calcul du F1-micro rattachée à L2. |
| v1.1 | 30/07/2026 | D-5 (frontières poreuses) et Q-8, Q-10, Q-13, Q-14, Q-15, Q-16 rattachées à un lot, une DoD ou un point de non-retour. Contrôles d'anonymisation (R-14) ajoutés à L1. |
| v1.1 | 30/07/2026 | Ajout du §1 (avertissement liminaire), du §6 (traçabilité objectifs → lots) et de l'explicitation des conséquences de chaque coupe. |
| v1.1 | 30/07/2026 | Règle de découpage n°7 corrigée : les lots à 2 j techniques (L10, L12) sont assumés comme tels, avec leur rationnel. |

---

*Projet interne Cultura / eXalt — usage confidentiel.*
