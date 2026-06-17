# Suivi d'avancement — V1 « Observatoire Ecom Studio »

> Tableau de bord vivant du développement par lots. Mis à jour à chaque fin de lot.
> Réf. : [CAHIER_DES_CHARGES.md](CAHIER_DES_CHARGES.md) · [PLAN_DEVELOPPEMENT_V1.md](PLAN_DEVELOPPEMENT_V1.md)
>
> Cadence : **1 lot = 1 branche git = 1 incrément relisable**, puis **validation du PO** avant le lot suivant.
> Légende statut : ⬜ À faire · 🟦 En cours · ✅ Fait (validé PO) · ⏸️ En attente de validation

| Lot | Intitulé | Statut | Branche |
|---|---|---|---|
| L0 | Socle projet & conteneurisation | ✅ Fait (validé PO) | `lot/0` (mergé) |
| L1 | Auth, comptes & rôles | ✅ Fait (validé PO) | `lot/1` (mergé) |
| L2 | Cœur ML : worker async + gestion modèle | ⏸️ En attente de validation | `lot/2-core-ml` |
| L3 | Ingestion & lancement de lot + suivi | ⏸️ En attente de validation | `lot/3-ingestion` |
| L4 | Consultation résultats + exports (→ MVP) | ⬜ | — |
| L5 | Revue humaine & corrections | ⬜ | — |
| L6 | Tableaux de bord & KPI | ⬜ | — |
| L7 | Historique, audit, config & rétention | ⬜ | — |
| L8 | Durcissement, RGPD, perf, recette V1 | ⬜ | — |

---

## L0 — Socle projet & conteneurisation ✅ (validé PO le 2026-06-17 — accueil affiché, DB/Redis OK)

**Objectif** : fondations techniques + lever le risque image worker arm64 (torch/onnx).

Critères d'acceptation :
- [x] Arborescence `app/` (api / worker / web) + moteur `src/` réutilisable
- [x] `docker-compose.yml` (web, api, worker, db Postgres, redis) + `.env.example`
- [x] `docker compose config` valide (syntaxe) — vérifié
- [x] API FastAPI : `/health` + `/api/health` + config + logging structuré
- [x] Squelette web React/TS (Vite) appelant `/api/health`
- [x] Worker RQ qui démarre et se connecte à Redis (code + bootstrap)
- [x] Base Postgres + Alembic configuré (migration baseline `0001`)
- [x] Exposition **localhost uniquement**, aucun accès réseau sortant au runtime (par conception)
- [ ] **À exécuter sur le poste (daemon Docker requis)** : `docker compose up --build` → page d'accueil + DB/Redis « OK ». *Valide aussi le build de l'image worker arm64 (torch/onnx) — risque technique #1.*

**Reste pour clore L0** : lancer `docker compose up --build` sur le laptop cible et confirmer l'écran d'accueil (composants OK). Ensuite → validation PO → merge.

---

## L1 — Auth, comptes & rôles ✅ (validé PO le 2026-06-17)

**Objectif** : sécuriser l'accès, poser le RBAC (Analyste / Admin).

Critères d'acceptation :
- [x] Table `users` (Alembic `0002`) ; mots de passe hachés (**argon2**)
- [x] Connexion / déconnexion (JWT en cookie **httpOnly**) ; session expirante (8h)
- [x] `GET /api/auth/me` ; RBAC **côté API** (dépendances `get_current_user` / `require_admin`)
- [x] Admin : créer / désactiver / réactiver, réinitialiser mot de passe, changer le rôle
- [x] Anti-bruteforce (verrouillage temporaire après 5 échecs)
- [x] Admin initial créé au démarrage si aucun utilisateur (via `.env`)
- [x] Front : page de connexion, shell authentifié, page admin « Utilisateurs », déconnexion
- [x] Garde-fous : pas d'auto-désactivation, dernier admin protégé ; non-authentifié bloqué ; Analyste bloqué sur écrans admin

**Validation automatisée** : test d'intégration FastAPI/SQLite **11/11 OK** (login, RBAC, garde-fous, validation mot de passe) ; front **type-check TS strict + build Vite OK**.
**Reste pour clore L1** : `docker compose up --build` sur le poste → se connecter (admin du `.env`) → créer un analyste → vérifier les accès. Puis validation PO → merge.

## L2 — Cœur ML : worker async + gestion modèle ⏸️

**Objectif** : industrialiser le moteur du POC en traitement asynchrone tracé.

