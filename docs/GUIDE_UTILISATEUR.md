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
2. Glisser-déposer les **deux fichiers Excel** du mois :
   - **MDTC** (`.xlsx`) — retours post-commande ;
   - **Mopinion** (`.xlsx`) — formulaire du site.
   > Au moins un des deux est requis. Les colonnes obligatoires sont vérifiées :
   > un fichier au mauvais format est **refusé avec un message explicite**.
3. Régler éventuellement le **seuil de revue** (défaut **0,50**) : en dessous de
   ce score de confiance, un verbatim part en file de revue.
   > 🔗 **Raffinement (optionnel, V5)** : le champ **« 2ᵉ moteur »** permet de chaîner un
   > second moteur LLM local (LM Studio) qui **relit et corrige** la classification du
   > modèle actif. En cas de **désaccord sur le grand thème**, le verbatim part **en revue
   > forcée**. Laisser « Aucun » = traitement classique à un seul moteur.
4. **Lancer**. Le traitement est **asynchrone** : la barre de progression avance
   (anonymisation → nettoyage → classification), l'interface reste libre.
5. À la fin : nombre de verbatims traités, **% en revue**, durée. 

> ⏱️ Un lot de ~11 000 verbatims se traite en **moins d'une heure** (modèle réel
> CamemBERT). Le mode *démonstration* (stub, sans modèle déposé) est quasi instantané.

---

## 3. Consulter et exporter les résultats

Menu **Lots → (un lot) → Résultats**.

- **Tableau paginé** : verbatim anonymisé, thème niv.1/niv.2 + scores, sentiment,
  signaux (rupture / churn / insatisfaction), confiance, statut.
- **Filtres** : thème (recherche « contient » sur niv.1 **ou** niv.2), sentiment,
  signaux, statut de revue, texte libre. *(< 2 s même sur 11k.)*
- **Exports** :
  - **CSV** (UTF-8 BOM, ré-ouvrable dans Excel FR sans casser les accents) ;
  - **XLSX**.
  Les exports contiennent **les colonnes d'origine + les colonnes du modèle**
  (format identique au POC).

> 🔒 Le tableau n'affiche **jamais** le texte brut : seul le **texte anonymisé**
> (e-mails, téléphones, n° de commande, noms remplacés par `[EMAIL]`, `[TEL]`,
> `[COMMANDE]`, `[NOM]`) est stocké et affiché.

---

## 4. Revue humaine & corrections

Menu **Lots → (un lot) → Revue**.

1. Les verbatims **sous le seuil** sont présentés, **du moins confiant au plus confiant**.
2. Pour chacun : corriger le **thème niv.1/niv.2**, le **sentiment**, les **signaux**.
   - Le sous-thème (niv.2) proposé est **contraint par le niv.1 choisi** : impossible
     de sélectionner un couple invalide.
3. Valider → le verbatim est marqué **« corrigé »**. La correction est **tracée**
   (qui, quand, ancienne → nouvelle valeur).
4. **Exporter les corrections validées** : ce fichier sert au ré-entraînement
   (opération hors application, pilotée par l'équipe data).

---

## 5. Tableaux de bord

Menu **Tableaux de bord** (global) et **Lots → (un lot) → Tableau de bord**.

- **KPI modèle** (version active) : F1 niv.1/niv.2, sentiment, signaux, avec
  **alerte visuelle** si un indicateur passe sous son seuil cible.
- **KPI résultats** : volume, % en revue, distribution des thèmes/sentiments,
  comptage des signaux, taux de correction.
- **Volumétrie & tendances** : évolution mensuelle, top thèmes vs mois précédent.
- **Thèmes × sentiment (volumétrie)** : barres empilées croisant le **volume** de
  chaque thème et la **répartition de sentiment** (Négatif / Neutre / Positif).

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
| Fichier refusé à l'upload | Mauvais format / colonne manquante | Vérifier que c'est bien l'export `.xlsx` attendu (MDTC ou Mopinion) |
| Le lot reste « en cours » longtemps | Traitement normal (gros volume) | Laisser tourner ; la page se met à jour seule |
| Thèmes/sentiments peu pertinents | Aucun modèle réel déposé (mode démo/stub) | Voir l'exploitant : déposer + activer le modèle CamemBERT |

Pour l'installation, la sauvegarde et le dépôt de modèle : voir **EXPLOITATION.md**.
