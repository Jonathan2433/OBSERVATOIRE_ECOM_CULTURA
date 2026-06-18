#!/usr/bin/env bash
# =============================================================================
#  restore_app.sh — Restaure un bundle de transmission sur une machine VIERGE.
#
#  À exécuter DEPUIS le dossier du bundle décompressé (oes-bundle-AAAAMMJJ-…/),
#  qui contient : images.tar, db.sql, data-*.tgz, docker-compose.yml,
#  .env.example, manifest.txt.
#
#  Pré-requis sur la cible : Docker + docker compose. AUCUN réseau requis.
#
#  Étapes : .env -> docker load -> base seule -> restauration DB -> volumes ->
#  stack complète -> vérification d'intégrité (comptages vs manifeste).
#
#  Usage :  bash restore_app.sh
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f images.tar ] || [ ! -f db.sql ]; then
  echo "ERREUR : lancez ce script depuis le dossier du bundle décompressé." >&2
  exit 1
fi

# 1. Fichier .env (créé depuis .env.example au 1er passage, à compléter).
if [ ! -f .env ]; then
  cp .env.example .env 2>/dev/null || true
  echo "⚠  .env créé depuis .env.example — VÉRIFIEZ POSTGRES_PASSWORD / SECRET_KEY puis relancez." >&2
  exit 1
fi
set -a; . ./.env; set +a
PGUSER="${POSTGRES_USER:-oes}"
PGDB="${POSTGRES_DB:-oes}"

echo "==> 1/5  Chargement des images (docker load)"
docker load -i images.tar

echo "==> 2/5  Démarrage de la base seule"
docker compose up -d db
for _ in $(seq 1 30); do
  if docker compose exec -T db pg_isready -U "${PGUSER}" -d "${PGDB}" >/dev/null 2>&1; then break; fi
  sleep 1
done

echo "==> 3/5  Restauration de la base (historique)"
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U "${PGUSER}" -d "${PGDB}" < db.sql

echo "==> 4/5  Restauration des volumes (modèles, uploads, sorties)"
for arc in data-models.tgz data-uploads.tgz data-output.tgz; do
  [ -f "${arc}" ] && tar xzf "${arc}" -C .
done
if [ -f data-raw/taxonomy_cultura_poc.json ]; then
  mkdir -p data/raw && cp data-raw/taxonomy_cultura_poc.json data/raw/
fi

echo "==> 5/5  Démarrage de la stack complète"
docker compose up -d

# --- Vérification d'intégrité (comptages vs manifeste) ----------------------
echo
echo "=== Vérification d'intégrité ==="
ok=1
if [ -f manifest.txt ]; then
  while IFS='=' read -r t expected; do
    case "${t}" in \#*|"") continue;; esac
    actual="$(docker compose exec -T db psql -tAU "${PGUSER}" -d "${PGDB}" -c "SELECT count(*) FROM ${t};" 2>/dev/null | tr -d '[:space:]' || echo '?')"
    if [ "${actual}" = "${expected}" ]; then
      printf "  ✅ %-16s %s\n" "${t}" "${actual}"
    else
      printf "  ❌ %-16s attendu=%s obtenu=%s\n" "${t}" "${expected}" "${actual}"; ok=0
    fi
  done < manifest.txt
else
  echo "  (pas de manifeste — vérification ignorée)"
fi

echo
if [ "${ok}" = 1 ]; then
  echo "✅ Restauration terminée — historique intègre. App sur http://localhost:8080"
else
  echo "⚠  Restauration terminée mais des comptages diffèrent (voir ci-dessus)." >&2
  exit 2
fi
