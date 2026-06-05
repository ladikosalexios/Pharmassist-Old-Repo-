#!/usr/bin/env bash
# Stop hook — re-runs the same checks CI runs, but only when there are
# uncommitted changes that could break them. Exit code 2 blocks the agent
# from stopping and feeds stderr back into context, so a "done" claim
# can't slip through with a red CI.
#
# Why guarded by diff: typecheck (~8s), ruff (~2s), eslint (~4s),
# prettier --check (~2s). Running on every Stop — including pure-
# conversation turns with no edits — adds 15s of latency for nothing.
#
# The four CI commands mirrored here:
#   backend  → ruff check
#   frontend → npm run typecheck, npm run lint, npm run format:check

set -uo pipefail

cd "$CLAUDE_PROJECT_DIR" || exit 0
git rev-parse --git-dir >/dev/null 2>&1 || exit 0

# Detect changed files across working tree + staged + untracked.
changed="$(
  {
    git diff --name-only HEAD 2>/dev/null
    git diff --cached --name-only 2>/dev/null
    git ls-files --others --exclude-standard 2>/dev/null
  } | sort -u
)"

needs_frontend=0
needs_backend=0
echo "$changed" | grep -qE '^frontend/.*\.(ts|tsx|js|jsx|css|json|md|yml|yaml)$' && needs_frontend=1
echo "$changed" | grep -qE '^backend/.*\.py$' && needs_backend=1

# Pure-conversation turn — no relevant edits. Let the agent stop instantly.
[[ $needs_frontend -eq 0 && $needs_backend -eq 0 ]] && exit 0

errors=""

# ── Backend: ruff check ────────────────────────────────────────────────
if [[ $needs_backend -eq 1 ]]; then
  if command -v ruff >/dev/null 2>&1; then
    if ! ruff_out="$(cd backend && ruff check . 2>&1)"; then
      errors+="── ruff check ──
$ruff_out

"
    fi
  elif docker compose ps --status=running backend >/dev/null 2>&1; then
    if ! ruff_out="$(docker compose exec -T backend ruff check . 2>&1)"; then
      errors+="── ruff check (via container) ──
$ruff_out

"
    fi
  fi
fi

# ── Frontend: typecheck + lint + format:check ──────────────────────────
if [[ $needs_frontend -eq 1 && -d frontend/node_modules ]]; then
  if ! tc_out="$(cd frontend && npm run typecheck --silent 2>&1)"; then
    errors+="── npm run typecheck ──
$tc_out

"
  fi
  if ! lint_out="$(cd frontend && npm run lint --silent 2>&1)"; then
    errors+="── npm run lint ──
$lint_out

"
  fi
  if ! fmt_out="$(cd frontend && npm run format:check --silent 2>&1)"; then
    errors+="── npm run format:check ──
$fmt_out
(Tip: \`npm run format\` rewrites in place.)

"
  fi
fi

if [[ -n "$errors" ]]; then
  cat <<EOF >&2
Pre-stop checks failed. Fix these before claiming the work is done — CI
runs the same commands and will block any PR.

$errors
EOF
  exit 2
fi

exit 0
