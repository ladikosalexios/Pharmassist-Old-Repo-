#!/usr/bin/env bash
#
# EC2 user-data bootstrap — PharmAssist internal pilot, Tailscale-only.
# Target AMI: Amazon Linux 2023. Runs as root on first boot (cloud-init).
#
# What it does:
#   1. Installs Docker + the Compose plugin + Tailscale.
#   2. Joins the tailnet (auth key from SSM) and derives the box's MagicDNS name.
#   3. Clones the repo and assembles .env.prod from SSM Parameter Store.
#   4. Brings up compose.prod.yaml with Caddy's internal TLS (CADDY_TLS="tls internal").
#
# It does NOT migrate or seed — the seed needs a live ΗΔΥΚΑ session, so that
# stays a deliberate manual step (see docs/pilot-runbook.md §3 + §12).
#
# Prereqs (one-time, before launch) are in docs/pilot-runbook.md §12:
#   • an IAM instance role with ssm:GetParameter (+ kms:Decrypt) on the prefix
#   • secrets stored as SSM SecureString params under $SSM_PREFIX
#   • a Tailscale auth key stored at $SSM_PREFIX/TS_AUTHKEY
#   • a GitHub read-only fine-grained PAT at $SSM_PREFIX/GH_PAT (repo is private)
set -euo pipefail

# ── CONFIG — edit before pasting into the launch wizard ───────────────────────
REPO_URL="https://github.com/ladikosalexios/Pharmassist.git"
REPO_REF="main"
APP_DIR="/opt/pharmassist"
TS_HOSTNAME="pharmassist-pilot"        # tailnet machine name testers will use
SSM_PREFIX="/pharmassist/pilot"        # SecureString params live under here
COMPOSE_VERSION="v2.32.4"              # pinned for reproducible boots
# ──────────────────────────────────────────────────────────────────────────────

log() { echo "[bootstrap] $(date -u +%H:%M:%S) $*"; }

# Region from IMDSv2 (no hard-coding — the script follows the instance).
TOKEN="$(curl -sX PUT 'http://169.254.169.254/latest/api/token' \
  -H 'X-aws-ec2-metadata-token-ttl-seconds: 300')"
AWS_REGION="$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/placement/region)"
log "Region: $AWS_REGION"

log "Installing Docker, git, dnf plugins..."
dnf -y update
dnf -y install docker git dnf-plugins-core
systemctl enable --now docker
usermod -aG docker ec2-user || true   # so SSM/SSH logins can run docker sans sudo

log "Installing the Docker Compose plugin ($COMPOSE_VERSION)..."
install -d /usr/libexec/docker/cli-plugins
curl -fsSL \
  "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)" \
  -o /usr/libexec/docker/cli-plugins/docker-compose
chmod +x /usr/libexec/docker/cli-plugins/docker-compose

log "Installing Tailscale..."
dnf config-manager --add-repo https://pkgs.tailscale.com/stable/amazon-linux/2023/tailscale.repo
dnf -y install tailscale
systemctl enable --now tailscaled

# aws CLI v2 ships with AL2023; guard just in case.
command -v aws >/dev/null || dnf -y install awscli

ssm() { aws ssm get-parameter --with-decryption --region "$AWS_REGION" \
  --name "$SSM_PREFIX/$1" --query Parameter.Value --output text; }

log "Joining the tailnet as $TS_HOSTNAME..."
TS_AUTHKEY="$(ssm TS_AUTHKEY)"
tailscale up --authkey "$TS_AUTHKEY" --hostname "$TS_HOSTNAME" --ssh

# Full MagicDNS name → Caddy site address + internal-cert SAN. Retry until set.
MAGICDNS=""
for _ in $(seq 1 15); do
  MAGICDNS="$(tailscale status --json \
    | python3 -c 'import sys,json; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))' 2>/dev/null || true)"
  [ -n "$MAGICDNS" ] && break
  sleep 2
done
[ -n "$MAGICDNS" ] || { log "ERROR: could not resolve MagicDNS name"; exit 1; }
log "MagicDNS: $MAGICDNS"

log "Cloning $REPO_URL@$REPO_REF -> $APP_DIR (private repo; token from SSM)..."
GH_PAT="$(ssm GH_PAT)"
# Inject the token only for the network op; never leave it in .git/config.
AUTH_URL="https://x-access-token:${GH_PAT}@${REPO_URL#https://}"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch --depth 1 "$AUTH_URL" "$REPO_REF"
  git -C "$APP_DIR" reset --hard FETCH_HEAD
else
  git clone --branch "$REPO_REF" --depth 1 "$AUTH_URL" "$APP_DIR"
  git -C "$APP_DIR" remote set-url origin "$REPO_URL"   # scrub token from stored remote
fi
unset GH_PAT AUTH_URL

log "Fetching secrets from SSM ($SSM_PREFIX/*)..."
SECRET_KEY="$(ssm SECRET_KEY)"
CREDENTIAL_ENCRYPTION_KEY="$(ssm CREDENTIAL_ENCRYPTION_KEY)"
POSTGRES_PASSWORD="$(ssm POSTGRES_PASSWORD)"
PHARMAPI_USERNAME="$(ssm PHARMAPI_USERNAME)"
PHARMAPI_PASSWORD="$(ssm PHARMAPI_PASSWORD)"
PHARMAPI_API_KEY="$(ssm PHARMAPI_API_KEY)"
# HMVS (EU-FMD) OAuth2 client-credentials + IQE base URLs. The Client Secret is
# the only true secret of the four; URLs and Client ID are not, but they live in
# SSM next to the secret so a host rotation (api-gr-iqe → api-gr → …) is a single
# put-parameter, not a code change. All four use SecureString uniformly.
HMVS_IDENTITY_URL="$(ssm HMVS_IDENTITY_URL)"
HMVS_VERIFICATION_URL="$(ssm HMVS_VERIFICATION_URL)"
HMVS_CLIENT_ID="$(ssm HMVS_CLIENT_ID)"
HMVS_CLIENT_SECRET="$(ssm HMVS_CLIENT_SECRET)"

log "Writing .env.prod (mode 600)..."
umask 077
cat > "$APP_DIR/.env.prod" <<ENVEOF
SECRET_KEY=$SECRET_KEY
CREDENTIAL_ENCRYPTION_KEY=$CREDENTIAL_ENCRYPTION_KEY
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
PHARMAPI_USERNAME=$PHARMAPI_USERNAME
PHARMAPI_PASSWORD=$PHARMAPI_PASSWORD
PHARMAPI_API_KEY=$PHARMAPI_API_KEY
HMVS_CLIENT_ID=$HMVS_CLIENT_ID
HMVS_CLIENT_SECRET=$HMVS_CLIENT_SECRET
HMVS_IDENTITY_URL=$HMVS_IDENTITY_URL
HMVS_VERIFICATION_URL=$HMVS_VERIFICATION_URL
HMVS_MOCK=false
PILOT_DOMAIN=$MAGICDNS
CADDY_TLS=tls internal
ENVEOF

log "Building + starting the stack..."
cd "$APP_DIR"
docker compose -f compose.prod.yaml --env-file .env.prod up -d --build

log "Stack is up. Remaining MANUAL steps (need a live ΗΔΥΚΑ session — see runbook §3):"
log "  docker compose -f compose.prod.yaml --env-file .env.prod exec backend alembic upgrade head"
log "  docker compose -f compose.prod.yaml --env-file .env.prod exec backend python -m scripts.seed"
log "Testers reach the pilot at: https://$MAGICDNS"
