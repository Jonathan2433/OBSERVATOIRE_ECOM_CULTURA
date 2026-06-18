# Dossier de passation — Observatoire Ecom Studio

Point d'entrée unique pour reprendre, exploiter, déplacer et faire évoluer
l'application. État : **POC avancée** (V1 fonctionnelle + V2 design + V3 finalisation).

---

## 1. En une phrase

Application **100 % locale, hors-ligne, conteneurisée** qui classe les verbatims
clients Cultura (thèmes hiérarchiques, sentiment, signaux) avec **revue humaine**,
**tableaux de bord** et **anonymisation RGPD** — moteur **CamemBERT** (ONNX int8),
exposée sur `localhost` uniquement.

## 2. Démarrer (poste avec Docker)

```bash
cp .env.example .env      # éditer SECRET_KEY, ADMIN_PASSWORD, POSTGRES_PASSWORD
docker compose up --build
```
→ http://localhost:8080. Détails et dépannage : **[EXPLOITATION.md](EXPLOITATION.md)**.

## 3. Documentation par sujet

| Besoin | Document |
|---|---|
| Vision produit, exigences, garde-fous, DoD | [CAHIER_DES_CHARGES.md](CAHIER_DES_CHARGES.md) |
| Utiliser l'app (analyste / admin) | [GUIDE_UTILISATEUR.md](GUIDE_UTILISATEUR.md) |
| Installer, secrets, sauvegarde, dépannage | [EXPLOITATION.md](EXPLOITATION.md) |
| **Entraîner & déposer le modèle CamemBERT** | [GUIDE_ENTRAINEMENT.md](GUIDE_ENTRAINEMENT.md) |
| **Déplacer l'app vers un autre poste (avec historique)** | [TRANSMISSION.md](TRANSMISSION.md) |
| Charte UI / design system V2 | [CHARTE_UI_V2.md](CHARTE_UI_V2.md) |
| Recette V1 (conformité §10/§11) | [RECETTE_V1.md](RECETTE_V1.md) |
| Suivi des lots (historique des développements) | [SUIVI_LOTS.md](SUIVI_LOTS.md) |
| Plans : [V1](PLAN_DEVELOPPEMENT_V1.md) · [V2](PLAN_V2_DESIGN.md) · [V3](PLAN_V3.md) | — |

## 4. Architecture (rappel)

5 services Docker : `web` (nginx + front React/TS, **seul exposé**, `127.0.0.1:8080`),
`api` (FastAPI, sans torch), `worker` (RQ + moteur ML `src/`), `db` (PostgreSQL),
`redis`. Package partagé `app/common` (DB + ORM). Modèles montés **lecture seule**.
Base **sans PII** (texte anonymisé uniquement).

## 5. Opérations courantes

- **Run mensuel** : déposer les 2 Excel → lancer → suivre → consulter/exporter → revue.
- **Annuler un lot** en cours : bouton *Annuler* (détail du lot). Au redémarrage du
  worker, les lots interrompus repassent en « échec » (pas de lot fantôme).
- **Nouveau modèle** (trimestriel) : entraîner (CLI) → déposer dans `data/models` →
  `docker compose restart worker` → activer dans *Administration → Modèles*.
- **Exploitation** : *Administration → Exploitation* (lots, taux d'échec, disque,
  rétention) ; *Administration → Rétention* pour purger (RGPD).
- **Mot de passe** : *Mon compte* (en haut à droite).
- **Sauvegarde / transmission** : `bash scripts/package_app.sh` (voir TRANSMISSION.md).

## 6. Recettes (non-régression)

Hors ligne, sans Docker, dans un venv torch-free
(`fastapi httpx sqlalchemy pydantic pydantic-settings argon2-cffi PyJWT python-multipart pandas numpy openpyxl pyyaml redis rq`) :

```bash
python app/tests/recette_v1.py    # conformité V1 (garde-fous §10 + DoD §11) -> 48/48
python app/tests/recette_v3.py    # ajouts V3 (annulation, reprise, ops, mot de passe) -> 13/13
python scripts/validate_pipeline.py   # plomberie ML torch-free (stub)
```

## 7. Reste à faire / trajectoire

- **T2 (en cours côté data)** : entraîner le **vrai** CamemBERT (`run_training.py`),
  l'activer, et **mesurer un lot ~11k < 1 h** (dernier critère du DoD §11).
- **Test de restauration** du bundle sur une 2ᵉ machine (packaging déjà validé).
- **V1.1** : SSO Entra ID, serveur interne multi-utilisateur, connecteurs API.
- **V2 (MLOps)** : ré-entraînement et comparaison de modèles depuis l'UI.

## 8. Garde-fous à ne jamais enfreindre (cf. §10 du cahier)

Pas de sortie réseau / cloud / télémétrie · jamais de PII en base · prédiction
toujours contrainte à la taxonomie · poids modèle en lecture seule · pas de
ré-entraînement auto en prod · localhost uniquement · pas de secrets/données
clients dans le dépôt · traitement lourd asynchrone · accès soumis à auth + rôle.
