# Verify PharmAssist

From this checkout or worktree, run:

```sh
python3 scripts/verify.py
```

The runner never installs dependencies, starts the application or Compose stack, calls the
live seed, launches agents, or publishes changes. It runs trusted repository code as your
local user; it is not an operating-system sandbox. Use Python 3.9+ to launch it, Python 3.13
for the backend, and Node 22 for the frontend (matching CI).

## Dependencies belong to each worktree

Prepare these explicitly, once, in the worktree you will verify:

```sh
python3.13 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt
cd frontend
npm ci
```

The runner uses `backend/.venv/bin/python` when present, otherwise its own interpreter.
`--python /absolute/path/to/python` selects a different backend interpreter. Missing tools
fail the corresponding check; there is no silent installation or fallback to a running container.
Do not symlink another worktree's mutable dependencies. No provider credentials are needed.

## Coverage and exits

The default runs:

- Harness and hook regression tests, using temporary synthetic repositories.
- Backend and tooling Ruff lint and format checks.
- The same DB-less backend pytest selection as CI, with skip reasons printed.
- Frontend typecheck, ESLint, Prettier check, Vitest, and a production build to a temporary output directory.

Ruff discovers configuration by file location. `scripts/ruff.toml` inherits the backend rules
with explicit source roots and a Python 3.9 target; backend code retains its Python 3.13 target.
This keeps imports and formatting consistent between hooks, pre-commit, and the runner,
including when invoked from another working directory.

CI calls the same entry point with `--backend-only` and `--frontend-only`. The optional
`--quick` mode runs lint/format/typecheck and tooling regressions; it explicitly excludes
application tests and builds. Stop hooks use this narrower mode, not a full test gate.

CI also covers pull requests targeting `fix/track-claude-md`, the existing instructions
branch this work depends on. Retarget the harness PR to `main` after that dependency lands.
The Claude review workflow skips drafts; moving a PR out of draft can launch a paid review.

The final coverage summary distinguishes PASS, FAIL, EXCLUDED and NOT RUN. A failed check
returns nonzero; interruption returns 130. Exclusions are never represented as passed tests.
No Electron packaging, deployed-service smoke, live Pharmapi/LLM/EOF/EMA checks, or browser
acceptance tests are included. This command does not establish release readiness by itself.

## Database suites: opt into an isolated cluster

```sh
python3 scripts/verify.py --with-db
# Or only backend, using an installed PostgreSQL tool directory:
python3 scripts/verify.py --backend-only --with-db --pg-bin /path/to/postgresql/bin
```

Install PostgreSQL tools separately: `initdb`, `pg_ctl`, `createdb`, and `psql`. Version 16
matches Compose. They must be on PATH or supplied via `--pg-bin`. The runner creates a new
cluster under a private `/tmp/pa-verify-*` directory, disables TCP listening, uses a private
Unix socket and a dedicated `pharmassist_verify` database, and stops it in a `finally` block.
It does not accept an existing database URL, inspect the developer's DB, or use production data.
Migrations run with `alembic upgrade head`; minimal synthetic pharmacist/pharmacy rows supply
foreign keys. One catalog entry and one rule are reused from the repository's existing
constants-only `seed_data.py` to satisfy tenant-isolation and credential-less tests. No
patient fixtures or live seed routines are imported.
**Never run `python -m scripts.seed` for verification**: that seed calls Pharmapi and truncates
tables. Database modules run in separate processes to avoid the application's
shared async connection pools and test dependency overrides leaking between modules.

Without `--with-db`, these seven modules are explicitly excluded:

- `test_endpoints_integration.py`
- `test_v1_tenant_isolation.py`
- `test_b2b_admin_audit.py`
- `test_ai_cache_db.py`
- `test_v1_safety_explain_cache_db.py`
- `test_spc_ingest_api.py`
- `test_v1_retrieval_free_db.py`

