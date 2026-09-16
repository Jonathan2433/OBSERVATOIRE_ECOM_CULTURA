# Prompt Codex — satisfaction native par répondant

> Version de cadrage : 16 septembre 2026
>
> Branche cible : `preprod`
>
> Projet : Observatoire e-commerce Cultura / `cultura-verbatim-classifier`

Copier-coller le prompt ci-dessous dans une nouvelle tâche Codex chargée de l'implémentation.

---

## Prompt à donner à l'agent

Tu es Lead Tech senior sur l'application **Observatoire e-commerce Cultura**. Ta mission est d'implémenter de bout en bout une évolution de la mesure de satisfaction afin que le métier sache immédiatement **d'où vient une note** et **quelle population elle concerne**.

Travaille sur la branche `preprod`. Commence par vérifier la branche, l'état du dépôt et les éventuelles modifications locales. Ne supprime, n'écrase, ne committe et ne reformate aucune modification qui ne t'appartient pas. Lis les README, la documentation fonctionnelle et technique, puis le code concerné avant de modifier quoi que ce soit.

### 1. Besoin métier faisant foi

La restitution doit respecter les règles suivantes :

1. L'unité statistique est le **répondant**, jamais le nombre de verbatims produits.
2. Une moyenne distincte est calculée pour chaque type de fichier/source :
   - `MDTC-postachat` ;
   - `MDTC-postrecep` ;
   - `Mopinion-desktop` ;
   - `Mopinion-mobile`.
3. La note native de la source doit être conservée. Les échelles sont différentes :
   - MDTC : modalités natives converties en `1..4` ;
   - Mopinion : note native `1..5`.
4. Toutes les moyennes sont affichées sur 10 pour faciliter la lecture, avec la formule fixe :

   `moyenne_sur_10 = moyenne(note_native) / maximum_echelle_native * 10`

   Exemples : `3/4 = 7,5/10` pour MDTC et `3/5 = 6/10` pour Mopinion.
5. Chaque moyenne doit pouvoir être analysée selon le statut client :
   - `ancien` ;
   - `nouveau` ;
   - `non_renseigne`.
6. Ne jamais déduire ou inventer un statut client. Le statut non disponible doit être rendu visible sous `non_renseigne`, et non assimilé à un ancien ou à un nouveau client.
7. Toute moyenne affichée doit être accompagnée au minimum du type de source, de l'échelle native et du nombre de répondants notés. Les valeurs nulles ne valent jamais zéro.
8. Une moyenne globale multi-source peut exister en information secondaire, mais la restitution principale reste la ventilation par source. Si elle existe, elle doit pondérer chaque **répondant distinct** une seule fois après conversion sur 10 et expliciter son périmètre.

Le périmètre statistique attendu est celui des répondants dont la réponse a produit au moins un verbatim analysé dans le lot. Si le produit doit aussi mesurer les répondants sans verbatim, signale que cela constitue une extension de périmètre et ne mélange pas silencieusement les deux populations.

### 2. Contexte technique constaté à vérifier

Lors du cadrage, les éléments suivants ont été observés. Vérifie-les dans le code actuel avant de t'appuyer dessus :

- `config/config.yaml` décrit les sources et les colonnes de satisfaction.
- `src/preprocessing/cultura_loader.py` extrait temporairement une satisfaction et, pour Mopinion, un identifiant répondant.
- `src/preprocessing/loader.py` transforme les données avant transmission au worker.
- `app/worker/tasks.py` crée les résultats persistés.
- `app/common/models/result.py` contient le modèle `Result`.
- `app/common/migrations/versions/0010_result_satisfaction.py` a introduit la satisfaction actuelle.
- `app/api/app/api/routes_kpi.py` calcule les KPI.
- `app/web/src/api.ts` porte les contrats TypeScript de l'API.
- `app/web/src/components/SatisfactionPanel.tsx`, `app/web/src/pages/DashboardsPage.tsx` et `app/web/src/pages/ResultsPage.tsx` affichent les notes.
- Les recettes principales se trouvent notamment dans `app/tests/recette_v1.py` et `app/tests/recette_l1a_chargeur.py`.
- `docs/SPEC_CHARGEUR.md` précise actuellement que la colonne Client MDTC n'est pas ingérée, car elle est absente de plusieurs fichiers. Cette décision doit être révisée pour répondre au nouveau besoin.

