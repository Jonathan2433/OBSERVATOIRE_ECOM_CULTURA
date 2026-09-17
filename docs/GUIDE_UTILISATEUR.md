# Guide utilisateur — Observatoire Ecom Studio

Application interne de classification et de pilotage des verbatims clients Cultura.
100 % locale, hors ligne, sur le poste de l'analyste.

> **Rôles** : *Analyste* (traitement, consultation, revue, exports) et *Admin*
> (tout cela + comptes, configuration, purge, audit, modèles).

---

## 1. Se connecter

1. Ouvrir le navigateur sur **http://localhost:8080**.
2. Saisir identifiant + mot de passe (fournis par l'administrateur).
3. Après 5 échecs, le compte est **temporairement verrouillé** (5 min) — sécurité anti-bruteforce.

L'écran d'accueil résume l'activité (derniers lots, KPI modèle).

---

## 2. Lancer un traitement mensuel (le run type)

1. Menu **Lots → Nouveau lot**.
2. Glisser-déposer **tous les exports du mois d'un coup** — `.xlsx` ou `.csv`,
   jusqu'à **20 fichiers** : post-achat et post-réception, ancien et nouveau
   format, Mopinion desktop et mobile.
   > **Vous n'avez rien à déclarer.** L'application reconnaît chaque export à son
   > jeu de colonnes, pas à son nom ni à son extension : elle distingue seule un
   > post-achat d'un post-réception, un desktop d'un mobile, l'ancien format du
   > nouveau. Les CSV sont lus quel que soit leur encodage (UTF-8, Windows-1252…).
   >
   > La liste des fichiers déposés s'affiche sous la zone ; on peut en retirer un.
   > Déposer deux fois le même fichier ne le compte qu'une fois.
   >
   > **Un fichier non reconnu arrête le lot en le nommant**, plutôt que de le
   > traiter amputé d'une source : un mois incomplet fausserait les volumes, qui
   > sont la raison d'être de l'outil.
3. Régler éventuellement le **seuil de revue** : en dessous de ce score de
   confiance, un verbatim part en file de revue.
   > Le défaut **dépend du moteur**, parce que les modèles ne sont pas également
   > sûrs d'eux. Le modèle **Cultura 2026** utilise **0,70** — calé pour renvoyer
   > 10 à 15 % des verbatims en relecture, la charge visée. Le modèle **V1**
   > utilise 0,50. Un même seuil sur les deux donnerait, sur l'un, une file vide.
   > 🔗 **Raffinement (optionnel, V5)** : le champ **« 2ᵉ moteur »** permet de chaîner un
   > second moteur LLM local (LM Studio) qui **relit et corrige** la classification du
   > modèle actif. En cas de **désaccord sur le grand thème**, le verbatim part **en revue
   > forcée**. Laisser « Aucun » = traitement classique à un seul moteur.
4. **Lancer**. Le traitement est **asynchrone** : la barre de progression avance
   (anonymisation → nettoyage → classification), l'interface reste libre.
5. À la fin : nombre de verbatims traités, **% en revue**, durée. 

> ⏱️ La cible d'exploitation est un lot de ~11 000 verbatims en **moins d'une
> heure**. Cette mesure reste à confirmer sur le poste cible avec le modèle réel
> CamemBERT. Le mode *démonstration* (stub) est quasi instantané.

---

## 3. Consulter et exporter les résultats

Menu **Lots → (un lot) → Résultats**.

- **Tableau paginé** : verbatim anonymisé, **thèmes** (principal *et* second),
  sentiment de chaque thème, **note du client**, signaux, confiance, statut.
- **Filtres** : thème (recherche « contient » sur les **quatre** champs de thème :
  niv.1 et niv.2, du thème principal comme du second), sentiment, note du client,
  bi-thème, signaux, statut de revue, texte libre. *(< 2 s même sur 11k.)*
- **Exports** :
  - **CSV** (UTF-8 BOM, ré-ouvrable dans Excel FR sans casser les accents) ;
  - **XLSX**.
  Les exports contiennent **la source, la note du client, les colonnes d'origine
  et les colonnes du modèle** (bloc modèle identique au POC, colonne pour colonne).

### Deux thèmes par verbatim, et ils comptent tous les deux

Le modèle retient **jusqu'à deux thèmes** par verbatim. Le second est marqué
**« 2e »** dans le tableau, avec son propre sous-thème et son propre sentiment —
un client peut être satisfait de la livraison et mécontent du produit dans la
même phrase, et la V4 calcule bien un sentiment par thème retenu.

Le filtre « Thème » ramène aussi les verbatims qui n'évoquent le sujet **qu'en
second**. Sans cela, un thème presque toujours cité en appui resterait
introuvable à l'écran alors qu'il figure dans l'export.

### La note du client n'est pas le signal d'insatisfaction

Deux colonnes voisines, deux natures différentes :

| | Origine | Ce que ça dit |
|---|---|---|
| **Note client** | déposée par le client dans le formulaire | ce qu'il a coché |
| **Insatisf.** (signal) | déduit par le modèle du **texte** | ce qu'il a écrit |

Les deux divergent régulièrement, et c'est précisément l'écart qui est
intéressant. Le tableau affiche la **note native** (`3/4` pour MDTC, `3/5` pour
Mopinion) et son équivalent sur 10. Une note absente ou un ancien lot sans détail
natif s'affiche comme indisponible, jamais comme 0.

> 🔒 Le tableau n'affiche **jamais** le texte brut : seul le **texte anonymisé**
> (e-mails, téléphones, n° de commande, noms remplacés par `[EMAIL]`, `[TEL]`,
> `[COMMANDE]`, `[NOM]`) est stocké et affiché.

### « non mesuré » n'est pas « absent »

Certains moteurs n'ont **pas de détecteur** pour tous les signaux. Le modèle
Cultura 2026 n'en a que pour l'insatisfaction : le corpus ne compte que 64
exemples de churn et 32 de rupture, trop peu pour un détecteur dont on puisse
mesurer la fiabilité.

Dans ce cas la colonne affiche **« non mesuré »**, et non l'absence de signal.
La nuance est importante : « pas de rupture détectée » laisserait croire qu'on a
cherché. L'export conserve `false` pour ne pas casser le format, mais l'écran dit
la vérité — survolez l'info-bulle pour le détail.

---

## 4. Revue humaine & corrections

Menu **Lots → (un lot) → Revue**.

1. Les verbatims **sous le seuil** sont présentés, **du moins confiant au plus confiant**.
2. Pour chacun : corriger le **thème principal niv.1/niv.2**, son **sentiment**,
   le **second thème** éventuel et les **signaux**.
   - Le second thème est présenté séparément avec son propre sous-thème et son
     propre sentiment. Il peut être corrigé, ajouté à un verbatim mono-thème ou
     supprimé. Le nombre de thèmes est recalculé automatiquement.
   - Le sous-thème (niv.2) proposé est **contraint par le niv.1 choisi** : impossible
     de sélectionner un couple invalide.
   - **Les thèmes proposés sont ceux du moteur qui a produit CE lot**, pas ceux du
     moteur actif au moment où vous ouvrez la page. Un lot ancien se relit donc avec
     le référentiel qui a servi à le classer. Les deux référentiels en service ne
     partagent aucun sous-thème : sans cette règle, la liste proposée n'aurait aucun
     rapport avec ce que vous relisez.
   - Un couple absent du référentiel peut être saisi : il est **enregistré** et
     proposé ensuite. C'est ainsi que le référentiel s'enrichit par l'usage.
3. Valider → le verbatim est marqué **« corrigé »**. La correction est **tracée**
   (qui, quand, ancienne → nouvelle valeur).
4. **Exporter les corrections validées** : ce fichier sert au ré-entraînement
   (opération hors application, pilotée par l'équipe data).

---

## 5. Tableaux de bord

Menu **Tableaux de bord** (global) et **Lots → (un lot) → Tableau de bord**.

- **KPI modèle** (version active) : F1 niv.1/niv.2, sentiment, signaux, avec
  **alerte visuelle** si un indicateur passe sous son seuil cible.
  > **Une case absente veut dire « non mesuré », jamais zéro.** Chaque moteur ne
  > publie que les métriques **validement** mesurées : le modèle V1 n'affiche que
  > le sentiment, faute d'évaluation thématique fiable (la sienne portait sur un
  > découpage où 99,6 % des textes de test se retrouvaient à l'entraînement).
  > Comparer les deux moteurs sur les cases communes, pas sur les cases vides.
- **KPI résultats** : volume, % en revue, **bi-thèmes**, distribution des
  thèmes/sentiments, comptage des signaux, taux de correction.
- **Volumétrie & tendances** : évolution mensuelle, top thèmes vs mois précédent.
- **Thèmes × sentiment (volumétrie)** : barres empilées croisant le **volume** de
  chaque thème et la **répartition de sentiment** (Négatif / Neutre / Positif),
  **toutes mentions confondues** — chaque thème y apparaît avec *son* sentiment.

### « Thème principal » ou « toutes mentions » : deux questions différentes

La carte *Répartition des thèmes* propose deux angles, qui ne se remplacent pas :

- **Thème principal** — un verbatim, une voix : son thème de tête. La somme fait
  le nombre de verbatims classés.
- **Toutes mentions** — thème principal **et** second thème. La somme dépasse le
  nombre de verbatims, et c'est normal : un verbatim bi-thème compte deux fois.

Le second angle n'est pas un raffinement cosmétique. Sur un lot de 561 verbatims
de septembre, le thème **Académie** n'apparaît **jamais** en thème principal et
quatre fois en second : la vue « thème principal » seule le rendait invisible.
La carte *Second thème seul* isole exactement ces sujets-là.

### Analyse automatique des verbatims

La synthèse affiche ensuite les cinq sous-thèmes les plus présents dans les
**réponses textuelles ouvertes** pour Mopinion mobile/ordinateur, MDTC
post-achat et MDTC post-réception. Pour chaque classification, elle montre le
**nombre de verbatims**, sa **part dans les verbatims de la source**, son rang
et l'évolution de cette part en points par rapport au lot de référence.

Cette vue porte sur tous les verbatims, et non sur le seul signal ML
`insatisfaction forte`. Elle compte le thème principal et le second thème. Un
verbatim peut donc alimenter deux classifications différentes, mais il ne peut
jamais être compté deux fois dans la même. Si le modèle ou le référentiel a
changé, les volumes courants restent lisibles mais les deltas sont marqués
« non comparable ». Les réponses aux **questions fermées** du formulaire ne
sont pas incluses dans ces thèmes : leur restitution nécessite un indicateur
distinct et une correspondance métier validée avec les choix du formulaire.

Les quatre emplacements de source restent présents. La mention « Aucune donnée
reçue pour cette source » signifie que l'export correspondant n'était pas dans
le lot ; elle ne doit pas être interprétée comme une mesure à zéro.

### Satisfaction client déclarée

Le panneau *Satisfaction* restitue ce que les clients ont **coché**, avec une
carte par source. La moyenne est affichée sur 10 mais calculée depuis l'échelle
native (`moyenne native / maximum natif × 10`). L'unité est le **répondant** :
plusieurs champs Mopinion remplis par la même personne ne lui donnent pas plus
de poids. Pour MDTC, chaque carte conserve les lignes `Ancien`, `Nouveau` et
`Statut client non disponible`, même lorsque leur effectif est nul. Dans les
exports Mopinion actuels, aucun champ ne permet de déterminer si le répondant
est ancien ou nouveau : toutes les réponses Mopinion sont donc regroupées sous
`Statut client non disponible`. Ce libellé ne signifie pas que la note de
satisfaction est manquante.

Le bloc **Comparaison inter-lots** permet de choisir un lot de référence. Sans
choix manuel, l'application retient le dernier lot terminé dont la période
métier précède la période courante sans la chevaucher. La date de traitement du
lot n'est jamais utilisée : un export d'août déposé en septembre reste une
donnée d'août.

Le badge d'évolution se lit en **points sur 10** : `+0,10 pt` signifie que la
moyenne est passée, par exemple, de `8,10/10` à `8,20/10`. Il ne s'agit pas d'une
hausse de 10 %. Les deux périodes et les deux effectifs notés restent affichés
pour ne pas interpréter de la même façon une évolution sur 20 réponses et une
évolution sur 10 000 réponses.

Précautions portées par l'écran lui-même :

- une **note absente** n'est pas un zéro : elle est comptée à part et ne pèse sur
  aucune moyenne ;
- une **source absente du lot courant** reste affichée comme non reçue, sans
  fabriquer une moyenne ni transformer son absence en zéro ;
- une valeur hors plage est signalée comme invalide et exclue du calcul ;
- les lots antérieurs à cette évolution affichent « détail natif indisponible ».
  Leur valeur Mopinion normalisée ne permet pas de retrouver la note native : il
  faut retraiter leurs fichiers source de manière explicite ;
- une source sans date métier, absente du lot de référence ou dont l'échelle a
  changé affiche « non comparable ». La date d'upload n'est jamais utilisée en
  remplacement.

---

## 6. Test à la volée

Menu **Test à la volée** : saisir un verbatim (et un score de satisfaction
facultatif) pour voir la prédiction immédiate. Outil de diagnostic/démonstration —
n'enregistre rien. Un **sélecteur de moteur** (V5) permet d'essayer un moteur précis
— y compris **Claude (comparaison)** si une clé est configurée — sans changer le modèle
de production.

---

## 6 bis. Comparer les moteurs (V5)

Menu **Lots → (un lot terminé) → Comparaison**. Permet de **mettre en regard 2-3 moteurs**
sur un échantillon du lot, pour décider lequel garder.

1. *(Admin)* Choisir les **moteurs** à comparer, la **taille d'échantillon** (max 200) et
   une **graine** (rejouer à l'identique). Cocher **« Juge Claude »** pour faire arbitrer
   les désaccords (si une clé Claude est configurée).
2. **Comparer** → le système rejoue l'échantillon (texte déjà anonymisé) et affiche :
   - **Accord entre moteurs** : part des verbatims classés dans le **même grand thème** ;
   - **Assurance moyenne** : la confiance que **chaque moteur s'attribue** — ⚠️ c'est son
     assurance, **pas sa justesse** ;
   - **Vitesse** (ms/verbatim, plus bas = plus rapide) et **répartition des sentiments** ;
   - si le juge a tourné : **win-rate** (qui gagne les désaccords) + **exemples arbitrés**
     (verbatim, classifications A/B, gagnant et justification de Claude).
3. **Exporter (CSV)** le détail des prédictions rejouées.

> 👥 **Lancer** une comparaison = **admin** ; tout le monde (analyste+) peut **consulter**.
> Le juge Claude envoie les verbatims **divergents** (anonymisés) à l'API Anthropic
> (consomme du crédit) ; **sans clé**, la page reste utile en **mode dégradé** (sans juge).

---

## 7. Administration (rôle Admin)

- **Utilisateurs** : créer / activer / désactiver des comptes, attribuer un rôle.
  *(Le dernier admin actif ne peut pas être supprimé.)*
- **Administration → Configuration** : durée de **rétention** (mois) et **seuil de
  revue par défaut**. *Une modification s'applique aux **nouveaux** lots ; les lots
  passés gardent leurs paramètres d'origine.*
- **Administration → Rétention (RGPD)** : **Purger** supprime définitivement les
  lots (et leurs verbatims/corrections + fichiers déposés) au-delà de la rétention.
  La purge tourne aussi **automatiquement au démarrage**.
- **Administration → Journal d'audit** : qui a fait quoi, quand (connexions,
  création de lot, corrections, config, purge, gestion des comptes, activation de modèle).
- **Modèles** : déposer une nouvelle version dans le volume `data/models` puis
  l'**activer en un clic** (voir le guide d'exploitation). Un **second moteur optionnel**
  (*LM Studio (LLM)*) peut y être activé s'il est configuré : **rien ne change côté analyste**,
  seules les prédictions des **nouveaux** lots sont produites par le moteur choisi.
  **Plusieurs modèles CamemBERT peuvent coexister** — activer l'un n'efface pas
  l'autre, et revenir en arrière est une simple resélection. Les lots déjà traités
  ne sont **jamais** reclassés : ils gardent la classification du moteur qui les a
  produits, ainsi que son référentiel en revue.
  Le moteur **Claude (API)** y apparaît (si une clé est configurée) avec la mention
  **« comparaison uniquement »** et **aucun bouton Activer** : il sert au *Test à la volée*
  et à la *Comparaison*, **jamais** au traitement d'un lot de production.

---

## 8. Ce que l'application ne fait jamais

- Elle **n'envoie aucune donnée** hors de votre poste (pas d'Internet, pas de cloud).
- Elle **ne stocke jamais** un verbatim non anonymisé.
- Elle **ne déclenche aucune action métier** (ne contacte aucun client) : c'est un
  **outil d'aide à l'analyse**, pas un outil d'action.
