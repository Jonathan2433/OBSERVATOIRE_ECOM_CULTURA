# Cahier des charges — Application « Observatoire Ecom Studio »

> Application interne de classification et de pilotage des verbatims clients e-commerce Cultura.
> Document technique **et** fonctionnel — base contractuelle du développement de la V1.

| | |
|---|---|
| **Version du document** | 0.1 (à valider) |
| **Date** | 2026-06-17 |
| **Auteur** | Équipe Data IA |
| **Statut** | Brouillon pour validation |
| **Socle technique** | POC `cultura-verbatim-classifier/` (pipeline CamemBERT déjà livré et validé) |

---

## 1. Contexte & objectifs

### 1.1 Contexte
L'équipe E-Commerce de Cultura analyse chaque mois ~11 000 verbatims clients (sources **MDTC** et **Mopinion**) pour prioriser les actions sur cultura.com. Un POC ML (CamemBERT, local, CPU, hors ligne) a été livré : il classe chaque verbatim (thème hiérarchique niv.1/niv.2, sentiment, signaux rupture/churn/insatisfaction) et route les cas incertains vers une revue humaine. Ce POC s'utilise aujourd'hui **en ligne de commande** — non exploitable par le métier ni transférable simplement.

### 1.2 Objectif
Transformer le POC en **application conteneurisée, utilisable par le métier**, permettant de : charger les nouvelles données, lancer la classification, consulter et corriger les résultats, et piloter via des tableaux de bord (KPI modèle, KPI résultats, volumétrie). L'entraînement du modèle reste une tâche data-science **hors application** (CLI).

### 1.3 Bénéfices attendus
- Diviser le temps d'analyse mensuel (de jours de lecture manuelle à un traitement automatisé + revue ciblée).
- Standardiser et tracer la classification (référentiel unique, historique, audit).
- Donner au métier une **autonomie** (plus besoin de la data science pour le run mensuel).
- Préserver la conformité RGPD (anonymisation, données qui ne quittent jamais le poste).

---

## 2. Périmètre