Critères d'acceptation :
- [x] Package partagé `common` (DB + modèles ORM) importé par `api` ET `worker`
- [x] Tables `batches`, `results` (texte **anonymisé** uniquement), `model_versions` (Alembic 0003)
- [x] Registre de modèles : découverte stub + modèle réel dans `/data/models`, activation (admin)
- [x] Tâche worker : lot Excel -> anonymisation -> nettoyage -> inférence -> résultats en base
- [x] Progression incrémentale (n traités/total) + gestion d'erreur **par verbatim**
- [x] Traçabilité **lot ↔ version de modèle** ; un seul job lourd concurrent (1 worker)
- [x] Mode **stub** (heuristique, sans torch) si aucun modèle réel -> app démontrable avant entraînement
- [x] Endpoints : `POST/GET /api/batches`, `GET /api/batches/{id}` (+ `/progress`), `GET /api/models`, `POST /api/models/{id}/activate`, `POST /api/models/rescan`
- [x] Aucun verbatim non anonymisé en base (seul `verbatim_analyse` est stocké)

**Validation automatisée** : test E2E FastAPI/SQLite **14/14 OK** (upload → traitement worker → 30 résultats persistés, hiérarchie taxonomie respectée, colonnes d'origine, progression, registre stub actif).
**Reste pour clore L2** : sur le poste, `docker compose down -v && docker compose up --build` (rebuild après refactor `common` + nouvelles deps API), vérifier que le worker synchronise le registre et que `GET /api/models` répond. (L'UI de lancement des lots arrive au L3.)

**Décision (D7)** : L2 embarque un **classifieur stub** (mots-clés) activé tant qu'aucun modèle CamemBERT n'est déposé/activé, afin de rendre l'app démontrable de bout en bout sans attendre l'entraînement (~2-4h). Le modèle réel se branche via le registre.
## L3 — Ingestion & lancement de lot + suivi ⏸️

**Objectif** : permettre au métier de charger les fichiers et lancer/suivre un lot.

Critères d'acceptation :
- [x] Écran « Lots » : liste des lots (statut, progression, modèle, volumétrie)
- [x] Formulaire « Nouveau lot » : upload MDTC + Mopinion (l'un ou l'autre), label, seuil de revue
- [x] Lancement -> création du lot via l'API -> traitement asynchrone
- [x] Suivi : barre de progression (polling) jusqu'à « terminé », puis résumé du lot
- [x] Diagnostic clair en cas d'échec (message d'erreur du lot affiché)
- [x] Navigation : lien « Lots » dans l'en-tête + raccourci sur l'accueil

**Validation** : front **type-check TS strict + build Vite OK**. Endpoints back-end couverts par le test E2E L2 (14/14).
**Reste pour clore L2+L3** : rebuild sur le poste, puis dans l'UI : Lots → Nouveau lot → déposer `data/raw/mdtc_poc.xlsx` (et/ou mopinion) → suivre la progression → voir le résumé (mode stub).

## L4 — Consultation résultats + exports ⬜
## L5 — Revue humaine & corrections ⬜
## L6 — Tableaux de bord & KPI ⬜
## L7 — Historique, audit, config & rétention ⬜
## L8 — Durcissement, RGPD, perf, recette V1 ⬜

---

## Journal de décisions (ADR-lite)

| # | Date | Décision | Justification |
|---|---|---|---|
| D1 | 2026-06-17 | Stack V1 : FastAPI + React/TS + worker RQ + PostgreSQL + Redis, conteneurisée | Choix PO ; archi découplée portable vers un serveur ultérieurement |
| D2 | 2026-06-17 | PostgreSQL **100 % local** (aucun port exposé hors localhost) | Contrainte RGPD « no data egress » |
| D3 | 2026-06-17 | Nom de l'app : « Observatoire Ecom Studio » | Choix PO |
| D4 | 2026-06-17 | Dév. par Claude Code (agent unique) ; **pas de backlog formel**, suivi léger + commits par lot + portes de validation | Pas d'équipe humaine à coordonner ; valeur = continuité inter-sessions + visibilité PO + DoD |
| D5 | 2026-06-17 | Service `web` = nginx multi-stage (build React + sert le statique + proxy `/api`) au lieu de 2 services proxy+frontend | Moins de conteneurs sur un laptop, même résultat |
| D6 | 2026-06-17 | `api` reste **léger (sans torch)** ; tout le ML est dans le `worker` | Démarrage rapide de l'API, séparation des responsabilités, image API petite |
| D7 | 2026-06-17 | Package partagé `common` (DB + modèles ORM) + classifieur **stub** activé tant qu'aucun modèle réel n'est déposé | `api` et `worker` partagent le schéma sans duplication ; l'app est démontrable avant l'entraînement CamemBERT |