- Une prédiction automatique est **toujours accompagnée de son score** et de son
  statut (auto / en revue / corrigé) — jamais présentée comme une vérité validée.

---

## 9. Problèmes fréquents

| Symptôme | Cause probable | Solution |
|---|---|---|
| « Identifiants invalides » répété puis blocage | 5 échecs → verrouillage 5 min | Attendre, ou demander à l'admin de réinitialiser le mot de passe |
| Fichier refusé à l'upload | Extension autre que `.xlsx` ou `.csv` | Réexporter dans l'un des deux formats |
| « Colonnes obligatoires manquantes » | Le fichier ne correspond à aucun format connu (ni Cultura 2026, ni historique) | Vérifier qu'il s'agit bien d'un export MDTC ou Mopinion complet ; le message liste les colonnes attendues |
| Le lot reste « en cours » longtemps | Traitement normal (gros volume) | Laisser tourner ; la page se met à jour seule |
| Thèmes/sentiments peu pertinents | Aucun modèle réel déposé (mode démo/stub) | Voir l'exploitant : déposer + activer le modèle CamemBERT |
| Deux lots du même mois n'ont pas les mêmes thèmes | Ils ont été traités par des **moteurs différents**, dont les référentiels diffèrent | Normal. Le moteur est indiqué sur le lot ; la revue sert le bon référentiel automatiquement |
| Beaucoup plus de verbatims en revue que d'habitude | Seuil de revue trop haut pour ce moteur, **ou** verbatims éloignés de ce que le modèle a vu à l'entraînement | Ajuster le seuil au lancement du lot ; en parler à l'exploitant si l'écart persiste |
| Les colonnes churn / rupture sont vides | Le moteur actif n'a pas de détecteur pour ces signaux (voir §3) | Attendu. L'écran affiche « non mesuré » ; l'export garde `false` |

Pour l'installation, la sauvegarde et le dépôt de modèle : voir **EXPLOITATION.md**.
