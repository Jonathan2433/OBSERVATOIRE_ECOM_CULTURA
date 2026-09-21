# Dossier de passation — Observatoire Ecom Studio

Point d'entrée unique pour reprendre, exploiter, déplacer et faire évoluer
l'application. État : **V5 en service** (V1→V5 livrées) + **modèle Cultura 2026
recetté, mis à disposition, non basculé par défaut** + **restitution métier à la
maille répondant livrée le 17/09/2026**.

---

## 1. En une phrase

Application **100 % locale, hors-ligne, conteneurisée** qui classe les verbatims
clients Cultura (thèmes hiérarchiques, sentiment, signaux) avec **revue humaine**,
**tableaux de bord** et **anonymisation RGPD** — moteur **CamemBERT** (PyTorch),
exposée sur `localhost` uniquement.

## 2. Démarrer (poste avec Docker)

```bash
cp .env.example .env      # éditer SECRET_KEY, ADMIN_PASSWORD, POSTGRES_PASSWORD
docker compose up --build
```
→ http://localhost:8080. Détails et dépannage : **[EXPLOITATION.md](EXPLOITATION.md)**.

## 3. Documentation par sujet

### L'application

| Besoin | Document |
|---|---|
| Vision produit, exigences, garde-fous, DoD | [CAHIER_DES_CHARGES.md](CAHIER_DES_CHARGES.md) |
| Utiliser l'app (analyste / admin) | [GUIDE_UTILISATEUR.md](GUIDE_UTILISATEUR.md) |
| Installer, secrets, sauvegarde, dépannage | [EXPLOITATION.md](EXPLOITATION.md) |
| **Entraîner & déposer un modèle** | [GUIDE_ENTRAINEMENT.md](GUIDE_ENTRAINEMENT.md) |
| **Déplacer l'app vers un autre poste (avec historique)** | [TRANSMISSION.md](TRANSMISSION.md) |
| Déployer la satisfaction à la maille répondant | [MIGRATION_SATISFACTION_REPONDANT.md](MIGRATION_SATISFACTION_REPONDANT.md) |
| Charte UI / design system V2 | [CHARTE_UI_V2.md](CHARTE_UI_V2.md) |
| Multi-moteur : cascade, comparaison, juge | [SPEC_V5_MULTI_MOTEUR.md](SPEC_V5_MULTI_MOTEUR.md) · [SPEC_V4_LMSTUDIO.md](SPEC_V4_LMSTUDIO.md) |
| Historique des développements et **journal des décisions** | [SUIVI_LOTS.md](SUIVI_LOTS.md) |

### Le modèle Cultura 2026 (refonte, septembre 2026)

| Besoin | Document |
|---|---|
| **Comment le moteur décide, et ce que ça vaut** | **[COUCHE_DECISION.md](COUCHE_DECISION.md)** |
| Verdict de recette, critères, procédure de bascule | [RECETTE_NOUVEAU_MODELE.md](RECETTE_NOUVEAU_MODELE.md) |
| Cadrage et découpage en lots | [CADRAGE_NOUVEAU_MODELE.md](CADRAGE_NOUVEAU_MODELE.md) · [PLAN_LOTS_NOUVEAU_MODELE.md](PLAN_LOTS_NOUVEAU_MODELE.md) |
| Ingestion de la livraison Cultura | [SPEC_CHARGEUR.md](SPEC_CHARGEUR.md) · [RAPPORT_L1a_CHARGEUR.md](RAPPORT_L1a_CHARGEUR.md) |
| Protocole sans fuite, baseline de l'ancien modèle | [RAPPORT_L2_BASELINE.md](RAPPORT_L2_BASELINE.md) |
| Réentraînement, trois itérations | [RAPPORT_L6_REENTRAINEMENT.md](RAPPORT_L6_REENTRAINEMENT.md) |
| Pistes d'optimisation, y compris celles qui ont échoué | [OPTIMISATION_SANS_CULTURA.md](OPTIMISATION_SANS_CULTURA.md) |
| Questions ouvertes adressées à Cultura | [SOLLICITATION_CULTURA.md](SOLLICITATION_CULTURA.md) |

