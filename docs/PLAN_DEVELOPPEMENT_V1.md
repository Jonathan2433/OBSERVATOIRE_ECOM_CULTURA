# Plan de développement V1 — « Observatoire Ecom Studio »

> Découpage en **lots** de la V1 décrite dans [CAHIER_DES_CHARGES.md](CAHIER_DES_CHARGES.md).
> Objectif : livrer un incrément utilisable au plus tôt, en traitant le risque technique (cœur ML + asynchrone) en priorité.

| | |
|---|---|
| **Version** | 0.1 (à valider) |
| **Date** | 2026-06-17 |
| **Cible** | Mono-poste, Docker Desktop, macOS Apple Silicon (linux/arm64) |
| **Décisions** | **PostgreSQL** (100 % local) ; **test à la volée incluse** (L4) ; **développement par Claude Code (agent unique)** ; nom **« Observatoire Ecom Studio »** |

---

## 1. Vue d'ensemble des lots

| Lot | Intitulé | Exigences CdC | Taille | Dépend de |
|---|---|---|---|---|
| **L0** | Socle projet & conteneurisation | §7 (archi, conteneurs) | M (~3-5 j) | — |
| **L1** | Authentification, comptes & rôles | F1, §7.9 | M (~3-4 j) | L0 |
| **L2** | Cœur ML : worker async + gestion modèle | F3, F9, §7.2/7.3 | **L (~5-8 j)** | L0 |
| **L3** | Ingestion & lancement de lot + suivi | F2, F3 (UI) | M (~3-4 j) | L1, L2 |
| **L4** | Consultation des résultats + exports | F4, F7 | M (~4-5 j) | L3 |
| **L5** | Revue humaine & corrections | F5 | M (~3-5 j) | L4 |
| **L6** | Tableaux de bord & KPI | F6, §6 | M-L (~4-6 j) | L4 |
| **L7** | Historique, audit, config & rétention | F8, F10, §7.10 | M (~3-5 j) | L1, L4 |
| **L8** | Durcissement, RGPD, perf, recette V1 | §7.9/7.10, §10, §11 | M (~3-5 j) | tous |

**Charge indicative totale : ~31–47 j·homme** (≈ 6–9 semaines à 1 dev ; ~2x plus rapide à 2 devs grâce au parallélisme L5/L6/L7).

---

## 2. Jalons (milestones)

- **M1 — Squelette qui tourne** (fin L0) : `docker compose up` lève une stack vide qui répond (`/health`, page d'accueil).
- **M2 — Cœur prouvé** (fin L2) : un job asynchrone traite un Excel et écrit les résultats en base, avec version de modèle tracée. *Risque technique principal levé.*
- **M3 — MVP interne utilisable** (fin L4) : un analyste se connecte, charge les 2 Excel, lance le lot, consulte et exporte les résultats. **Bout-en-bout exploitable.**
- **M4 — V1 fonctionnelle** (fin L6) : + revue humaine + dashboards.
- **M5 — V1 livrable** (fin L8) : durcie, conforme RGPD, recettée (§11), documentée.

---

## 3. Chemin critique & parallélisation

```
L0 ──► L1 ──┐
            ├─► L3 ──► L4 ──┬─► L5 ─┐
L0 ──► L2 ──┘               ├─► L6 ─┼─► L8 (recette)
                            └─► L7 ─┘
```
- **Chemin critique** : L0 → L2 → L3 → L4 → (L5/L6/L7 en parallèle) → L8.
- **Parallélisable** : L1 ∥ L2 dès que L0 est fini ; L5, L6, L7 ∥ après L4.

---

## 4. Détail des lots

### L0 — Socle projet & conteneurisation
**Objectif** : poser les fondations techniques et lever tôt le risque Docker/arm64.
**Contenu**
- Arborescence `app/` (backend `api/`, `worker/`, frontend `web/`) à côté du moteur POC réutilisé (`src/`).
- `docker-compose.yml` : services `proxy` (nginx), `frontend`, `api`, `worker`, `db` (Postgres), `redis` ; volumes `pgdata`, `models` (RO), `uploads`, `outputs`, `logs` ; `.env.example`.
- Squelette FastAPI (`/health`, config, logging structuré) + squelette React/TS (Vite) + reverse-proxy.
- Base de données : connexion + migrations Alembic initiales (schéma vide) ; packaging du moteur `src/` importable par `api`/`worker`.
- Images **linux/arm64**.
**Livrable** : `docker compose up` → page d'accueil + `/health` OK sur tous les services.
**Critères d'acceptation** : stack reproductible, aucun accès réseau sortant requis au runtime, healthchecks verts.
**Risques** : wheels torch/onnxruntime arm64 dans l'image worker → valider dès ce lot (build de l'image worker).

