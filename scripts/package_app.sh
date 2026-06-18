#!/usr/bin/env bash
# =============================================================================
#  package_app.sh — Crée un bundle de TRANSMISSION hors-ligne de l'application.
#
#  Contenu du bundle : images Docker (docker save) + dump PostgreSQL (logique,
#  avec tout l'historique : comptes, lots, résultats, corrections, audit) +
#  archives des volumes (modèles, uploads, sorties) + compose + .env.example +
#  script de restauration + manifeste d'intégrité.
#
#  À transférer (USB, etc.) puis restaurer sur une machine vierge avec
#  restore_app.sh. Aucun registre ni réseau requis (offline strict).
#
#  Usage :  bash scripts/package_app.sh
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

# Charge POSTGRES_USER / POSTGRES_DB depuis .env (valeurs par défaut sinon).
if [ -f .env ]; then set -a; . ./.env; set +a; fi
PGUSER="${POSTGRES_USER:-oes}"
PGDB="${POSTGRES_DB:-oes}"

STAMP="$(date +%Y%m%d-%H%M%S)"
BUNDLE="oes-bundle-${STAMP}"
OUT="transmission/${BUNDLE}"
mkdir -p "${OUT}"

echo "==> 1/5  Construction des images"
docker compose build

echo "==> 2/5  Sauvegarde des images (docker save)"
IMAGES="$(docker compose config --images | sort -u)"
echo "${IMAGES}" | tr ' ' '\n' > "${OUT}/images.list"
# shellcheck disable=SC2086
docker save ${IMAGES} -o "${OUT}/images.tar"

echo "==> 3/5  Dump PostgreSQL (historique complet)"
docker compose up -d db
# Attente que la base réponde
for _ in $(seq 1 30); do
  if docker compose exec -T db pg_isready -U "${PGUSER}" -d "${PGDB}" >/dev/null 2>&1; then break; fi
  sleep 1
done
docker compose exec -T db pg_dump -U "${PGUSER}" -d "${PGDB}" --no-owner --clean --if-exists > "${OUT}/db.sql"

# Manifeste d'intégrité (comptages de référence pour vérif post-restauration)
{
  echo "# Manifeste d'intégrité — ${STAMP}"
  for t in users batches results corrections audit_log model_versions; do
    n="$(docker compose exec -T db psql -tAU "${PGUSER}" -d "${PGDB}" -c "SELECT count(*) FROM ${t};" 2>/dev/null | tr -d '[:space:]' || echo '?')"
    echo "${t}=${n}"
  done
} > "${OUT}/manifest.txt"

echo "==> 4/5  Archivage des volumes (modèles, uploads, sorties)"
for d in data/models data/uploads data/output; do
  if [ -d "${d}" ]; then
    tar czf "${OUT}/$(echo "${d}" | tr '/' '-').tgz" -C "${ROOT}" "${d}"
  fi
done

echo "==> 5/5  Configuration + script de restauration"
cp docker-compose.yml "${OUT}/"
[ -f .env.example ] && cp .env.example "${OUT}/"
cp scripts/restore_app.sh "${OUT}/"
[ -f data/raw/taxonomy_cultura_poc.json ] && { mkdir -p "${OUT}/data-raw"; cp data/raw/taxonomy_cultura_poc.json "${OUT}/data-raw/"; }

# Archive finale
tar czf "${OUT}.tar.gz" -C transmission "${BUNDLE}"
rm -rf "${OUT}"

echo
echo "✅ Bundle de transmission créé :"
echo "   ${ROOT}/${OUT}.tar.gz"
echo "   Manifeste d'intégrité inclus. À restaurer avec restore_app.sh sur la cible."