État fonctionnel observé avant implémentation :

- MDTC utilise déjà une représentation interne `1..4` cohérente avec ses quatre modalités.
- Mopinion transforme actuellement `1..5` en `1..4` selon une règle du type `1→1`, `2→2`, `3→2`, `4→3`, `5→4`. Cette valeur normalisée peut rester utile au modèle ML, mais elle ne permet pas de reconstruire la note native et ne doit pas servir à la moyenne métier sur 10.
- La note brute et l'identifiant répondant existent pendant le chargement, mais sont perdus avant ou pendant la persistance.
- Les KPI actuels moyennent des lignes `Result`, donc des verbatims. Un répondant Mopinion ayant renseigné plusieurs champs peut être compté plusieurs fois.
- La requête KPI globale peut inclure des résultats provenant de lots qui ne sont pas terminés.
- Certains chemins historiques peuvent laisser entrer des notes hors plage dans les agrégats.
- Une conversion front seule du type `note_normalisee * 10 / 4` est insuffisante. Pour Mopinion, une note native `3/5` doit donner `6/10`, alors que la normalisation actuelle la ramène à `2/4`, soit `5/10`.

### 3. Données de référence mesurées lors du cadrage

Les fichiers de référence présents dans `data/raw/cultura_2026/v2_20260909` donnaient les ordres de grandeur suivants. Utilise-les comme garde-fous, sans en faire des constantes applicatives :

| Type de source | Fichiers | Répondants/verbatims analysables | Statut client connu | Ancien | Nouveau | Non renseigné |
|---|---:|---:|---:|---:|---:|---:|
| MDTC-postachat | 4 | 1 928 | 749 (38,8 %) | 502 | 247 | 1 179 |
| MDTC-postrecep | 2 | 3 869 | 3 388 (87,6 %) | 2 556 | 832 | 481 |
| Mopinion-desktop | 1 | 535 répondants / 537 verbatims | indisponible | 0 | 0 | 535 |
| Mopinion-mobile | 2 | 1 210 répondants / 1 218 verbatims | indisponible | 0 | 0 | 1 210 |

Le léger écart répondants/verbatims de Mopinion démontre pourquoi les KPI ne doivent pas être calculés sur les lignes `Result`.

### 4. Architecture cible recommandée

Privilégie une représentation persistée d'une **réponse de questionnaire**, distincte des verbatims. Par exemple, crée une entité `SurveyResponse`/`RespondentResponse` avec une ligne par répondant et par réponse source, puis relie chaque `Result` produit à cette réponse.

Champs minimaux attendus, à adapter aux conventions du dépôt :

- `id` ;
- `batch_id` ;
- `source_type` ou réutilisation contrôlée de la source du lot ;
- `source_file` ou identifiant de fichier permettant la traçabilité ;
- `respondent_key` opaque, stable dans le fichier et non porteur de PII ;
- `satisfaction_native` nullable ;
- `satisfaction_scale_max` (`4` pour MDTC, `5` pour Mopinion) ;
- `satisfaction_normalized` nullable si la normalisation ML doit être conservée à ce niveau ;
- `client_status` parmi `ancien`, `nouveau`, `non_renseigne` ;
- éventuellement `satisfaction_raw_label`, uniquement si utile à l'audit et sans donnée personnelle.

Ajoute à `Result` une clé étrangère vers cette réponse. Conserve provisoirement le champ historique `Result.satisfaction` si sa suppression créerait une migration risquée ou casserait le modèle, mais documente clairement qu'il représente la normalisation ML et non la note native métier.

Si une table séparée est réellement incompatible avec l'architecture actuelle, une solution fondée sur un `respondent_key` dupliqué dans `Result` est acceptable uniquement si les requêtes garantissent formellement le dédoublonnage et si les tests couvrent les réponses multi-verbatims. Explique alors ce compromis.

Construction de la clé répondant :