### 2.1 Dans le périmètre (V1)
1. Authentification par comptes locaux + rôles (Analyste / Admin).
2. Upload manuel des 2 fichiers Excel (MDTC + Mopinion) avec validation des colonnes.
3. Traitement par lots **asynchrone** (file de jobs, progression, notification de fin).
4. Consultation des résultats (tableau filtrable/triable, détail d'un verbatim).
5. **Revue humaine active** : correction dans l'UI des verbatims sous le seuil de confiance ; corrections historisées et exportables pour ré-entraînement.
6. Tableaux de bord : KPI modèle, KPI résultats du lot, volumétrie et tendances.
7. Exports (CSV/XLSX enrichi + fichier de revue + jeu de corrections).
8. Historique des traitements et **traçabilité** (audit).
9. Gestion des versions de modèle via le dossier `data/models` **monté en volume** (sélection/activation de la version courante).
10. Administration : gestion des comptes, configuration (seuils, rétention).
11. Rétention configurable (défaut **13 mois**) avec purge automatique.

### 2.2 Hors périmètre V1 (phases ultérieures)
- Ré-entraînement déclenché depuis l'UI (cycle MLOps complet) → **V2**.
- Connecteurs API automatiques (Mopinion API, export MDTC) → **V1.1**.
- SSO entreprise (Azure AD / Entra ID), déploiement serveur multi-utilisateur → **V1.1**.
- Détection de dérive du modèle (drift), A/B de versions → **V2**.
- Multi-langue (l'app est **en français** uniquement).

---

## 3. Acteurs & rôles

| Acteur | Type | Description |
|---|---|---|
| **Analyste** | Utilisateur app | Métier E-Commerce. Charge les données, lance les traitements, consulte, fait la revue/corrections, exporte. |
| **Admin** | Utilisateur app | Gère les comptes, la configuration (seuils, rétention), active la version de modèle, purge. Possède aussi tous les droits Analyste. |
| **Data Scientist** | Externe à l'app | Entraîne/évalue le modèle en **CLI** (hors app) et dépose les artefacts dans `data/models`. N'a pas besoin de l'app pour son travail. |

### 3.1 Matrice des droits (permissions)

| Fonction | Analyste | Admin |
|---|:---:|:---:|
| Se connecter | ✓ | ✓ |
| Upload + lancer un lot | ✓ | ✓ |
| Consulter résultats & KPI | ✓ | ✓ |
| Revue / corriger un verbatim | ✓ | ✓ |
| Exporter (résultats, revue, corrections) | ✓ | ✓ |
| Annuler / supprimer un lot | ✓ (ses lots) | ✓ (tous) |
| Gérer les comptes utilisateurs | ✗ | ✓ |
| Modifier la configuration (seuils, rétention) | ✗ | ✓ |
| Activer une version de modèle | ✗ | ✓ |
| Purger des données / lancer la rétention | ✗ | ✓ |
| Consulter le journal d'audit | ✗ | ✓ |

---

## 4. Exigences fonctionnelles

> Notation : **RG** = règle de gestion, **CA** = critère d'acceptation.

### F1 — Authentification & comptes
- Connexion par identifiant + mot de passe ; déconnexion ; session expirante.
- RG : mots de passe stockés **hachés** (argon2/bcrypt), jamais en clair ; politique minimale (longueur ≥ 12).
- RG : verrouillage temporaire après N échecs ; pas d'énumération de comptes.
- Admin : créer/désactiver un compte, réinitialiser un mot de passe, assigner un rôle.
- CA : un utilisateur sans session valide ne peut accéder à aucune donnée ni endpoint (hors /login, /health).

### F2 — Ingestion & validation des fichiers
- Upload des fichiers **MDTC** et **Mopinion** (.xlsx) par glisser-déposer ; l'un ou l'autre peut être fourni seul.
- RG : validation des **colonnes obligatoires** par source avant traitement ; message d'erreur explicite si manquantes.
- RG : taille de fichier max paramétrable (défaut 50 Mo) ; formats acceptés .xlsx uniquement (V1).
- RG : les fichiers d'origine ne sont **jamais modifiés** ; ils sont stockés dans un volume sécurisé soumis à rétention.
- CA : un fichier au mauvais schéma est refusé avec un diagnostic ; un fichier valide crée un lot en statut « en attente ».

### F3 — Traitement par lots (asynchrone)
- Le lancement d'un lot crée un **job** traité en arrière-plan par un worker ; l'UI n'est jamais bloquée.
- Affichage : statut (en attente / en cours / terminé / échec / annulé), **progression** (n traités / total) et durée.
- RG : gestion des erreurs **par verbatim** (un verbatim défaillant n'interrompt pas le lot) ; comptage des erreurs.
- RG : pipeline = anonymisation PII → nettoyage → inférence (réutilise le moteur du POC) ; seuil de revue paramétrable au lancement (défaut 0,70).
- RG : un seul job lourd à la fois par défaut (poste mono-machine) ; les autres sont mis en file.
- CA : un lot de ~11 000 verbatims se traite **en moins d'~1 h** sur le laptop cible, avec progression visible et reprise propre en cas de relance.

### F4 — Consultation des résultats
- Tableau paginé, **filtrable** (thème niv.1/niv.2, sentiment, signaux, statut revue, confiance) et triable.
- Détail d'un verbatim : texte **analysé (anonymisé)**, thèmes + scores, sentiment, signaux, confiance globale, statut (auto / corrigé / en revue), colonnes d'origine.
- RG : affichage systématique du **score de confiance** et de la mention « prédiction automatique » tant qu'elle n'est pas validée.
- CA : on retrouve un verbatim par filtre combiné en < 2 s sur un lot de 11k.

### F5 — Revue humaine (HITL) & corrections
- File de revue = verbatims `revue_humaine_requise = vrai`, triés par confiance croissante.
- L'analyste peut **corriger** : thème niv.1, niv.2 (contraint à la taxonomie), sentiment, signaux ; valider ou écarter.
- RG : la correction respecte la **contrainte hiérarchique** (un niv.2 n'est sélectionnable que sous son niv.1).
- RG : chaque correction est **historisée** (qui, quand, ancienne/nouvelle valeur) et le résultat est marqué « corrigé ».
- RG : les corrections constituent un jeu « **corrections validées** » exportable, fusionnable à l'historique pour le prochain ré-entraînement CLI.
- CA : après correction, le tableau, les KPI et les exports reflètent la valeur corrigée ; l'historique conserve l'origine.

### F6 — Tableaux de bord & KPI (cf. §6 pour le détail)
- Trois familles : **KPI modèle**, **KPI résultats du lot**, **volumétrie & tendances**.
- RG : les KPI modèle proviennent du rapport d'évaluation de la **version active** (`eval_report.json`) ; les KPI résultats/volumétrie sont calculés sur les lots traités.
- CA : chaque dashboard se charge en < 3 s et indique la version de modèle et la période concernées.

### F7 — Exports
- Export du **CSV enrichi** (toutes colonnes d'origine + colonnes du modèle, format identique au POC) et en **XLSX**.
- Export du **fichier de revue** (cas incertains) et du jeu de **corrections validées**.
- RG : encodage UTF-8 (BOM) pour ouverture Excel FR ; le nom de fichier reprend le libellé du lot.
- CA : le CSV exporté est ré-ouvrable dans Excel sans casse d'accents et contient exactement les colonnes attendues.

### F8 — Historique & traçabilité
- Liste des lots (date, auteur, source, volumétrie, taux de revue, durée, version de modèle, statut).
- **Journal d'audit** (admin) : connexions, lancements, corrections, activations de modèle, purges, modifications de configuration.
- CA : toute action sensible est tracée avec utilisateur + horodatage.

### F9 — Gestion des versions de modèle
- L'app **lit** les versions présentes dans le volume `data/models` (pointeurs `CURRENT`, cartes de version, métriques).
- L'admin **sélectionne/active** la version courante utilisée pour les nouveaux lots.
- RG : le volume modèles est monté en **lecture seule** ; l'app ne modifie jamais les poids.
- RG : chaque lot enregistre la **version de modèle** utilisée (traçabilité résultats ↔ modèle).
- CA : déposer une nouvelle version dans le volume puis l'activer dans l'UI suffit à l'utiliser, sans rebuild.

### F10 — Administration & configuration
- Paramètres : seuils (revue, niv.1/niv.2, signaux), `batch_size`, durée de rétention, taille max de fichier.
- Déclenchement manuel de la purge ; planification de la purge automatique (rétention).
- CA : une modification de seuil de revue s'applique aux **nouveaux** lots (les lots passés restent inchangés et tracés avec leurs paramètres d'origine).

### 4.1 User stories clés
- *En tant qu'analyste, je dépose les 2 Excel du mois et lance le traitement, puis je vais prendre un café pendant que le lot tourne, et je suis notifié à la fin.*
- *En tant qu'analyste, je filtre les verbatims « rupture client » pour les traiter en priorité.*
- *En tant qu'analyste, je corrige un thème mal prédit ; ma correction est tracée et servira à améliorer le modèle.*
- *En tant qu'admin, je dépose la nouvelle version de modèle trimestrielle et je l'active en un clic.*
- *En tant qu'admin, je vérifie que les KPI du modèle restent au-dessus des seuils cibles avant de communiquer les résultats.*

---

## 5. Parcours utilisateur type (run mensuel)

```
1. Analyste se connecte
2. → Nouveau lot : dépose mdtc_juillet.xlsx + mopinion_juillet.xlsx
3. → App valide les colonnes → crée le lot (seuil revue 0,70 par défaut)
4. → Lancement : job asynchrone (anonymisation → nettoyage → inférence) + progression
5. → Notification de fin : 11 247 traités, 8,3 % en revue
6. → Dashboard du lot : top thèmes, sentiments, signaux, volumétrie vs mois précédent
7. → File de revue : 934 verbatims, l'analyste corrige les plus incertains
8. → Export du CSV enrichi + du fichier de revue
9. → (trimestriel) Admin dépose une nouvelle version de modèle et l'active
```

---

## 6. KPI & indicateurs

### 6.1 KPI Modèle (version active, issus de l'évaluation)
- F1-macro niv.1, F1-micro, F1-weighted ; F1 par thème (tableau trié).
- F1-macro niv.2 et accuracy à niv.1 connu ; précision hiérarchique.
- Accuracy + F1 par classe du sentiment.
- Signaux : précision / rappel / F1 / AUC (rappel rupture mis en avant).
- Matrice de confusion niv.1 (heatmap).
- Comparaison aux **seuils cibles** (alerte visuelle si en dessous : F1-niv1 ≥ 0,70, etc.).

### 6.2 KPI Résultats du lot
- Volume traité, % en revue humaine, % d'erreurs, durée, vitesse (s/verbatim).
- Distribution des thèmes niv.1 (top 5 + complet), des sous-thèmes, des sentiments.
- Comptage des signaux : rupture / churn / insatisfaction (n et %).
- Répartition par source (MDTC / Mopinion) et par score de satisfaction.
- Nombre de corrections effectuées (taux de correction).

### 6.3 Volumétrie & tendances
- Évolution mensuelle du volume et du taux de revue.
- Tendance des top thèmes (mois courant vs M-1, vs N mois).
- Évolution des signaux (alerte si pic de rupture/churn).
- Évolution de la part de chaque sentiment.

### 6.4 KPI opérationnels
- Nombre de lots traités, durée moyenne, taux d'échec des jobs.
- Espace disque occupé, prochaine échéance de purge.

---

## 7. Exigences techniques

### 7.1 Architecture cible (mono-poste, Docker Desktop)

```
                         Laptop macOS Apple Silicon — Docker Desktop (linux/arm64)
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  navigateur (localhost)                                                    │
  │        │                                                                   │
  │        ▼                                                                   │
  │  [reverse-proxy nginx]  ── sert le build React + proxy /api ──┐            │
  │        │                                                      │            │
  │        ▼                                                      ▼            │
  │  [frontend React/TS]                               [api FastAPI/uvicorn]   │
  │   (statique, build Vite)                              │   │   │            │
  │                                                       │   │   └──▶ [db Postgres]
  │                                            enqueue job │   │        (volume pgdata)
  │                                                       ▼   ▼                │
  │                                              [redis] ◀─ [worker RQ]        │
  │                                                          │  réutilise le   │
  │                                                          │  moteur ML POC  │
  │                                                          ▼                 │
  │                                   volumes:  models (RO)  uploads  outputs  │
  └──────────────────────────────────────────────────────────────────────────┘
                         Aucun trafic réseau sortant (offline strict)
```

### 7.2 Composants & responsabilités
| Service | Rôle | Image / techno |
|---|---|---|
| `proxy` | Sert le front statique + reverse-proxy `/api` | nginx |
| `frontend` | UI métier (build statique) | React + TypeScript + Vite |
| `api` | API REST, auth, RBAC, orchestration des jobs, lecture/écriture DB | FastAPI / uvicorn (Python 3.11) |
| `worker` | Exécute les jobs lourds (pipeline ML du POC) | Python 3.11 + `src/` du POC + torch/onnx |
| `redis` | Broker de la file de jobs | redis |
| `db` | Persistance (utilisateurs, lots, résultats, corrections, audit, config) | PostgreSQL |

> Réutilisation maximale du POC : `api`/`worker` importent le package `src/` existant (preprocessing, predictor, batch_processor, exporter) — pas de réécriture du moteur.

### 7.3 Traitement asynchrone
- File de jobs **Redis + RQ** (léger, adapté mono-poste) ; un worker dédié.
- Le `worker` charge les modèles **une fois** (au démarrage / au 1er job) et reste chaud.
- Progression écrite en base (n traités/total) et exposée via `GET /batches/{id}`.
- RG : un seul job lourd concurrent (limite ressources laptop) ; annulation possible.

### 7.4 Modèle de données (entités principales)
- `users` (id, username, password_hash, role, active, created_at)
- `batches` (id, label, statut, created_by, dates, model_version, seuil_revue, n_total, n_processed, n_review, n_errors, duration_s, source_files)
- `results` (id, batch_id, row_index, source, **verbatim_analyse (anonymisé)**, nb_themes, theme1_niv1/niv2/sentiment/score, theme2_*, signaux, confidence_globale, revue_humaine_requise, corrected, original_columns (jsonb))
- `corrections` (id, result_id, user_id, champ, ancienne_valeur, nouvelle_valeur, created_at)
- `model_versions` (id, version, path, metrics (jsonb), active, registered_at)
- `audit_log` (id, user_id, action, entity, entity_id, timestamp, details)
- `app_config` (clé, valeur) — seuils, rétention, taille max…

> **Règle RGPD forte** : la base ne stocke que le texte **anonymisé** (`verbatim_analyse`). Le texte brut (potentiellement porteur de PII) ne vit que dans le fichier source du volume `uploads`, soumis à purge.

### 7.5 API (principaux endpoints)
- `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`
- `GET/POST/PATCH/DELETE /api/users` (admin)
- `POST /api/batches` (upload + params), `GET /api/batches`, `GET /api/batches/{id}`, `DELETE /api/batches/{id}`
- `GET /api/batches/{id}/results` (filtres, pagination), `GET /api/batches/{id}/export?format=csv|xlsx`
- `GET /api/review?batch_id=...`, `PATCH /api/results/{id}` (correction), `GET /api/corrections/export`
- `GET /api/kpi/model`, `GET /api/kpi/batch/{id}`, `GET /api/kpi/volumetry?from=&to=`
- `GET /api/models`, `POST /api/models/{id}/activate` (admin)
- `GET/PATCH /api/config` (admin), `POST /api/admin/purge` (admin)
- `GET /health` (sans auth)

### 7.6 Stack & versions cibles
- Backend : Python 3.11, FastAPI, SQLAlchemy/Alembic, RQ, pydantic.
- Frontend : React 18 + TypeScript, Vite, une lib de composants (ex. MUI), une lib de graphiques (ex. Recharts).
- Données : PostgreSQL 16, Redis 7.
- ML : le socle du POC (torch, transformers, optimum/onnxruntime, scikit-learn, spaCy) — **ONNX int8** privilégié à l'inférence.

### 7.7 Conteneurisation & déploiement
- `docker compose up` lance toute la stack ; un `.env` fournit les secrets (clé de session, mot de passe DB).
- Images **linux/arm64** (Apple Silicon).
- Volumes : `pgdata` (DB), `models` (monté depuis `./data/models`, **lecture seule**), `uploads`, `outputs`, `logs`.
- Front exposé sur `http://localhost:<port>` ; rien d'autre n'est exposé.

### 7.8 Performance & dimensionnement
- Cible : lot ~11 000 verbatims **< ~1 h** (ONNX int8, `batch_size` ajustable).
- Recommandé : laptop **≥ 16 Go RAM, ≥ 4 cœurs** ; allouer suffisamment de RAM/CPU à Docker Desktop (ex. 8 Go / 4 cœurs).
- Le `worker` garde les modèles chargés ; un seul job lourd à la fois.

### 7.9 Sécurité
- Hachage des mots de passe (argon2/bcrypt) ; sessions via cookie httpOnly / JWT court.
- RBAC appliqué côté API (pas seulement côté UI).
- CORS verrouillé sur l'origine locale ; binding **localhost uniquement**.
- Secrets hors dépôt (`.env`, non commité) ; limitation des tentatives de connexion.

### 7.10 Confidentialité & RGPD
- Anonymisation PII **avant** stockage et inférence (e-mails, téléphones, n° commande, noms).
- Base **sans PII** (texte anonymisé seulement) ; fichiers bruts purgés selon rétention.
- Rétention configurable (défaut **13 mois**), purge automatique planifiée + purge manuelle (admin).
- Aucun appel réseau sortant (offline strict) ; aucune télémétrie.
- Journal d'audit ; droit à l'effacement via purge ciblée.

### 7.11 Observabilité & exploitation
- Logs structurés par service ; `GET /health` par service ; statut visible dans l'UI admin.
- Sauvegarde : dump périodique de `pgdata` + copie du volume `outputs` (procédure documentée).

---

## 8. Exigences non-fonctionnelles

| Catégorie | Exigence |
|---|---|
| Performance | Lot 11k < ~1 h ; UI < 3 s par écran ; recherche/filtre < 2 s |
| Disponibilité | Usage mono-poste ; redémarrage propre via `docker compose` ; reprise des jobs interrompus marqués « échec » |
| Utilisabilité | Interface FR, sobre, parcours en ≤ 3 clics pour lancer un lot ; messages d'erreur explicites |
| Portabilité | 100 % conteneurisé ; déployable tel quel sur un serveur interne ultérieurement (sans refonte) |
| Maintenabilité | Code typé, tests, séparation api/worker/front ; moteur ML réutilisé du POC |
| Sécurité | Cf. §7.9 ; principe du moindre privilège |
| Conformité | Cf. §7.10 (RGPD) |
| Internationalisation | Français uniquement (V1) |

---

## 9. Contraintes & hypothèses

**Contraintes**
- Mono-poste (laptop), CPU uniquement, **hors ligne** après installation.
- 2 sources Excel aux schémas distincts ; volume ~11k/mois.
- Le modèle est produit hors app (CLI) et déposé dans `data/models`.

**Hypothèses (à valider)**
- Base de données **PostgreSQL** conteneurisée (alternative SQLite écartée pour la robustesse/concurrence).
- Une fonction « test à la volée » (saisir un verbatim et voir la prédiction) est incluse comme outil de démonstration/diagnostic.
- Laptop ≥ 16 Go RAM ; Docker Desktop disponible et licencié (voir §12).
- Sauvegardes réalisées manuellement par l'admin selon la procédure fournie.

---

## 10. Ce que l'application ne doit JAMAIS faire (garde-fous)

1. **Jamais** envoyer de données (verbatims, résultats, modèles, métriques) hors du poste : pas d'Internet, pas de cloud, pas d'API tierce, **pas de télémétrie**.
2. **Jamais** stocker en base un verbatim **non anonymisé** ; la base ne contient que du texte anonymisé.
3. **Jamais** prédire une classe hors `taxonomy_cultura_poc.json`, ni un couple (niv.1, niv.2) invalide (contrainte hiérarchique imposée).
4. **Jamais** modifier ou écraser les fichiers sources d'origine, ni les poids du modèle (volume modèles en lecture seule).
5. **Jamais** ré-entraîner le modèle automatiquement en production : l'entraînement reste une opération CLI maîtrisée et validée par un humain.
6. **Jamais** présenter une prédiction automatique comme une vérité validée : toujours afficher le score de confiance et le statut (auto / en revue / corrigé).
7. **Jamais** supprimer définitivement des données sans trace d'audit ni hors de la politique de rétention.
8. **Jamais** s'exposer sur un réseau public : écoute sur **localhost** uniquement.
9. **Jamais** committer de secrets ni de données clients dans le dépôt de code.
10. **Jamais** bloquer l'interface pendant un traitement long : tout traitement lourd est **asynchrone**.
11. **Jamais** donner accès aux données sans authentification ni rôle valide.
12. **Jamais** déclencher d'action métier à fort impact (ex. contacter un client) : l'app est un **outil d'aide à l'analyse**, pas un outil d'action.

---

## 11. Critères d'acceptation de la V1 (Definition of Done)

- [ ] `docker compose up` démarre toute la stack sur le laptop cible (arm64), sans accès réseau.
- [ ] Connexion + rôles fonctionnels ; un non-authentifié n'accède à rien.
- [ ] Upload des 2 Excel → validation des colonnes → lot créé.
- [ ] Traitement asynchrone d'un lot de 11k **< ~1 h** avec progression et notification.
- [ ] Résultats consultables/filtrables ; détail d'un verbatim conforme.
- [ ] Export CSV/XLSX **conforme au format du POC** (colonnes d'origine + colonnes modèle).
- [ ] File de revue + correction d'un verbatim (hiérarchie respectée) + export des corrections.
- [ ] Dashboards KPI modèle / résultats / volumétrie opérationnels.
- [ ] Historique des lots + journal d'audit.
- [ ] Activation d'une version de modèle déposée dans le volume, sans rebuild.
- [ ] Rétention configurable + purge auto et manuelle.
- [ ] Tous les garde-fous du §10 vérifiés (offline, anonymisation, taxonomie, localhost).

---

## 12. Risques & recommandations

| Risque | Impact | Mitigation / conseil |
|---|---|---|
| **Mono-poste = point de défaillance unique** (panne/perte du laptop) | Perte d'historique | Sauvegardes régulières des volumes ; l'archi conteneurisée permet de **migrer vers un petit serveur interne** sans refonte si l'usage se généralise. |
| **Ressources laptop** (CamemBERT CPU + Postgres + worker) | Lenteur / OOM | ONNX int8, un seul job lourd à la fois, allouer assez de RAM à Docker Desktop, recommander ≥ 16 Go. |
| **Licence Docker Desktop** (payante au-delà d'un certain seuil d'entreprise) | Conformité licence | Vérifier l'éligibilité ; alternatives gratuites : **Rancher Desktop / Podman / Colima**. |
| **Handoff modèle via volume** (dépôt manuel de fichiers) | Erreur d'activation | Validation au chargement (présence taxonomie/encodeurs/carte de version) + activation explicite tracée. |
| **Comptes locaux** (gestion mots de passe) | Sécurité | Politique de mot de passe, verrouillage anti-bruteforce ; **prévoir SSO Entra ID en V1.1**. |
| **Dérive du modèle** dans le temps | Qualité en baisse | KPI modèle visibles + alerte sous seuils ; ré-entraînement trimestriel via corrections validées. |
| **Conseil d'archi** | — | Bien que mono-poste, garder api/worker/front/db découplés (compose) pour pouvoir passer à un serveur multi-utilisateur sans réécriture. |

---

## 13. Trajectoire (phasage)

- **V1 (ce document)** : pilotage + revue humaine, mono-poste, comptes locaux, upload manuel.
- **V1.1** : SSO Azure AD / Entra ID, déploiement serveur interne multi-utilisateur, connecteurs API (Mopinion / MDTC).
- **V2** : ré-entraînement et gestion des versions **depuis l'UI** (MLOps), comparaison/promotion de modèles, suivi de dérive.

---

## 14. Annexes

### 14.1 Glossaire
- **MDTC / Mopinion** : les deux sources de verbatims.
- **niv.1 / niv.2** : grande thématique / sous-thématique (taxonomie : 20 / 67).
- **HITL** : human-in-the-loop (revue humaine).
- **Signal** : rupture client / churn / insatisfaction forte.
- **Lot (batch)** : ensemble de verbatims traités ensemble.

### 14.2 Lien avec le POC existant
Le moteur (`src/preprocessing`, `src/modeling`, `src/inference`, `src/output`, `src/evaluation`) est réutilisé tel quel par l'API et le worker. L'app ajoute : persistance, UI, jobs async, comptes/rôles, dashboards, revue, audit, rétention.

### 14.3 Décisions validées
- **Base de données : PostgreSQL**, conteneurisée et **100 % locale** (aucun port exposé hors localhost). ✓
- **Fonction « test à la volée »** d'un verbatim unique : **incluse en V1**. ✓
- **Nom de l'application : « Observatoire Ecom Studio »**. ✓
- **Équipe de développement : Claude Code (agent unique)**, en charge du développement complet. ✓

### 14.4 À préciser ultérieurement
- Port d'exposition local exact (défaut proposé : `http://localhost:8080`).
- Procédure de sauvegarde retenue (fréquence, emplacement) — spécifiée au L8.
