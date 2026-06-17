# Suivi d'avancement — V1 « Observatoire Ecom Studio »

> Tableau de bord vivant du développement par lots. Mis à jour à chaque fin de lot.
> Réf. : [CAHIER_DES_CHARGES.md](CAHIER_DES_CHARGES.md) · [PLAN_DEVELOPPEMENT_V1.md](PLAN_DEVELOPPEMENT_V1.md)
>
> Cadence : **1 lot = 1 branche git = 1 incrément relisable**, puis **validation du PO** avant le lot suivant.
> Légende statut : ⬜ À faire · 🟦 En cours · ✅ Fait (validé PO) · ⏸️ En attente de validation

| Lot | Intitulé | Statut | Branche |
|---|---|---|---|
| L0 | Socle projet & conteneurisation | 🟦 En cours | `lot/0-socle-conteneurisation` |
| L1 | Auth, comptes & rôles | ⬜ | — |
| L2 | Cœur ML : worker async + gestion modèle | ⬜ | — |
| L3 | Ingestion & lancement de lot + suivi | ⬜ | — |
| L4 | Consultation résultats + exports (→ MVP) | ⬜ | — |
| L5 | Revue humaine & corrections | ⬜ | — |
| L6 | Tableaux de bord & KPI | ⬜ | — |
| L7 | Historique, audit, config & rétention | ⬜ | — |
| L8 | Durcissement, RGPD, perf, recette V1 | ⬜ | — |

---

## L0 — Socle projet & conteneurisation 🟦

**Objectif** : fondations techniques + lever le risque image worker arm64 (torch/onnx).

Critères d'acceptation :
- [ ] Arborescence `app/` (api / worker / web) + moteur `src/` réutilisable
- [ ] `docker-compose.yml` (web, api, worker, db Postgres, redis) + `.env.example`
- [ ] `docker compose config` valide (syntaxe)
- [ ] API FastAPI : `/health` + config + logging structuré
- [ ] Squelette web React/TS (Vite) appelant `/api/health`
- [ ] Worker RQ qui démarre et se connecte à Redis
- [ ] Base Postgres + Alembic configuré (migration baseline)
- [ ] Images **linux/arm64**, aucun accès réseau sortant au runtime
- [ ] `docker compose up` → page d'accueil + `/health` OK *(à exécuter sur le poste, daemon requis)*

---

## L1 — Auth, comptes & rôles ⬜
Critères : voir [PLAN §4 / L1](PLAN_DEVELOPPEMENT_V1.md). (détaillé à l'ouverture du lot)

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