- Mopinion : partir de l'identifiant source et le rendre unique dans le contexte `type + fichier` ;
- MDTC : générer une clé déterministe à partir du contexte `type + fichier + ligne source` ;
- ne jamais exposer directement une donnée personnelle ; utiliser une empreinte stable si l'identifiant source peut être sensible ;
- ne pas dédupliquer deux fichiers différents uniquement parce qu'un identifiant technique se ressemble.

Une réponse source qui produit plusieurs verbatims doit créer une seule ligne réponse et plusieurs lignes `Result` reliées à elle.

### 5. Chargement et règles de qualité

Fais évoluer le chargeur pour transporter jusqu'à la base :

- la note native ;
- le maximum de l'échelle native ;
- la note normalisée destinée au ML, si nécessaire ;
- la clé répondant ;
- le type et le fichier source ;
- le statut client.

Règles obligatoires :

- valider la plage native (`1..4` MDTC, `1..5` Mopinion) avant agrégation ;
- exclure les notes invalides de la moyenne et exposer leur nombre dans les métriques ou les logs ;
- exclure les notes nulles du numérateur et du dénominateur ;
- ne jamais convertir une note manquante en `0` ;
- normaliser explicitement les libellés Client connus vers `ancien` ou `nouveau`, le reste vers `non_renseigne` ;
- détecter et journaliser des notes contradictoires pour une même réponse ;
- préserver le comportement attendu de la préparation ML sauf décision documentée et testée.

### 6. API attendue

Fais évoluer le contrat KPI pour retourner une ventilation explicite par source et par statut client. Le nom exact des objets peut suivre les conventions existantes, mais le contrat doit exprimer au minimum :

```json
{
  "unit": "respondent",
  "display_scale_max": 10,
  "by_source": [
    {
      "source_type": "MDTC-postachat",
      "native_scale_min": 1,
      "native_scale_max": 4,
      "respondent_count": 120,
      "rated_respondent_count": 110,
      "unrated_respondent_count": 10,
      "invalid_rating_count": 0,
      "mean_native": 3.1,
      "mean_on_10": 7.75,
      "native_distribution": {},
      "by_client_status": [
        {
          "client_status": "ancien",
          "respondent_count": 70,
          "rated_respondent_count": 65,
          "mean_native": 3.2,
          "mean_on_10": 8.0
        }
      ]
    }
  ]
}
```

Contraintes API :

- les calculs doivent partir de la table des réponses, pas de `Result` ;
- chaque répondant compte une fois dans chaque périmètre ;
- les KPI globaux doivent se limiter aux lots terminés ;
- les filtres existants de lot et de période doivent rester cohérents ;
- la somme des trois segments client doit correspondre au total de la source ;
- distinguer clairement `aucune note` d'une moyenne égale à zéro, qui ne devrait pas exister sur ces échelles ;
- versionner ou faire évoluer le contrat sans rupture non maîtrisée du front.

### 7. Restitution front attendue

La vue principale ne doit plus présenter une moyenne unique sans origine. Affiche un tableau ou des cartes par type de source avec :

- le nom lisible de la source, par exemple « MDTC — Post-achat web » ;
- la moyenne sur 10 ;
- l'échelle native d'origine, par exemple « calculée à partir d'une note sur 4 » ;
- le nombre de répondants notés ;
- la ventilation `Ancien`, `Nouveau`, `Non renseigné`, avec effectifs et moyennes ;
- un état explicite lorsque les données historiques ou le statut client sont indisponibles.

La comparaison entre types doit rester lisible sur ordinateur et mobile. Les libellés et info-bulles doivent expliquer en une phrase la conversion sur 10 et l'unité « répondant ».

Aligne également la page de résultats si elle affiche une satisfaction : elle doit indiquer la note native et son échelle, ou utiliser la conversion correcte pilotée par `satisfaction_scale_max`. Centralise les règles d'affichage ; n'utilise pas un maximum interne fixé à `4` pour toutes les sources.

Il peut déjà exister dans l'arbre de travail un fichier `app/web/src/satisfactionDisplay.ts` ou des modifications locales de `SatisfactionPanel.tsx` et `DashboardsPage.tsx` qui convertissent la note normalisée `/4` vers `/10`. Inspecte leur provenance et ne les écrase pas. Leur logique ne répond toutefois pas au présent contrat pour Mopinion : adapte-la seulement si ces changements font bien partie du travail autorisé.

