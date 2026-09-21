# Migration de la satisfaction à la maille répondant

La révision Alembic `0011_survey_responses` crée `survey_responses` et ajoute la
clé nullable `results.survey_response_id`. La révision
`0012_survey_response_date` ajoute la date métier nullable `response_date` et
l'index `(batch_id, source_type, response_date)`. La révision
`0013_analysis_source_date_index` ajoute l'index complémentaire
`(response_date, source_type, batch_id)` utilisé par les analyses transversales.
Ces migrations ne rétro-remplissent aucune donnée impossible à reconstruire.

## Contrat fonctionnel livré

- une ligne `survey_responses` représente une réponse source ayant produit au
  moins un verbatim analysé ; plusieurs verbatims Mopinion ne donnent donc pas
  plusieurs voix au même répondant ;
- la note native et son maximum sont conservés (`1–4` pour MDTC, `1–5` pour
  Mopinion), puis projetés sur 10 uniquement pour l'affichage ;
- `client_status` vaut `ancien`, `nouveau` ou `non_renseigne`. Dans l'interface,
  ce dernier code devient **« Statut client non disponible »** ; il ne signifie
  pas « note absente » ;
- les quatre sources attendues restent dans le contrat KPI. Une source non reçue
  porte `availability_status=source_not_provided`, sans moyenne fabriquée ;
- les comparaisons utilisent `response_date`, jamais la date d'upload du lot.
- les filtres source/date des résultats, de la revue, des exports et des KPI
  utilisent ce même périmètre ; les bornes de date sont inclusives ;
- pour les nouveaux imports, `source_file` reçoit le nom original du fichier et
  non son nom technique dans le volume. La fin de traitement vient de
  `batches.finished_at`, déjà existant ;
- `response_reference` est calculée à la restitution sous la forme `REP-…` par
  un second hachage de `respondent_key`. Elle ne nécessite ni colonne ni migration
  supplémentaire et n'expose jamais l'identifiant source ou le numéro de commande.

## Déploiement

1. Sauvegarder la base et les volumes d'uploads selon la procédure d'exploitation.
2. Appliquer les migrations habituelles (`alembic upgrade head` dans le service API).
3. Redémarrer l'API et le worker avec la même version applicative.
4. Traiter un petit lot représentatif et contrôler les quatre sources, leurs
   périodes métier et la sélection automatique du lot de référence.
5. Vérifier qu'une source volontairement omise apparaît comme « source non
   reçue », et que les lignes MDTC `Ancien`, `Nouveau` et `Statut client non
   disponible` restent présentes même à zéro.

Le démarrage Docker applique automatiquement `alembic upgrade head`. En mise à
jour manuelle, sauvegarder impérativement la base avant l'étape 2.

## Lots historiques

La normalisation Mopinion 1–5 vers 1–4 n'est pas inversible : `2/5` et `3/5`
peuvent toutes deux avoir produit `2/4`. La migration ne fabrique donc ni note
native, ni répondant, ni statut client, ni date métier. Ces lots restent visibles
avec l'état « détail natif indisponible » ou « non comparable ».

Un résultat historique sans `survey_response_id` ne reçoit pas non plus de
référence pseudonymisée : l'interface et les exports indiquent une valeur absente
plutôt que d'en fabriquer une.

De même, les lots créés avant la conservation du nom original peuvent ne porter
que le nom technique (`source_00.xlsx`). Il n'est pas possible de retrouver le
nom envoyé par l'utilisateur à partir de ce seul identifiant. Aucun nom n'est
donc fabriqué ; retraiter explicitement les fichiers est la seule restauration fiable.

Pour récupérer le détail, recréer volontairement un **nouveau lot** depuis ses
fichiers source conservés, vérifier son résultat, puis archiver l'ancien lot selon
la procédure métier. Aucun retraitement automatique, écrasement ou suppression
de lot historique n'est effectué par la migration.

Le périmètre reste celui des réponses ayant produit au moins un verbatim analysé.
Inclure les répondants sans verbatim serait une extension de produit distincte.

## Retour arrière

Les migrations possèdent un `downgrade`, mais son exécution peut supprimer la
maille répondant et la date métier acquises après déploiement. En exploitation,
le retour arrière recommandé est donc applicatif : restaurer ensemble le dump et
la version précédents. Ne pas rétrograder le schéma seul sur une base alimentée.