> **Deux natures de documents.** Ceux du premier tableau décrivent **l'état
> courant** et sont tenus à jour. Les rapports de lot (`RAPPORT_*`) sont des
> **relevés datés** : ils ne sont pas réécrits, seulement complétés d'un avis de
> correction quand une mesure ultérieure les contredit. Un rapport qu'on récrit
> ne prouve plus rien.

## 4. Architecture (rappel)

5 services Docker : `web` (nginx + front React/TS, **seul exposé**, `127.0.0.1:8080`),
`api` (FastAPI, sans torch), `worker` (RQ + moteur ML `src/`), `db` (PostgreSQL),
`redis`. Package partagé `app/common` (DB + ORM). Modèles montés **lecture seule**.
Base **sans PII** (texte anonymisé uniquement). `survey_responses` conserve la
maille répondant avec une clé opaque, la note native, la source, le statut client
normalisé et la date métier ; chaque `result` peut lui être rattaché.

**Plusieurs moteurs coexistent** dans le sélecteur — deux CamemBERT (V1 et
Cultura 2026), LM Studio, Claude (comparaison seule), le stub. Chaque CamemBERT
porte son **profil** (`config.yaml → moteurs_camembert`) : son référentiel, son
seuil d'activation, son seuil de revue, sa couche de décision. Activer un moteur
n'en supprime aucun ; **le retour arrière est une resélection**.

LM Studio est aligné sur Cultura 2026 par le prompt `v2-cultura-2026` et charge le
référentiel 11/59 embarqué. Son contrat impose un sentiment unique par verbatim,
un second thème seulement pour deux sujets distincts et la priorité au négatif
dans les verbatims mixtes. Le prompt Claude reste en V1 pour isoler la comparaison.

## 5. Opérations courantes

- **Run mensuel** : déposer en une fois les exports CSV/XLSX disponibles (jusqu'à
  20 fichiers, quatre sources reconnues par leurs colonnes) → lancer → suivre →
  consulter/exporter → revue.
- **Lire la synthèse métier** : les notes déclarées sont comptées une fois par
  répondant ; les thèmes proviennent uniquement des textes libres. Une source non
  reçue reste visible et ne vaut pas zéro. Les graphiques thème × sentiment
  classent les thèmes par volume négatif décroissant afin de faire remonter les
  irritants prioritaires. Dans *Répartition des thèmes*, le métier peut classer
  les niveaux 1 et 2 par volume total, négatif, neutre ou positif ; ce choix suit
  l'angle actif et les filtres source/date.
- **Annuler un lot** en cours : bouton *Annuler* (détail du lot). Au redémarrage du
  worker, les lots interrompus repassent en « échec » (pas de lot fantôme).
- **Nouveau modèle** : entraîner (CLI) → déposer sous `data/models/<nom>/` **avec son
  `taxonomy.json`** → déclarer le profil dans `config.yaml` → `docker compose restart
  worker` → activer dans *Administration → Modèles*.
- **Changer de moteur** : *Administration → Modèles → Activer*. Tracé à l'audit.
- **Exploitation** : *Administration → Exploitation* (lots, taux d'échec, disque,
  rétention) ; *Administration → Rétention* pour purger (RGPD).
- **Mot de passe** : *Mon compte* (en haut à droite).
- **Sauvegarde / transmission** : `bash scripts/package_app.sh` (voir TRANSMISSION.md).

## 6. Recettes (non-régression)

**Applicatives** — hors ligne, sans Docker, venv torch-free
(`fastapi httpx sqlalchemy pydantic pydantic-settings argon2-cffi PyJWT python-multipart pandas numpy openpyxl pyyaml redis rq`) :

```bash
python app/tests/recette_v1.py   # -> 115 OK   python app/tests/recette_v4.py  # -> 67 OK
python app/tests/recette_v3.py   # -> 13 OK    python app/tests/recette_v5.py  # -> 115 OK
python app/tests/recette_v6.py   # -> 42 OK
python app/tests/test_satisfaction_respondents.py  # -> 10 OK
```

**Modèle** — environnement ML complet (`pip install -r requirements.txt`) :

```bash
python app/tests/recette_l1a_chargeur.py     # spaCy + fichiers réels requis pour le parcours complet
python app/tests/recette_l2_protocole.py     # -> 15 OK
python app/tests/recette_couche_decision.py  # -> 46 OK
```