Even DB-less tests receive a private nonexistent socket URL, so an accidental database access
fails instead of reaching localhost's dev server. Subprocesses receive synthetic credentials,
mock provider flags, disabled background fetches/telemetry and no inherited database/provider
secrets or pytest options. The backend bootstrap disables dotenv loading before app imports,
including on python-dotenv versions predating its disable environment variable. Tests can
still override flags deliberately; those test seams are trusted code, not a network sandbox.
Normal failure and interruption trigger cleanup; uncatchable termination may leave the private
cluster behind. If cleanup fails, the runner retains its directory and reports the path.
Inspect that exact run directory before cleanup; never stop unrelated servers.

## Portable instructions and hooks

`AGENTS.md` is a regular tracked entry point that directs Codex to shared `CLAUDE.md` and this
guide. It works even where Git symlinks are disabled. `.agents/skills/` uses relative symlinks
to the existing canonical `.claude/skills/` directories rather than divergent copied skills;
on systems without symlink support, consult `.claude/skills/` directly.

Both `.claude/settings.json` and `.codex/hooks.json` use the current Git worktree root, then
invoke a small wrapper that resolves its own location and calls `scripts/agent_hooks.py`.
There are no personal absolute paths and no dependency on `CLAUDE_PROJECT_DIR`. The shared
formatter reads actual hook JSON from stdin, safely handles paths containing spaces, and
rejects resolved paths outside its worktree. Shell/apply_patch edits without a single
`file_path` are left for verification. Formatting is advisory; failures are reported.
The Stop hook checks tracked/staged/untracked work, runs appropriate quick checks, and returns
2 when checks fail or cannot run. A repeated Stop (`stop_hook_active`) allows the agent
to report the failure without an endless retry loop; it emits an explicit message that this
is not a verification pass. No relevant edits means an explicit skip message.

