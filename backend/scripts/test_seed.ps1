# Manual seed diagnostic for Windows / PowerShell.
# Mirror of test_seed.sh — same five jobs, same env-handling rules.
#
# Usage (from PowerShell, anywhere in the repo):
#     backend\scripts\test_seed.ps1
#
# If your execution policy blocks running .ps1 files, you can either:
#   - Run as: powershell -ExecutionPolicy Bypass -File backend\scripts\test_seed.ps1
#   - Or unblock once: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

$ErrorActionPreference = 'Stop'

# Resolve repo root no matter where the script is invoked from.
$ScriptDir = Split-Path -Parent $PSCommandPath
$RepoRoot  = (Resolve-Path (Join-Path $ScriptDir '..\..')).Path
Set-Location $RepoRoot

if (-not (Test-Path 'backend\.env')) {
    Write-Host 'missing backend/.env — copy backend/.env.example and fill in:' -ForegroundColor Red
    Write-Host '  CREDENTIAL_ENCRYPTION_KEY, PHARMAPI_USERNAME, PHARMAPI_PASSWORD'
    exit 1
}

# Make sure the db container is up — `docker compose run backend` does
# NOT auto-start it (no depends_on declared), and step 5 of the
# diagnostic talks to Postgres at hostname `db` over the compose network.
# `up -d db` is idempotent: it's a no-op if db is already running.
Write-Host '→ ensuring db service is running...'
docker compose up -d db | Out-Null

# Parse backend/.env into a hashtable. Single regex matches each
# non-comment KEY=VALUE line; trims whitespace around both sides.
$envVars = @{}
Get-Content 'backend\.env' | ForEach-Object {
    if ($_ -match '^\s*([^#=][^=]*)=(.*)$') {
        $envVars[$matches[1].Trim()] = $matches[2].Trim()
    }
}

# backend/.env is written for host-side use (DATABASE_URL points at
# localhost). Inside the container we need the compose service hostname.
$databaseUrlInContainer = 'postgresql+asyncpg://pharmassist:pharmassist_dev@db:5432/pharmassist'

# Build -e args. Skip empty values: passing -e FOO="" clobbers the
# default in config.py with an empty string (and `os.getenv("FOO", "default")`
# returns "" because the var IS set), so we let config.py's defaults
# take over for missing entries.
if (-not $envVars['CREDENTIAL_ENCRYPTION_KEY']) {
    Write-Host 'CREDENTIAL_ENCRYPTION_KEY missing in backend/.env' -ForegroundColor Red
    exit 1
}

$dockerEnvs = @(
    '-e', "DATABASE_URL=$databaseUrlInContainer",
    '-e', "CREDENTIAL_ENCRYPTION_KEY=$($envVars['CREDENTIAL_ENCRYPTION_KEY'])"
)
foreach ($var in @('PHARMAPI_USERNAME', 'PHARMAPI_PASSWORD', 'PHARMAPI_API_KEY')) {
    $val = $envVars[$var]
    if ($val) {
        $dockerEnvs += @('-e', "$var=$val")
    }
}

# Run the diagnostic inside the backend container.
& docker compose run --rm @dockerEnvs backend python -m scripts.test_seed
exit $LASTEXITCODE