## 7. Reste à faire

- **Bascule du modèle par défaut** — décision humaine, à faire depuis
  *Administration → Modèles* pour qu'elle soit tracée. Le modèle Cultura 2026 est
  recetté et disponible ; **V1 reste actif** tant que personne n'a basculé.
- **Mesurer un lot ~11k < 1 h** en conditions réelles (dernier critère du DoD §11).
- ~~**Ingestion au format Cultura 2026**~~ — **fait le 15/09/2026.** L'application
  lit désormais les exports Cultura 2026 en `.csv` comme en `.xlsx`, reconnaît les
  quatre schémas sur leur jeu de colonnes, convertit la satisfaction textuelle, et
  produit la **source fine** — ce qui rend enfin active la règle d'arbitrage
  contextuel. Le format historique reste lu par son chargeur d'origine.
- ~~**Restitution du second thème et de la satisfaction**~~ — **fait le
  17/09/2026.** Les écrans de résultats et les tableaux de bord ne s'arrêtent
  plus au premier thème. Depuis le **16/09/2026**, la revue permet également
  d'ajouter, corriger ou supprimer le second thème, son sous-thème et son
  sentiment. Les migrations `0011` et `0012` ajoutent la réponse source et sa
  date métier : la satisfaction est désormais calculée **une fois par répondant**,
  sur l'échelle native. Les quatre sources et les trois statuts MDTC restent
  visibles, y compris avec un effectif nul. Les lots historiques ne sont pas
  rétro-remplis : ils indiquent « détail natif indisponible » jusqu'à un
  retraitement volontaire depuis les fichiers source.
- **Faire valider la table des libellés de satisfaction MDTC (Q-17)** — les
  moyennes par source conservent désormais leur échelle native et l'affichage sur
  10 est une projection explicite. La correspondance des libellés MDTC en 1–4
  reste toutefois une hypothèse eXalt à faire confirmer par Cultura.
- **Questions fermées** — elles sont volontairement exclues de l'analyse des
  verbatims. Leur restitution exige un mapping métier séparé entre chaque choix
  du formulaire et l'indicateur attendu.
- **`signaux_non_mesures` est inerte en production** — `/api/meta` le calcule en
  important `src.inference.predictor`, absent de l'image API (volontairement sans
  torch). L'appel échoue silencieusement et renvoie `[]` : le badge « non mesuré »
  arbitré le 11/09 ne s'affiche donc **jamais** dans le déploiement Docker, alors
  qu'il fonctionne en recette. À rendre indépendant de `src/`, comme vient de
  l'être le statut des échelles de satisfaction (lecture YAML directe).
- **Atelier de référentiel (L3)** côté Cultura — recouvrements de libellés
  (`Cartes cadeaux` / `Passer commande`, `Choix produit` / `Recherche produit`).
- **Confort** : `torch` non épinglé tire les wheels CUDA sur un déploiement CPU
  (image worker 10,3 Go, ~2 Go récupérables) ; une modification de `src/` peut
  invalider le cache de build et relancer ~10 min d'installation.
- **V1.1** : SSO Entra ID, serveur interne multi-utilisateur, connecteurs API.
- **V2 (MLOps)** : ré-entraînement et comparaison de modèles depuis l'UI.

## 8. Garde-fous à ne jamais enfreindre (cf. §10 du cahier)

Pas de sortie réseau / cloud / télémétrie · jamais de PII en base · prédiction
toujours contrainte à la taxonomie · poids modèle en lecture seule · pas de
ré-entraînement auto en prod · localhost uniquement · pas de secrets/données
clients dans le dépôt · traitement lourd asynchrone · accès soumis à auth + rôle.

**Trois garde-fous ajoutés par la refonte :**

- **Aucun nombre magique dans le code** — seuils, cibles et leviers vivent dans
  `config/config.yaml`, avec le motif de leur valeur.
- **Un chiffre ne se publie jamais sans son protocole** — jeu, effectif, seuil,
  politique de décision. Les métriques invalides du 18/06 ont survécu deux mois
  faute de cette règle ; elles ne sont plus publiées.
- **Un levier muet est pire que pas de levier** — une règle qui ne peut pas
  s'appliquer échoue au démarrage ou se journalise, jamais ne se tait.