### 8. Migration et données historiques

Crée une migration Alembic réversible suivant la dernière révision réellement présente dans le dépôt. N'invente pas de note native, de clé répondant ou de statut client pour les anciennes lignes.

La note Mopinion native n'est pas récupérable depuis la seule valeur normalisée actuelle, car `2/5` et `3/5` ont toutes deux pu devenir `2/4`. Les anciens lots doivent donc :

- soit être affichés avec un état « détail natif indisponible » ;
- soit être retraités depuis leurs fichiers sources dans une opération explicite et contrôlée.

Ne lance aucun retraitement destructif ou massif sans validation. Documente la stratégie de migration et la marche à suivre pour retraiter un lot.

### 9. Tests d'acceptation obligatoires

Ajoute des tests unitaires et/ou d'intégration couvrant au minimum :

1. Un répondant Mopinion avec trois champs textuels produit trois `Result`, mais une seule réponse et un seul comptage KPI.
2. Une note Mopinion native `3/5` est affichée `6/10`.
3. Une moyenne MDTC native `3/4` est affichée `7,5/10`.
4. Les quatre types de source sont distingués dans l'API.
5. `ancien + nouveau + non_renseigne` reconstitue le total de répondants pour chaque source.
6. Une note nulle est exclue de la moyenne sans devenir zéro.
7. Une note hors plage est exclue et comptabilisée comme invalide.
8. Plusieurs verbatims d'un même répondant ne modifient pas sa pondération.
9. Les KPI globaux ignorent les lots non terminés.
10. Un ancien lot sans données natives renvoie un état indisponible propre, sans moyenne fabriquée.
11. Les typings TypeScript et le build front passent.
12. Les recettes existantes pertinentes restent vertes.

Ajoute si possible un test de non-régression utilisant de petits fixtures représentatifs des quatre sources et des statuts Client réels, sans PII.

### 10. Documentation et livrables

Livre une implémentation complète comprenant :

- modèle et migration de base ;
- évolution des chargeurs ;
- évolution du worker et de la persistance ;
- calcul KPI par répondant ;
- contrat API et typings front ;
- restitution UI par source et segment client ;
- tests automatisés ;
- mise à jour de `docs/SPEC_CHARGEUR.md`, `docs/CAHIER_DES_CHARGES.md` et `docs/GUIDE_UTILISATEUR.md` si leur contenu est impacté ;
- une courte note de migration/retraitement des anciens lots.

À la fin :

1. exécute les tests backend ciblés, les recettes pertinentes et le build/typecheck front ;
2. donne les commandes lancées et leurs résultats ;
3. résume les fichiers modifiés et les décisions techniques ;
4. signale clairement toute limite restante ou toute donnée qui nécessite un retraitement ;
5. vérifie le diff final afin de ne pas embarquer de modifications étrangères à la mission.

### 11. Hors périmètre et interdictions

- Ne change pas la normalisation ou l'entraînement du modèle ML sans nécessité démontrée et validation explicite.
- Ne calcule pas la moyenne métier à partir de la valeur Mopinion normalisée `1..4`.
- Ne moyenne pas les lignes de verbatim.
- Ne masque pas la population `non_renseigne`.
- Ne fabrique pas de données historiques impossibles à reconstruire.
- Ne stocke ni n'expose de PII pour construire la clé répondant.
- Ne mélange pas silencieusement des échelles ou des populations différentes.

### 12. Définition de terminé

La mission est terminée lorsque, pour un lot neuf de chaque type de source, un utilisateur peut répondre sans ambiguïté aux questions suivantes depuis l'interface :

- Quelle est la moyenne sur 10 ?
- De quelle source et de quelle échelle native provient-elle ?
- Combien de répondants sont inclus ?
- Quelle est la moyenne des anciens clients, des nouveaux clients et des statuts non renseignés ?
- Les répondants ayant plusieurs verbatims ont-ils été comptés une seule fois ?

Toutes ces réponses doivent être justifiées par les données persistées, vérifiables par l'API et couvertes par les tests.