Codex loads project hooks only for trusted projects and requires trust of each hook definition;
see the [official hook documentation](https://learn.chatgpt.com/docs/hooks). This change does
not modify trust records, bypass approval, or launch either agent. Test the scripts directly
with synthetic events before enabling them. Do not assume installation means execution.

The original checkout's untracked `.codex/` and `.agents/` files were inspected. Its Codex
config declares local Ollama/Milvus MCP dependencies; it remains personal and is ignored.
Copied reviewer presets (including an Antigravity preset) remain personal rather than
silently becoming team instructions. The shared hooks are recreated from reviewed source,
and skills reference already tracked canonical content; no personal settings or credentials
are imported. The original checkout's files are left untouched. To use these changes there,
review that local untracked configuration before merging/checking out a branch that tracks
the same paths; never overwrite it or force the checkout.

### Existing checkout collision plan

The reviewed original checkout has eight local files. Their disposition is:

| Existing path | Shared replacement or preservation |
| --- | --- |
| `.agents/skills/audit-log/` | Replace the copied directory with a relative link to the identical canonical skill. |
| `.agents/skills/screen-convert/` | Replace the copied directory with a relative link. Its only local difference was a stale `.Codex` hook path; the canonical skill now describes the shared hook and manual checks. |
| `.codex/hooks.json` | Replace two absolute hook commands with worktree-relative commands; keep both events and existing matchers, adding `apply_patch`. |
| `.codex/hooks/format-on-edit.sh` | Replace the copied legacy formatter with the shared wrapper; preserve the formatting intent and fix stdin/worktree handling. |
| `.codex/hooks/typecheck-on-stop.sh` | Replace the copied legacy gate with the shared wrapper; report missing tools/failures and bound repeated blocking. |
| `.codex/config.toml` | Keep local, byte-for-byte; ignored and absent from the proposed tracked files. |
| `.codex/agents/code-reviewer.toml` | Keep local, byte-for-byte; ignored and absent from the proposed tracked files. |
| `.codex/agents/antigravity-reviewer.toml` | Keep local, byte-for-byte; ignored and absent from the proposed tracked files. |

The personal files are not copied into other worktrees automatically. Their absence there
does not prevent shared verification. Keeping them in the original checkout preserves the
user's settings without making them team defaults. No differing personal setting needs to
be dropped or selected to integrate this change.

Before any future integration into that checkout:

1. Obtain approval for the actual branch integration and collision relocation. This plan
   does not perform either action. Preserve the original branch and commit as the rollback
   target; independently commit/review the harness changes before attempting integration.
2. Recheck the current files against the verified private backup. If anything has changed,
   make a fresh backup and review the delta. Never use an old snapshot to overwrite newer
   settings or pending work. Keep the backup outside all repositories, accessible only to
   the owner; preserve file modes and symlinks and verify hashes and metadata.
3. Relocate only the first five collision paths above into a new private holding directory
   outside the checkout, preserving their relative paths. Move each whole skill directory,
   not only its `SKILL.md`. Leave the personal config, both reviewer presets, and any other
   untracked files in place. Record every successful move so a partial operation is reversible.
4. Integrate the reviewed commit without a forced checkout, `git clean`, or hard reset.
   If Git reports another collision or tracked work conflict, stop and preserve it. Verify
   that the three personal files still match their pre-integration hashes and modes and are
   ignored rather than tracked. Check that both skill links resolve within this checkout.
5. Run `python3 scripts/verify.py --quick` using this checkout's own dependencies; then run
   the full intended checks. Review changed hook trust through the agent's normal workflow;
   do not copy trust records or assume the hooks are activated.

Rollback: first preserve any changes made after integration. Reverse the integration using
the recorded commit/branch and normal Git operations; never force away pending work. After
the newly tracked collision paths are absent, move the originals back from the holding
directory, creating missing parent directories as needed. Verify their contents, modes,
and symlink targets against the private manifest. Leave the personal config and presets
in place throughout. If a destination is occupied, stop and compare it rather than overwrite.
For a partially completed relocation, restore only the recorded moves. Retain the verified
backup until integration and rollback recovery have been accepted.

This sequence was rehearsed in a disposable Git checkout with synthetic personal settings:
Git rejected the initial collisions without loss, relocating the five paths allowed checkout,
the three personal files remained ignored and untracked, both skill links resolved, and
rollback restored all eight original file contents and modes. Actual personal configuration
was not placed in the test repository. The eight real local files and seven directories were
separately backed up outside Git and verified against the originals, including ownership,
modes and timestamps. After the documentation reconciliation, the 14 tooling regressions
and all `--quick` lint/format/typecheck checks passed. Application tests and builds were not
rerun for this documentation-only follow-up; the full-run results below remain the prior run.

## Validation of this change

`python3 scripts/verify.py --with-db` completed with exit 0 in the isolated worktree:

- 14 harness regressions, 422 DB-less backend tests, and 51 database tests passed.
- One existing test remains skipped: `GET /pharmapi/errors`, awaiting the T8 implementation.
- Backend/tooling lint and formatting, fresh migrations, frontend typecheck/lint/format,
  eight frontend tests, and production build passed.
- Both providers' registered hook commands passed from a nested directory without
  `CLAUDE_PROJECT_DIR`. The formatter regression also exercises a path containing spaces.
- A native SIGTERM check returned 130, stopped its private PostgreSQL server, and removed
  the cluster directory. The normal full run also stopped and removed its cluster.

Local versions were Python 3.13.15, PostgreSQL 14.18 and Node 23.11.0. PostgreSQL 16
(Compose) and Node 22 (CI) parity remains unverified. Frontend dependencies were copied into
the isolated worktree from the existing local installation; this was not a fresh `npm ci`
validation. The initial local validation did not run hosted CI or activate actual agent hooks;
consult the PR's exact-commit checks for subsequent CI results. Independent read-only review
found no remaining blocking findings. These results do not include the release checks excluded
above.