### L1 — Authentification, comptes & rôles (F1)
**Objectif** : sécuriser l'accès, poser le RBAC.
**Contenu** : modèle `users` ; hachage argon2/bcrypt ; login/logout/session (cookie httpOnly) ; middleware RBAC (Analyste/Admin) côté API ; écrans connexion + gestion des comptes (admin) ; compte admin initial (seed) ; anti-bruteforce.
**Livrable** : connexion fonctionnelle, droits appliqués **côté API** (pas seulement UI).
**Critères** : un non-authentifié n'accède à rien (hors `/login`, `/health`) ; un Analyste n'accède pas aux écrans admin.

### L2 — Cœur ML : worker asynchrone + gestion du modèle (F3, F9) — *lot pivot*
**Objectif** : industrialiser le moteur du POC en traitement asynchrone tracé.
**Contenu**
- File **Redis + RQ** ; service `worker` chargeant les modèles une fois (à chaud).
- Réutilisation de `batch_processor`/`predictor` du POC ; pipeline anonymisation → nettoyage → inférence.
- Modèle de données `batches` + `results` (texte **anonymisé** uniquement) ; écriture de la progression (n traités/total) ; gestion d'erreur **par verbatim**.
- `model_versions` : découverte des versions dans le volume `data/models` (pointeur `CURRENT`, cartes, métriques) ; activation de la version courante ; traçabilité lot ↔ version.
- Endpoints `POST /api/batches`, `GET /api/batches/{id}` (statut/progression).
**Livrable** : via API, un job traite un petit Excel et persiste les résultats + la version de modèle.
**Critères** : un verbatim défaillant n'arrête pas le lot ; un seul job lourd concurrent ; progression lisible ; aucun verbatim non anonymisé en base.
**Risques** : mémoire (modèles + Postgres) → garder le worker chaud, `batch_size` configurable ; valider ONNX int8 ici.

### L3 — Ingestion & lancement de lot + suivi (F2, F3 UI)
**Objectif** : permettre au métier de charger et lancer.
**Contenu** : upload des 2 Excel (glisser-déposer) ; validation des **colonnes obligatoires** par source ; création + lancement du lot (seuil de revue paramétrable, défaut 0,70) ; écran de suivi (statut, barre de progression, durée) ; notification de fin.
**Livrable** : upload via UI → job → progression jusqu'à « terminé ».
**Critères** : fichier au mauvais schéma refusé avec diagnostic clair ; fichiers d'origine jamais modifiés.

### L4 — Consultation des résultats + exports (F4, F7) — *fin MVP (M3)*
**Objectif** : exploiter les résultats.
**Contenu** : tableau paginé, **filtrable** (thème, sentiment, signaux, statut revue, confiance) et triable ; vue détail d'un verbatim (texte anonymisé, thèmes+scores, sentiment, signaux, confiance, colonnes d'origine) ; exports **CSV/XLSX conformes au format POC** ; *(optionnel)* « test à la volée » d'un verbatim unique.
**Livrable** : voir, filtrer et exporter les résultats d'un lot.
**Critères** : recherche/filtre < 2 s sur 11k ; CSV ré-ouvrable dans Excel FR sans casse d'accents, colonnes exactes.

### L5 — Revue humaine & corrections (F5)
**Objectif** : boucle qualité humaine.
**Contenu** : file de revue (verbatims sous le seuil, tri par confiance croissante) ; correction niv.1/niv.2 **contrainte par la taxonomie**, sentiment, signaux ; `corrections` historisées (qui/quand/ancienne→nouvelle) ; marquage « corrigé » ; export du jeu **corrections validées** pour ré-entraînement CLI.
**Livrable** : corriger un verbatim, tracé ; export des corrections.
**Critères** : impossible de choisir un niv.2 hors de son niv.1 ; KPI et exports reflètent la correction ; origine conservée.

