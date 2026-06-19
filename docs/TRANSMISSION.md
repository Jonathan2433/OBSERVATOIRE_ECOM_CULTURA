# Transmission de l'application (poste → poste / serveur)

Déplacer l'« Observatoire Ecom Studio » sur une autre machine **hors-ligne**, en
**conservant tout l'historique** (comptes, lots, résultats anonymisés, corrections,
audit, configuration) et les modèles déposés. Sans registre Docker ni réseau.

> Deux scripts : [`scripts/package_app.sh`](../scripts/package_app.sh) (source) et
> [`scripts/restore_app.sh`](../scripts/restore_app.sh) (cible, inclus dans le bundle).

---

## 1. Sur la machine SOURCE — créer le bundle

```bash
bash scripts/package_app.sh
```
Produit `transmission/oes-bundle-AAAAMMJJ-HHMMSS.tar.gz` contenant :

| Élément | Contenu |
|---|---|
| `images.tar` | les 3 images Docker (api, worker, web) via `docker save` |
| `db.sql` | **dump PostgreSQL logique** = tout l'historique |
| `data-models.tgz` / `data-uploads.tgz` / `data-output.tgz` | volumes (modèle entraîné, fichiers déposés, exports) |
| `docker-compose.yml`, `.env.example`, `data-raw/taxonomy…` | configuration de déploiement |
| `restore_app.sh` | script de restauration |
| `manifest.txt` | **comptages de référence** (vérification d'intégrité) |

Transférer ce `.tar.gz` (USB, disque…) vers la cible.

---

## 2. Sur la machine CIBLE — restaurer

Pré-requis : Docker + docker compose installés. Aucun réseau requis.

```bash
tar xzf oes-bundle-AAAAMMJJ-HHMMSS.tar.gz
cd oes-bundle-AAAAMMJJ-HHMMSS
bash restore_app.sh          # 1er passage : crée .env depuis .env.example
#   -> éditer .env (POSTGRES_PASSWORD, SECRET_KEY, ADMIN_*) puis :
bash restore_app.sh          # restaure images + base + volumes + démarre
```

Le script enchaîne : `docker load` → base seule → **restauration du dump** →
volumes → stack complète → **vérification d'intégrité** (comptages vs `manifest.txt`).

Sortie attendue :
```
=== Vérification d'intégrité ===
  ✅ users            3
  ✅ batches          12
  ✅ results          13456
  ✅ corrections      87
  ✅ audit_log        212
  ✅ model_versions   2
✅ Restauration terminée — historique intègre. App sur http://localhost:8080
```

---

## 3. Notes

- **Mot de passe PostgreSQL** : sur la cible, `POSTGRES_PASSWORD` du `.env` doit être
  cohérent au 1er démarrage du volume. Le dump étant logique, il se restaure quelle que
  soit la valeur — mais gardez le même `.env` ensuite (cf. dépannage exploitation).
- **Migrations** : au démarrage, l'API applique Alembic ; le dump contenant déjà le schéma
  à jour (`alembic_version`), c'est un no-op — pas de conflit.
- **Offline strict préservé** : images transférées en fichier, modèle de base déjà local,
  aucun `docker pull`.
- **Sauvegarde courante** : le même `package_app.sh` sert de **sauvegarde complète** datée.
  Voir aussi la sauvegarde DB seule dans [EXPLOITATION.md](EXPLOITATION.md) §5.
- **Moteur LM Studio (V4)** : c'est une **dépendance hôte hors bundle Docker**. Si le poste
  cible doit l'utiliser, y installer LM Studio, **charger un modèle** et démarrer le serveur
  local (cf. [EXPLOITATION.md](EXPLOITATION.md) §4 bis), puis `LMSTUDIO_ENABLED=true` dans `.env`.
  Le bundle transféré fonctionne **sans** LM Studio (moteur désactivé par défaut → CamemBERT/stub).
