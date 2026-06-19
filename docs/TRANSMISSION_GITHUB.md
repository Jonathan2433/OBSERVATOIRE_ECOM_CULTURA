# Transmission via GitHub (public) — guide pas à pas

Ce document décrit comment **publier** le projet sur un dépôt GitHub public, puis
comment un collègue (le **manager**) l'**installe et le lance** chez lui. Deux parties :

- **Partie A** — pour celui qui publie (l'auteur).
- **Partie B** — pour celui qui récupère et teste (le manager).

> ⚠️ **Dépôt public = tout est visible (y compris l'historique git).** Ne jamais y
> mettre de secret ni de donnée client réelle. Le projet a été conçu pour ça : les
> secrets vivent dans `.env` (ignoré par git), les modèles/poids et les données de
> runtime sont ignorés. Les seuls fichiers de données versionnés sont
> `data/raw/*.xlsx`, **synthétiques** (aucune PII réelle).

---

## Partie A — Publier (auteur)

### A.1 Checklist AVANT de rendre public (30 s)
Vérifier qu'aucun secret n'est suivi par git :
```bash
git ls-files .env                 # doit ne RIEN afficher (le .env est ignoré)
git ls-files | grep -iE "\.env$|secret|\.key$|\.pem$|safetensors|\.onnx|data/models" || echo "OK : rien de sensible"
```
- ✅ `.env` non suivi (mots de passe, SECRET_KEY restent locaux).
- ✅ `data/models/`, `*.safetensors`, `*.onnx`, `*.joblib` ignorés (gros + non nécessaires au test).
- ✅ `data/raw/*.xlsx` = données **simulées** (OK à publier). *Si un jour ces fichiers
  contiennent du réel : décommenter `data/raw/` dans `.gitignore` et les retirer du suivi.*

### A.2 Créer le dépôt public et pousser
Avec **GitHub CLI** (`gh`) :
```bash
gh repo create OBSERVATOIRE_ECOM_CULTURA --public --source=. --remote=origin --push
git push origin --tags        # publie aussi les tags (v3.0, v4.0)
```
**Ou** sans `gh` (dépôt créé via le site github.com, vide, sans README) :
```bash
git remote add origin https://github.com/<compte>/OBSERVATOIRE_ECOM_CULTURA.git
git branch -M main
git push -u origin main
git push origin --tags
```
> Authentification HTTPS : GitHub demande un **token personnel (PAT)** comme mot de
> passe (Settings → Developer settings → Personal access tokens). Le PAT n'est saisi
> que par l'auteur, jamais stocké dans le projet.

### A.3 Envoyer au manager
Lui transmettre **uniquement** : l'URL du dépôt + le lien vers ce guide (Partie B).
**Ne pas** lui envoyer votre `.env` : il crée le sien (voir B.2).

---

## Partie B — Installer & lancer (manager)

### B.1 Prérequis
- **Docker Desktop** (macOS/Windows/Linux), démarré, avec **≥ 8 Go RAM / 4 cœurs**
  (réglage dans Docker Desktop → Settings → Resources).
- **git**.
- *(Optionnel)* **LM Studio** si l'on veut tester le moteur LLM (sinon, mode démo/CamemBERT).

### B.2 Récupérer et configurer
```bash
git clone https://github.com/<compte>/OBSERVATOIRE_ECOM_CULTURA.git
cd OBSERVATOIRE_ECOM_CULTURA          # (dossier cultura-verbatim-classifier selon le repo)
cp .env.example .env
```
**Éditer `.env`** — ⚠️ **à ne pas oublier**, sinon l'app refusera de démarrer
correctement ou sera non sécurisée :

| Variable | Quoi mettre |
|---|---|
| `POSTGRES_PASSWORD` | Un mot de passe au choix. **À figer une fois pour toutes** (le changer plus tard impose `docker compose down -v`, ce qui efface la base). |
| `SECRET_KEY` | Une chaîne aléatoire longue. Générer : `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ADMIN_USERNAME` | Identifiant du **compte admin** (ex. `admin`). |
| `ADMIN_PASSWORD` | Mot de passe admin, **≥ 12 caractères**. C'est avec ce couple qu'on se connecte la 1re fois. |

> Laisser `LMSTUDIO_ENABLED=false` pour un premier lancement.

### B.3 Lancer
```bash
docker compose up --build        # 1re fois : build (quelques minutes)
```
Puis ouvrir **http://localhost:8080**.

### B.4 Se connecter
- Identifiant / mot de passe = `ADMIN_USERNAME` / `ADMIN_PASSWORD` du `.env`.
- Le **compte admin est créé automatiquement au 1er démarrage** (si la base est vide).
- Une fois connecté : créer d'autres comptes dans **Utilisateurs**, changer son mot de
  passe dans **Mon compte**.

### B.5 Tester
1. **Lots → Nouveau lot** : déposer les fichiers Excel de démo fournis dans le dépôt
   (`data/raw/mdtc_poc.xlsx` et/ou `data/raw/mopinion_poc.xlsx`) → **Lancer**.
2. Consulter **Résultats**, **Tableaux de bord**, **Revue**.

> **Quel moteur ?** Par défaut, le dépôt ne contient **aucun modèle entraîné** → l'app
> tourne en **mode démonstration** (classifieur heuristique *stub* : thèmes approximatifs,
> mais le parcours complet fonctionne). Pour de la vraie qualité :
> - **CamemBERT** : entraîner le modèle (voir [GUIDE_ENTRAINEMENT.md](GUIDE_ENTRAINEMENT.md)), puis l'activer dans **Administration → Modèles** ;
> - **LM Studio** : installer LM Studio, charger un modèle, démarrer le serveur local,
>   passer `LMSTUDIO_ENABLED=true` + renseigner `LMSTUDIO_MODEL` dans `.env`, relancer
>   `docker compose up -d`, puis **Administration → Modèles → Re-scanner → Activer**
>   (voir [EXPLOITATION.md](EXPLOITATION.md) §4 bis).

### B.6 Arrêter / relancer
```bash
docker compose down       # arrête (les données PostgreSQL persistent dans le volume)
docker compose up -d       # relance
docker compose down -v     # ⚠️ EFFACE la base (comptes, lots, résultats) — repart de zéro
```

---

## Dépannage express
| Symptôme | Cause | Solution |
|---|---|---|
| `password authentication failed for user "oes"` (api en boucle) | `POSTGRES_PASSWORD` changé après le 1er démarrage | `docker compose down -v` puis `up --build` (efface la base), ou remettre l'ancien mot de passe |
| Page inaccessible sur :8080 | Build en cours / port occupé | Attendre la fin du build ; changer `WEB_PORT` dans `.env` |
| Thèmes peu pertinents | Mode démo (aucun modèle réel) | Entraîner CamemBERT ou activer LM Studio (B.5) |
| LM Studio : `Failed to resolve model metadata` | Requêtes parallèles + JIT loading | LM Studio : désactiver « Just-in-Time Model Loading » ; garder `LMSTUDIO_MAX_PARALLEL=1` |

Pour aller plus loin : [`EXPLOITATION.md`](EXPLOITATION.md) (admin/exploitant),
[`GUIDE_UTILISATEUR.md`](GUIDE_UTILISATEUR.md) (analyste).
