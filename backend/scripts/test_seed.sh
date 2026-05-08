#!/usr/bin/env bash
# Manual seed diagnostic. Sources backend/.env (gitignored) so you don't
# have to retype PHARMAPI_PASSWORD on the command line where '!' might
# trip over shell history-expansion. Then runs the diagnostic inside the
# backend docker container with Python 3.13.
#
# Usage (from anywhere in the repo):
#     backend/scripts/test_seed.sh

set -euo pipefail

# Resolve repo root no matter where the script is invoked from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

if [[ ! -f backend/.env ]]; then
  echo "missing backend/.env — copy backend/.env.example and fill in:"
  echo "  CREDENTIAL_ENCRYPTION_KEY, PHARMAPI_USERNAME, PHARMAPI_PASSWORD"
  exit 1
fi

# Make sure the db container is up — `docker compose run backend` does
# NOT auto-start it (no depends_on declared), and step 5 of the
# diagnostic talks to Postgres at hostname `db` over the compose network.
# `up -d db` is idempotent: it's a no-op if db is already running.
echo "→ ensuring db service is running..."
docker compose up -d db >/dev/null

# Load env from .env. `set -a` exports every assignment that follows;
# `set +a` turns it back off. Source-loading reads values literally, so
# '!' is not expanded.
set -a
# shellcheck disable=SC1091
source backend/.env
set +a

# backend/.env is written for host-side use (DATABASE_URL points at
# localhost). Inside the container we need the compose service hostname.
DATABASE_URL_IN_CONTAINER='postgresql+asyncpg://pharmassist:pharmassist_dev@db:5432/pharmassist'

# Build -e flags only for env vars that are actually set & non-empty.
# Passing -e FOO="" clobbers the default in config.py with an empty
# string (and `os.getenv("FOO", "default")` returns "" because the var
# IS set), so we skip empties and let config.py's defaults take over.
docker_envs=(
  -e DATABASE_URL="$DATABASE_URL_IN_CONTAINER"
  -e CREDENTIAL_ENCRYPTION_KEY="${CREDENTIAL_ENCRYPTION_KEY:?missing in backend/.env}"
)
for var in PHARMAPI_USERNAME PHARMAPI_PASSWORD PHARMAPI_API_KEY; do
  val="${!var:-}"
  [[ -n "$val" ]] && docker_envs+=(-e "$var=$val")
done

exec docker compose run --rm "${docker_envs[@]}" backend python -m scripts.test_seed
