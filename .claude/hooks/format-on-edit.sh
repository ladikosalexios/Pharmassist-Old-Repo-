#!/usr/bin/env bash
# PostToolUse hook — runs the right formatter for the file the agent just
# edited, so anything written to disk already matches what CI expects.
#
# Reads the tool-call JSON on stdin, parses the file_path, dispatches:
#   .py                            → ruff format
#   .ts/.tsx/.js/.jsx/.json/.css   → prettier --write
#   .md/.yml/.yaml                 → prettier --write
#
# Exit policy:
#   - exits 0 silently on success
#   - exits 0 on formatter failure too (CI's format:check is the safety net;
#     blocking the agent on a formatter hiccup is more disruptive than
#     letting it continue and catching the issue in the Stop-gate)
#   - never exits non-zero — formatting is a quality-of-life convenience,
#     not a correctness gate

set -uo pipefail

# Parse file_path from the tool input without needing jq.
file_path="$(python3 - <<'PY'
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get("tool_input", {}).get("file_path", ""))
except Exception:
    pass
PY
)"

# Bail out cleanly if we can't identify a project file to format.
[[ -z "$file_path" ]] && exit 0
[[ "$file_path" != "$CLAUDE_PROJECT_DIR"* ]] && exit 0
[[ ! -f "$file_path" ]] && exit 0

ext="${file_path##*.}"

format_py() {
  # Prefer a host-side ruff (pip / pre-commit install). Fall back to the
  # running backend container so engineers without a local Python env still
  # get formatting.
  if command -v ruff >/dev/null 2>&1; then
    ruff format --quiet "$file_path" 2>&1 | head -5 || true
    return
  fi
  if docker compose ps --status=running backend >/dev/null 2>&1; then
    rel="${file_path#$CLAUDE_PROJECT_DIR/backend/}"
    docker compose exec -T backend ruff format --quiet "$rel" 2>&1 | head -5 || true
  fi
}

format_js() {
  # Prettier lives in frontend/node_modules. We never run npx because that
  # can trigger an install — silent npm churn during a hook is bad UX.
  local prettier_bin="$CLAUDE_PROJECT_DIR/frontend/node_modules/.bin/prettier"
  [[ ! -x "$prettier_bin" ]] && return
  (
    cd "$CLAUDE_PROJECT_DIR/frontend" || exit 0
    "$prettier_bin" --write --log-level=warn "$file_path" 2>&1 | head -5 || true
  )
}

case "$ext" in
  py)
    format_py
    ;;
  ts|tsx|js|jsx|json|css|md|yml|yaml)
    format_js
    ;;
  *)
    # Nothing to format for this extension. Stay silent.
    ;;
esac

exit 0
