# Suivi d'avancement — V1 « Observatoire Ecom Studio »

> Tableau de bord vivant du développement par lots. Mis à jour à chaque fin de lot.
> Réf. : [CAHIER_DES_CHARGES.md](CAHIER_DES_CHARGES.md) · [PLAN_DEVELOPPEMENT_V1.md](PLAN_DEVELOPPEMENT_V1.md)
>
> Cadence : **1 lot = 1 branche git = 1 incrément relisable**, puis **validation du PO** avant le lot suivant.
> Légende statut : ⬜ À faire · 🟦 En cours · ✅ Fait (validé PO) · ⏸️ En attente de validation

| Lot | Intitulé | Statut | Branche |
|---|---|---|---|
| L0 | Socle projet & conteneurisation | ✅ Fait (validé PO) | `lot/0` (mergé) |
| L1 | Auth, comptes & rôles | ⏸️ En attente de validation | `lot/1-auth` |
| L2 | Cœur ML : worker async + gestion modèle | ⬜ | — |
| L3 | Ingestion & lancement de lot + suivi | ⬜ | — |
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

## L1 — Auth, comptes & rôles ⏸️

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

## L2 — Cœur ML : worker async + gestion modèle ⬜
## L3 — Ingestion & lancement de lot + suivi ⬜
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
