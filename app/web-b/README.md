# Front « Direction B » — branché sur l'API Observatoire Ecom Studio

Front-end de l'Observatoire Ecom Studio reprenant la maquette **Direction B**
(dense & instrumenté, design system Untitled UI · violet `#7F56D9`), réécrit en
**JavaScript vanilla sans dépendance** et **branché sur l'API FastAPI réelle**
(`app/api`). Alternative au front React de `app/web` ; même backend, même proxy.

## Comment c'est branché

| Pièce | Rôle |
|---|---|
| `index.html` | coquille (tokens CSS + police Inter), monte `api.js` puis `app.js` |
| `api.js` | **client API** fidèle (miroir de `app/web/src/api.ts`) + mode démo |
| `app.js` | état, rendu (toutes les vues Direction B), actions → `window.API` |
| `nginx.conf` | identique au service `web` : sert le statique + proxifie `/api` |
| `Dockerfile` | image nginx statique (aucun build node) |

- **Auth** : session par cookie httpOnly (JWT). `api.js` envoie `credentials:'include'` ;
  rien à gérer côté front. Au démarrage, `GET /api/auth/me` restaure la session.
- **Même origine** : le front et `/api` sont servis par le même nginx → CSP stricte
  respectée (aucun script inline, aucune ressource distante, `connect-src 'self'`).
- **Endpoints utilisés** : exactement ceux de `api.ts` — `auth/*`, `batches`,
  `batches/{id}/{results,review,kpi,progress,export,cancel}`, `results/{id}` (PATCH),
  `predict`, `taxonomy`, `kpi/{volumetry,model}`, `models[/activate,/rescan]`,
  `users`, `audit`, `config`, `admin/{ops,purge}`, `meta`, `corrections/export`.

## Lancer (à la place du front React)

Un override Compose bascule le service `web` vers ce dossier :

```bash
cd cultura-verbatim-classifier
docker compose up --build            # docker-compose.override.yml est auto-fusionné
# → http://localhost:8080  (front Direction B sur le backend réel)
```

**Revenir au front React** : supprimer/renommer `docker-compose.override.yml`, ou
`docker compose -f docker-compose.yml up --build` (sans override).

> Validé en local le 23/06/2026 : `web` sert le front, `GET /api/health` OK
> (db+redis), login admin → 200, `me`/`batches`/`taxonomy`(20 thèmes)/`kpi/model`/
> `meta`/`audit` → 200. Le `worker` doit tourner pour qu'un lot soit réellement
> traité (création → file Redis → worker).

## Mode démo (aperçu sans backend)

Ouvrir `index.html` en `file://`, ou ajouter `?demo=1` à l'URL : `api.js` sert
alors des fixtures en mémoire (mêmes formes que l'API). Utile pour la revue design.
Forcer le live : `?live=1`.

## Correspondances front ↔ API (écarts assumés)

L'API ne renvoie pas tout ce que la maquette affichait ; le front s'adapte au
backend **sans le modifier** :

- **Sentiments** : API `Négatif|Neutre|Positif` → puces `NÉG|NEU|POS`.
- **Statuts de lot** : `pending|running|done|failed|canceled` → `attente|en cours|terminé|échec|annulé`.
- **Signaux** : booléens `signal_rupture|churn|insatisfaction` → puces `RUP|CHU|INS`.
- **Accueil** : « Confiance moy. » (absente de l'API) remplacée par **F1 modèle niv.1**
  (`kpi/model.metrics.f1_macro_niv1`). « Lots ce mois » = mois du lot le plus récent.
- **Détail › Tableau de bord** : les 4 cartes sont `Volume / En revue / Erreurs / Durée`
  (le KPI lot n'expose pas « taux de correction » ni « confiance moyenne »).
- **Dashboards › Qualité du modèle** : `f1_macro_niv1`, `f1_macro_niv2`,
  `accuracy_sentiment` (« Précision sentiment »), `recall_rupture` (« Rappel rupture »).
  Si le modèle actif est le **stub** (pas de CamemBERT monté), `metrics` est `null`
  → affichage « — / n/d » (état honnête, pas une erreur).
- **Résultats** : filtres `q`, thème (`niv1`), sentiment, signaux, revue → paramètres
  serveur ; le statut « Corrigé » est filtré côté client (pas de paramètre dédié).
  Pagination via `limit`/`offset` (Préc./Suivant).
- **Revue** : `PATCH /api/results/{id}` action `correct` ; la file se recharge après validation.
- **Mot de passe** : minimum **12 caractères** (contrainte backend).
- **Rôles** : la section *Administration* (Utilisateurs, Administration) n'apparaît
  que pour un compte `admin` ; un analyste obtient 401/403 et un panneau d'accès refusé.

## À faire pour brancher un vrai modèle

Le moteur actif est le `stub-heuristique` tant qu'aucun CamemBERT n'est monté dans
`/data/models` (cf. `app/worker/model_registry.py`). Une fois le modèle déposé et
re-scanné (bouton « Re-scanner » de l'onglet Administration › Modèles), ses métriques
F1 alimentent automatiquement l'accueil et les tableaux de bord.
