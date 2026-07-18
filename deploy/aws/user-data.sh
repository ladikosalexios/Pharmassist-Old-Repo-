#!/usr/bin/env bash
#
# EC2 user-data bootstrap — PharmAssist mock demo, PUBLIC HTTPS.
# Target AMI: Amazon Linux 2023. Runs as root on first boot (cloud-init).
#
# What it does:
#   1. Installs Docker + the Compose plugin (no VPN).
#   2. Derives a public HTTPS hostname from the box's public IPv4 via sslip.io
#      (`<ip>.sslip.io` resolves publicly → Caddy issues a real Let's Encrypt
#      cert, with zero DNS setup). Set PILOT_DOMAIN below to use your own domain.
#   3. Clones the repo and assembles .env.prod (crypto secrets generated on-box;
#      ΗΔΥΚΑ + repo creds come from the CONFIG block below).
#   4. Brings up compose.prod.yaml, then migrates + seeds the DB.
#
# The stack runs PHARMAPI_MOCK=true (no live ΗΔΥΚΑ at runtime), but scripts.seed
# authenticates once against live Pharmapi to materialise the demo pharmacy — so
# PHARMAPI_* must be real (the ΗΔΥΚΑ test-env creds are fine).
#
# SECURITY NOTE: values in this CONFIG block are retrievable by anyone with
# `ec2:DescribeInstanceAttribute` on this instance (user-data is not secret).
# Fine for the ΗΔΥΚΑ *test-env* creds + a read-only repo token on a throwaway
# demo box; do NOT put production secrets here.
set -euo pipefail

# ── CONFIG — fill these before launch ─────────────────────────────────────────
REPO_URL="https://github.com/ladikosalexios/Pharmassist.git"
REPO_REF="main"
APP_DIR="/opt/pharmassist"
COMPOSE_VERSION="v2.32.4"

# Own domain? Set it (and point an A record here). Empty → auto `<ip>.sslip.io`.
PILOT_DOMAIN=""

# GitHub read-only token (private repo clone). Fine-grained, Contents:Read.
GH_PAT="__FILL_ME__"

# ΗΔΥΚΑ Pharmapi (test-env creds are fine — used by the seed, and at runtime when
# PHARMAPI_MOCK=false).
PHARMAPI_USERNAME="__FILL_ME__"
PHARMAPI_PASSWORD="__FILL_ME__"
PHARMAPI_API_KEY="__FILL_ME__"

# "true"  → synthetic data at runtime (safe for a public box).
# "false" → LIVE ΗΔΥΚΑ data. This makes a publicly-reachable box proxy real
#           (test-env) patient data — restrict the security group accordingly.
PHARMAPI_MOCK="true"
# ──────────────────────────────────────────────────────────────────────────────

log() { echo "[bootstrap] $(date -u +%H:%M:%S) $*"; }

log "Installing Docker, git..."
dnf -y update
dnf -y install docker git
systemctl enable --now docker

log "Installing the Docker Compose plugin ($COMPOSE_VERSION)..."
install -d /usr/libexec/docker/cli-plugins
curl -fsSL \
  "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)" \
  -o /usr/libexec/docker/cli-plugins/docker-compose
chmod +x /usr/libexec/docker/cli-plugins/docker-compose

# Public IPv4 from IMDSv2 → sslip.io hostname (unless a domain was set).
TOKEN="$(curl -sX PUT 'http://169.254.169.254/latest/api/token' \
  -H 'X-aws-ec2-metadata-token-ttl-seconds: 300')"
PUBLIC_IP="$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/public-ipv4)"
DOMAIN="${PILOT_DOMAIN:-${PUBLIC_IP}.sslip.io}"
log "Public HTTPS host: https://$DOMAIN"

log "Cloning $REPO_URL@$REPO_REF -> $APP_DIR..."
AUTH_URL="https://x-access-token:${GH_PAT}@${REPO_URL#https://}"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch --depth 1 "$AUTH_URL" "$REPO_REF"
  git -C "$APP_DIR" reset --hard FETCH_HEAD
else
  git clone --branch "$REPO_REF" --depth 1 "$AUTH_URL" "$APP_DIR"
  git -C "$APP_DIR" remote set-url origin "$REPO_URL"   # scrub token from stored remote
fi
unset AUTH_URL

# .env.prod is written ONCE — crypto keys must be stable across reboots or
# encrypted-at-rest credentials stop decrypting. Regenerate only if absent.
if [ ! -f "$APP_DIR/.env.prod" ]; then
  log "Generating .env.prod (mode 600)..."
  umask 077
  gen_hex() { openssl rand -hex 32; }
  gen_b64() { openssl rand -base64 32; }
  cat > "$APP_DIR/.env.prod" <<ENVEOF
SECRET_KEY=$(gen_hex)
CREDENTIAL_ENCRYPTION_KEY=$(gen_b64)
POSTGRES_PASSWORD=$(gen_hex)
PHARMAPI_USERNAME=$PHARMAPI_USERNAME
PHARMAPI_PASSWORD=$PHARMAPI_PASSWORD
PHARMAPI_API_KEY=$PHARMAPI_API_KEY
PHARMAPI_MOCK=$PHARMAPI_MOCK
PILOT_DOMAIN=$DOMAIN
ENVEOF
fi

log "Building + starting the stack..."
cd "$APP_DIR"
docker compose -f compose.prod.yaml --env-file .env.prod up -d --build

log "Migrating + seeding (seed authenticates once against live ΗΔΥΚΑ)..."
docker compose -f compose.prod.yaml --env-file .env.prod exec -T backend alembic upgrade head
docker compose -f compose.prod.yaml --env-file .env.prod exec -T backend python -m scripts.seed \
  || log "WARN: seed failed (ΗΔΥΚΑ creds/session?) — rerun manually once fixed."

# Live mode needs the national drug catalogue synced (brand→ATC/substance
# resolution for the safety engine); mock mode ships without it.
if [ "$PHARMAPI_MOCK" = "false" ]; then
  log "Live mode: syncing drug catalogue from ΗΔΥΚΑ masterdata (~1 min)..."
  docker compose -f compose.prod.yaml --env-file .env.prod exec -T backend \
    python -m scripts.seed_drug_catalog \
    || log "WARN: catalogue sync failed — rerun 'python -m scripts.seed_drug_catalog'."
fi

log "Done. Demo reachable at: https://$DOMAIN"
log "Point the agent at it:  PHARMASSIST_BACKEND_URL=https://$DOMAIN PHARMASSIST_WEBAPP_URL=https://$DOMAIN"
