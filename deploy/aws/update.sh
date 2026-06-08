#!/usr/bin/env bash
#
# Update the running pilot to the latest code and rebuild — run ON the box
# (installed at /usr/local/bin/pilot-update by user-data / the operator).
#
#   pilot-update          # update to latest main
#   pilot-update <ref>    # update to a branch/tag/sha
#
# The repo is private and the on-box remote is tokenless, so we re-auth the
# fetch with the GitHub PAT from SSM (used only for the fetch, never stored).
set -euo pipefail
log(){ echo "[update] $(date -u +%H:%M:%S) $*"; }

APP_DIR=/opt/pharmassist
REPO_SLUG=ladikosalexios/Pharmassist
REF="${1:-main}"
SSM_PREFIX=/pharmassist/pilot

TOKEN=$(curl -sX PUT 'http://169.254.169.254/latest/api/token' -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')
REGION=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)

log "Fetching $REF (token from SSM)..."
GH_PAT=$(aws ssm get-parameter --with-decryption --region "$REGION" --name "$SSM_PREFIX/GH_PAT" --query Parameter.Value --output text)
git -C "$APP_DIR" fetch --depth 1 "https://x-access-token:${GH_PAT}@github.com/${REPO_SLUG}.git" "$REF"
unset GH_PAT
git -C "$APP_DIR" reset --hard FETCH_HEAD
log "Now at $(git -C "$APP_DIR" rev-parse --short HEAD)"

cd "$APP_DIR"
log "Rebuilding + restarting changed services..."
docker compose -f compose.prod.yaml --env-file .env.prod up -d --build
log "Applying migrations..."
docker compose -f compose.prod.yaml --env-file .env.prod exec -T backend alembic upgrade head
docker image prune -f >/dev/null 2>&1 || true
docker compose -f compose.prod.yaml --env-file .env.prod ps
log "DONE"