### L6 — Tableaux de bord & KPI (F6, §6)
**Objectif** : pilotage.
**Contenu** : **KPI modèle** (depuis `eval_report.json` de la version active, alerte sous seuils cibles) ; **KPI résultats du lot** (distributions thèmes/sentiments/signaux, taux de revue, durée) ; **volumétrie & tendances** (évolution mensuelle, top thèmes vs M-1, pics de signaux) ; graphiques.
**Livrable** : 3 dashboards.
**Critères** : chargement < 3 s ; version de modèle et période affichées.

### L7 — Historique, audit, configuration & rétention (F8, F10, §7.10)
**Objectif** : traçabilité, administration, conformité RGPD.
**Contenu** : liste/historique des lots ; **journal d'audit** (connexions, lancements, corrections, activations, purges, config) ; écran de configuration admin (seuils, `batch_size`, rétention, taille max fichier) ; **purge** automatique planifiée (rétention défaut 13 mois) + purge manuelle.
**Livrable** : historique + audit + config + purge.
**Critères** : modif de seuil de revue appliquée aux **nouveaux** lots seulement ; toute action sensible tracée ; purge respecte la rétention.

### L8 — Durcissement, RGPD, performance & recette V1 (§7.9/7.10, §10, §11)
**Objectif** : rendre la V1 livrable.
**Contenu** : sécurité (binding **localhost**, secrets hors dépôt, CORS verrouillé, anti-bruteforce) ; vérification **offline strict** (aucun appel sortant) ; perf (ONNX int8, lot 11k **< ~1 h**) ; **vérification des 12 garde-fous §10** ; procédure de sauvegarde/restauration des volumes ; documentation utilisateur + admin ; **recette des critères §11**.
**Livrable** : V1 recettée et documentée.
**Critères** : tous les items de la Definition of Done (§11) cochés.

---

## 5. Traçabilité exigences → lots

| Exigence CdC | Lot(s) |
|---|---|
| F1 Auth & comptes | L1 |
| F2 Ingestion & validation | L3 |
| F3 Traitement async & suivi | L2 (moteur) + L3 (UI) |
| F4 Consultation résultats | L4 |
| F5 Revue & corrections | L5 |
| F6 Dashboards & KPI | L6 |
| F7 Exports | L4 |
| F8 Historique & audit | L7 |
| F9 Gestion des versions de modèle | L2 |
| F10 Administration & config | L7 |
| §7.10 RGPD / rétention / purge | L2 (anonymisation en base) + L7 (purge) + L8 (vérif) |
| §10 Garde-fous | transverse, vérifiés en L8 |
| §11 Recette V1 | L8 |

---

## 6. Risques de planning & mitigations

| Risque | Lot | Mitigation |
|---|---|---|
| Image worker arm64 (torch/onnx) instable | L0/L2 | Construire et tester l'image worker dès L0 ; figer les versions (cf. `requirements.txt`). |
| Perf 11k < 1 h non atteinte | L2/L8 | ONNX int8 dès L2 ; `batch_size` configurable ; mesurer tôt sur volume réel. |
| Dérive de périmètre sur les dashboards | L6 | KPI figés au §6 ; tout ajout = backlog V1.1. |
| Mono-poste / sauvegardes | L8 | Procédure de backup des volumes documentée et testée. |

---

## 7. Définition de « prêt » et « terminé »
- **Prêt (Ready)** pour un lot : exigences du CdC référencées, critères d'acceptation écrits, dépendances livrées.
- **Terminé (Done)** pour un lot : critères d'acceptation validés, testé dans la stack Docker, pas de régression sur les garde-fous §10, documentation à jour.

---

## 8. Décisions validées
1. **PostgreSQL** confirmé, 100 % local. ✓
2. « **Test à la volée** » **inclus** en V1 (L4, plus optionnel). ✓
3. **Développement assuré par Claude Code (agent unique)** — pas de dépendance à une équipe humaine ; les « tailles » servent de repère de complexité, pas de calendrier RH. ✓
4. Nom : « **Observatoire Ecom Studio** ». ✓

> Les estimations en « j·homme » deviennent un simple **indicateur de complexité relative** : l'exécution se fait par lot, avec une **validation à chaque jalon** par le responsable (product owner).
