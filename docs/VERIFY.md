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

CI calls the same entry point with `--backend-only` and `--frontend-only`, and runs
`--backend-only --with-db` against the runner image's PostgreSQL 16 (Compose's major version). The optional
`--quick` mode runs lint/format/typecheck and tooling regressions; it explicitly excludes
application tests and builds. Stop hooks use this narrower mode, not a full test gate.

CI also covers pull requests targeting `fix/track-claude-md`, the existing instructions
branch this work depends on. Retarget the harness PR to `main` after that dependency lands.
The Claude review workflow skips drafts; moving a PR out of draft can launch a paid review.

### Claude automated review evidence

`.github/workflows/claude-code-review.yml` checks out the event's PR head SHA and
requests a structured attestation with the reviewed head/base SHAs and findings count.
The reviewer must check those revisions before and after review. `scripts/review_evidence.py`
writes a bounded Actions summary using only validated SHAs, counts and fixed reason labels:

- **COMPLETED (model reported)** requires a successful action and a completion attestation
  matching both event revisions. This is model-reported evidence, not independent proof.
- **SKIPPED** identifies a draft without launching the paid action; **SKIPPED (model reported)**
  identifies an explicit reviewer skip or a changed revision.
- **FAILED** identifies action failure. **UNVERIFIED** covers absent, malformed, inconsistent
  or stale attestations, even when the action exits successfully.

The summary reports evidence; it does not implement an approval or merge gate. A green job
alone is not a completed review. Findings remain in Actions; the workflow requests no
GitHub comments or reviews. See the upstream
[action outputs](https://github.com/anthropics/claude-code-action/blob/main/action.yml).

The repository now owns the review procedure: existing Claude comments never suppress a
review. An exact Actions cache key includes the PR number and both event SHAs; no prefix
restores are used. `scripts/review_checkpoint.py` also validates the restored completion
record against the repository, PR and revisions. Only a validated **COMPLETED** report is
saved after the findings artifact uploads successfully. Findings are cached with a verified
digest and re-uploaded on reuse; absent or changed findings force a fresh review. **REUSED (prior model attestation)** explicitly identifies a prior completed run,
rather than claiming the model ran again. Failed, skipped or unverified reports never create
a completion record. Caches are best effort: eviction, expiry or restore failure means a
fresh review. Bump the cache key version when changing review policy so older evidence is
not reused under a different procedure. A rerun uses the original event revisions; a new
head/base pair is reviewed when a new PR event is received. Base advancement alone does not
trigger this pull-request workflow.

The procedure reviews tooling and documentation too, asks four independent agents for
concrete defects, checks candidates against source, and rechecks live PR state/revisions
before attesting completion. Credentials and permissions remain unchanged. Findings are
bounded structured JSON in the run's Actions artifact (14-day retention), with relative
file paths and line numbers; they are never posted to a PR or interpolated into the summary.
The reporter reads the action's execution file (not a report-sized environment variable),
extracts only the final successful structured result, and rejects count mismatches, malformed
or oversized findings and unsafe paths.
No raw execution transcript is dumped. Completion remains model evidence, not approval.

The headless reviewer explicitly approves source reads, review agents and the two read-only
shell commands `gh pr view` and `gh pr diff`; edit/write tools are removed. This CI tool
configuration leaves GitHub token permissions and local project/hook trust unchanged.
An unapproved tool request still fails rather than being silently treated as review success.

A PR changing this workflow cannot exercise its new model step until the workflow is merged:
Anthropic's action validates that the workflow matches the default branch. Such a green run
can report **UNVERIFIED**, and must not be described as a completed review. Validate actual
execution on a subsequent ordinary PR, then rerun that exact event to verify reuse. Do not
bypass workflow validation or grant broader token access to make a test run.

Offline regressions use synthetic events/reports and execute the provider hook adapters in
temporary repositories. They establish neither paid-review execution nor lifecycle hook
activation; project/hook trust still requires the user's normal review.

The final coverage summary distinguishes PASS, FAIL, EXCLUDED and NOT RUN. A failed check
returns nonzero; interruption returns 130. Exclusions are never represented as passed tests.
Test steps read their result report rather than trusting the exit code alone: a passing step
shows its counts, for example `PASS (421 passed, 1 skipped)`, and pytest's `-ra` output above
the summary gives each skip reason. A step whose tests were all skipped is
`NOT RUN: 0 passed, N skipped` and fails verification; a missing report is a failure.
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
foreign keys. They are loaded with `psql -X`: without it, psql reads the installation's
`psqlrc`, the account's `~/.psqlrc` (the runner keeps `HOME`, and PostgreSQL 14 locates the
file through the password database anyway) or `PSQLRC`. Such a file can `\connect` to another database or
turn `AUTOCOMMIT` off, sending the fixtures elsewhere or rolling them back while psql still
exits 0. With `--with-db`, the harness regressions also run a real-psql test against their own
disposable cluster with a synthetic startup file; without it that test is reported as skipped.
One catalog entry and one rule are reused from the repository's existing
constants-only `seed_data.py` to satisfy tenant-isolation and credential-less tests. No
patient fixtures or live seed routines are imported.
**Never run `python -m scripts.seed` for verification**: that seed calls Pharmapi and truncates
tables. Database modules run in separate processes to avoid the application's
shared async connection pools and test dependency overrides leaking between modules.

Without `--with-db`, these eight modules are explicitly excluded:

- `test_endpoints_integration.py`
- `test_v1_tenant_isolation.py`
- `test_b2b_admin_audit.py`
- `test_ai_cache_db.py`
- `test_v1_safety_explain_cache_db.py`
- `test_spc_ingest_api.py`
- `test_v1_retrieval_free_db.py`
- `test_yellow_cards_db.py`

### Yellow Card suite

`test_yellow_cards_db.py` is opt-in: it skips itself unless `YELLOW_TEST_DATABASE_URL` is
set. With `--with-db` it runs last, in its own process, after migrations, fixtures and the
other seven suites, against the same private `pharmassist_verify` database. Its fixtures add
their own synthetic pharmacies, pharmacists and reports and cancel other queued Yellow
submissions, but never reset the schema, so it does not need a separate database. If its
fixtures ever become destructive, give it its own freshly migrated private database instead.

- Only this suite receives `YELLOW_TEST_DATABASE_URL`, and only as a copy of the run's own
  private `DATABASE_URL`. A caller's exported `YELLOW_TEST_DATABASE_URL` or `DATABASE_URL` is
  never inherited, and no `.env` file is loaded. If the URL is not the private cluster's, the
  suite fails as unusable configuration rather than running.
- Any skip fails verification: one skipped test, the module skipping itself, zero collected
  tests or a missing report. In other suites some skipped tests still pass (a suite where every
  test skipped does not), so the known pending `GET /pharmapi/errors` skip in
  `test_endpoints_integration.py` stays a separate `PASS (… 1 skipped)`.
- Email never leaves the process. The tests replace the SMTP transport with an in-memory
  capture, and the suite also gets `YELLOW_CARDS_MODE=disabled`, so the real transport refuses
  to send. That transport only knows the Compose-internal `mailpit` host anyway. There is no
  live SMTP, EOF delivery or other external service, and all data is synthetic.

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

Both providers invoke a small wrapper that resolves its own location and calls
`scripts/agent_hooks.py`; there are no personal absolute paths. How the wrapper is found
differs, because the providers run hooks differently:

- **Claude Code** runs hooks in the agent's current directory, which follows `cd`. Resolving
  the wrapper from that directory's Git root would run another repository's
  `.claude/hooks/` scripts after a `cd` into it, and would fail with exit 2 outside Git,
  before the repeat-stop guard could run. `.claude/settings.json` therefore uses the quoted
  `"$CLAUDE_PROJECT_DIR"`, the trusted project. If that variable is missing, the hook reports
  a non-blocking failure (exit 1) instead of silently doing nothing.
- **Codex** sets no project variable and runs hooks in the session directory its project hooks
  were loaded for, so `.codex/hooks.json` uses that directory's Git root. If the lookup fails,
  the hook reports a non-blocking failure (exit 1) rather than exit 2, which Codex would turn
  into a Stop continuation with no loop limit.

`scripts/agent_hooks.py` follows the hook input's `cwd` only into worktrees registered with
this repository (`git worktree list`), including ones nested under `.claude/worktrees/`, and
runs that worktree's own checks and dependencies. Treat every registered worktree's code as
trusted: a worktree checked out on an untrusted branch has its `verify.py`, npm scripts and
formatter config run on Stop or Edit. Any other directory, including another repository, one
outside Git or one whose planted `.git` file points at this repository, falls back to the
trusted project.

The shared formatter reads actual hook JSON from stdin and safely handles paths containing
spaces. It formats only what pre-commit formats: Ruff with `--force-exclude` for `backend/` and
`scripts/` (so Ruff's own excludes, such as migrations, still apply), Prettier for `frontend/`
(excluding `node_modules/`, `dist/` and `build/`). Repository docs, workflows
and other files are left as written, because CI does not check them and the frontend Prettier
config would rewrite them. Files outside this repository's worktrees, such as agent memory or
scratch files, are skipped without an error. Shell/apply_patch edits without a single
`file_path`, which includes every Codex edit, are left for verification. Formatting is
advisory; formatter failures are reported.

The Stop hook checks tracked/staged/untracked work, runs appropriate quick checks, and returns
2 when checks fail or cannot run. Changes to agent hook or instruction wiring (`.claude/`,
`.codex/`, `.agents/`, `.github/workflows/`, `CLAUDE.md`, `AGENTS.md`) run the harness regressions
that cover it. New
files under `.claude/hooks/` and `.claude/skills/` are visible to Git and to this check;
`.gitignore` keeps the rest of `.claude/` local (settings.local.json, worktrees, session
state, and agent presets other than the listed shared ones). The
runner's log never goes to stdout, because Codex marks a Stop hook that exits 0 with non-JSON
stdout as failed; on failure, the log's tail with the coverage summary goes to stderr. A
repeated Stop (`stop_hook_active`) allows the agent to report the failure without an endless
retry loop; it emits an explicit message that this is not a verification pass. No relevant
edits means an explicit skip message.

Registration is not activation; check both before relying on these hooks. The behaviour
below was observed live on 2026-10-07 with Claude Code 2.1.286 and Codex CLI 0.162.0-alpha.2:

- **Claude Code** reads the shared `.claude/settings.json` only from the session's primary
  working directory. A session started at the worktree root ran both hooks: the formatter
  rewrote an edited frontend file, and the Stop hook blocked once on a type error, fed the
  error back, then let the repeated stop finish with its "not a verification pass" message.
  A session started in `frontend/` ran neither hook, although it still loaded `CLAUDE.md`,
  which therefore tells such sessions to run `python3 scripts/verify.py` themselves. A
  `cd` outside the project is reset unless the directory was added as a working directory
  (`--add-dir`); with one added, the previous hook command ran that directory's own
  `.claude/hooks/` script after a `cd`, and the current one does not. In a worktree, Claude
  Code also applies the main checkout's `.claude/settings.local.json` permissions.
- **Codex** enables hooks by default (`codex features list`: `hooks stable true`) and
  discovers `.codex/` layers from a subdirectory up to the project root. It loads project
  hooks only for trusted projects, and lists a hook that has not been reviewed as untrusted;
  untrusted hooks are skipped until reviewed in `/hooks`. Per the Codex source, trust is
  recorded against each hook's hash, so changing a hook needs another review (not observed
  live). A project that is not trusted in `~/.codex/config.toml` gets no project hooks at all. In a linked
  worktree, Codex takes hook definitions from the main checkout's `.codex/hooks.json`, not
  the worktree's: until the main checkout carries this file, its own local file decides what
  runs in every worktree. With project and hook trust granted for one run, a Codex edit in a
  fresh clone (without dependencies) answered "DONE", then "BLOCKED" (the reply it was told to
  give if a hook reported a failure), and then finished rather than looping. Codex's JSON
  output and local logs did not record the hook run itself, so this is indirect evidence.

To see what Codex will load without starting a model session, call the app server's
`hooks/list` method for the directory: it reports each hook's source file, timeout and trust
status. Do not grant one-off project trust with `codex exec -c 'projects."<path>".trust_level=…'`:
Codex 0.162 wrote that override into `~/.codex/config.toml`.

See the [Claude Code hooks reference](https://code.claude.com/docs/en/hooks) and the
[Codex hook documentation](https://learn.chatgpt.com/docs/hooks). The repository does not
modify trust records or bypass approval. Test the scripts directly with synthetic events
before enabling them. Do not assume installation means execution.

### Start a session with the shared hooks

After integrating the tracked configuration, start a new provider session at the checkout
or worktree root so it loads the current definitions.

1. In Codex, open `/hooks`. Check that the project definitions come from the main checkout's
   `.codex/hooks.json`, and that PostToolUse and Stop are enabled and trusted. If a definition
   is untrusted or modified, inspect its command and approve it through this normal interface.
   Each contributor reviews their own trust state; pulling Git changes does not grant trust.
2. In Claude Code, start at the repository root and complete any normal workspace trust
   prompt. Open `/hooks` to inspect PostToolUse and Stop from `.claude/settings.json`.
   The commands use the quoted `$CLAUDE_PROJECT_DIR`; local settings can override or disable
   hooks, so check the effective configuration if an event does not run.
3. Run `python3 scripts/verify.py --quick` from that checkout using its own dependencies.
   This establishes check readiness. To establish lifecycle execution, use a disposable
   synthetic edit in a normal provider session and record the formatter/Stop response.
   Remove the fixture afterward. A direct wrapper invocation or a passing manual verifier
   is adapter evidence; neither establishes that the provider emitted the lifecycle event.

Codex's read-only app-server `hooks/list` can establish discovery, enabled state and trust
without starting a model session. It does not grant trust or demonstrate execution. A
successful edit hook does not establish that Stop ran; record the two events separately.

The original checkout's untracked `.codex/` and `.agents/` files were inspected. Its Codex
config declares local Ollama/Milvus MCP dependencies; it remains personal and is ignored.
Copied reviewer presets (including an Antigravity preset) remain personal rather than
silently becoming team instructions. The shared hooks are recreated from reviewed source,
and skills reference already tracked canonical content; no personal settings or credentials
are imported. For an older checkout, review local untracked configuration before
merging/checking out a branch that tracks the same paths. Preserve the conflicting files
before integration.

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

### Local integration evidence, 2026-10-10

The owner selected integration into the existing `codex/yellow-card-local-capture` branch.
A fresh owner-only backup outside Git preserved the five collision paths, three personal
Codex files and Claude local settings, with a hash/metadata manifest and every relocation
recorded. The original `58561c5` commit remains reachable on a rollback branch.

Main through #187 was merged locally. The two add/add conflicts contained only newer
verification guidance: `58561c5` and its already-merged squash have identical Git trees,
so the reviewed main versions preserved the Yellow Card implementation. The three personal
Codex files and Claude local settings retained their hashes, modes and timestamps and remain
ignored. Both canonical skill links resolve within the checkout.

Verification used this checkout's own dependencies: 47 tooling regressions, 429 DB-less
backend tests, 55 isolated database tests plus the existing `/pharmapi/errors` skip,
23 frontend tests, lint/format/typecheck and build passed. Local PostgreSQL was 14; the
shared CI separately uses 16. Only synthetic fixtures and the private socket cluster ran.

Read-only inspection with Codex CLI 0.162.0-alpha.17.2 reported both project hooks enabled
and trusted in the original checkout and linked worktree, using the main checkout's source,
with no errors or warnings. Claude's existing workspace trust was accepted and its local
settings contained no hook override or disable flag. No trust/configuration was changed.
These observations establish readiness; this integration did not run a new model session
to observe lifecycle execution. The prior live observations above and synthetic adapter
regressions remain distinct evidence.

## Validation of this change

These results come from the review follow-up and the end-to-end audit (2026-10-07), in the
isolated worktree.

**Passed.** `python3 scripts/verify.py --with-db` exited 0:

- **Harness:** 33 regressions passed, including the real-psql startup-file test.
- **Backend:** 422 DB-less tests passed. 51 database tests passed with one existing skip
  (`GET /pharmapi/errors`, awaiting T8), which the summary now shows.
- **Other checks:** lint and format, fresh migrations, frontend typecheck/lint/format, eight
  Vitest tests and the production build passed.
- **Cleanup:** no `/tmp/pa-verify-*` cluster or `pa-check-*` directory was left behind.
- **Command discovery:** a harness regression parses every documented `verify.py` invocation
  (in instructions, `docs/VERIFY.md`, skills and CI) against the runner's options. Separately,
  a manual run worked from `frontend/src` under system Python 3.9, and the `.agents/skills`
  links resolve.

**Passed in CI on PostgreSQL 16.** The `backend-db` job's first run (commit `9485c5e`,
PostgreSQL 16.15 on `ubuntu-24.04`) reported the same coverage: harness 33/33, 422 DB-less
tests, fresh migrations, and 51 database tests with the one existing skip.

**Skipped, by design.** Without `--with-db`, the summary reports the harness as
`32 passed, 1 skipped` (the real-psql test) and the seven database suites as EXCLUDED
(the Yellow Card suite was added as an eighth later; see below).

**Live activation**, with probe files that were removed afterwards:

- **Claude Code**, headless on the claude.ai plan:
  - **From the root:** the formatter and the Stop hook ran. The Stop hook blocked on a type
    error, then the repeat-stop guard let the session finish.
  - **From `frontend/`:** no hooks ran.
  - **After `cd` into an added directory:** the previous hook command ran that directory's
    hook script; the current one does not.
- **Codex:** `hooks/list` found no hooks for this repository under the developer's real
  config, because the project is not trusted. It found the hooks with trust granted in an
  isolated `CODEX_HOME`:
  - from a fresh clone's root and from `frontend/src`, as untrusted until reviewed;
  - in a linked worktree, from the main checkout's local `.codex/hooks.json`.

  One `codex exec` run with per-run trust ended as described above. That run persisted its
  trust override into `~/.codex/config.toml`; the line was removed and the file restored
  byte-for-byte.

**Reproduced, then fixed.** Each problem below was reproduced first, and each regression test
was shown to fail against the previous code:

- **Fixture loading:** psql with a synthetic startup file exited 0 but rolled the fixtures back
  (`\set AUTOCOMMIT off`) or wrote them to another database (`\connect decoy`).
- **Hook resolution:** a Claude Stop hook ran another repository's hook script, and exited 2
  outside Git despite `stop_hook_active`.
- **Stop output:** the successful Stop hook wrote plain text to stdout, which Codex rejects.
- **Formatter:** it returned exit 2 for an outside-worktree edit, and hook-config-only edits
  skipped the Stop checks.
- **Ignore rules:** a directory-level `.claude/` rule hid new hook and skill files from Git and
  the Stop hook, and made `git add` of tracked Claude config exit 1. The regression test runs
  without global, system or default-excludes Git config, which had masked a missing rule.
- **Instruction edits:** editing only `CLAUDE.md` or `AGENTS.md` skipped the Stop checks, although
  a harness regression covers their verification fallback.
- **Review findings:** a planted `.git` file was followed as a worktree, nested worktrees were
  not formatted, Ruff ignored its own excludes for explicit paths, and an unset
  `CLAUDE_PROJECT_DIR` failed with an unrelated error.

**Not verified:**

- **Codex Stop feedback:** observed only through the model's reply. Codex's JSON output and
  local logs did not record the hook run.
- **Codex in the developer's own setup:** no hooks run there until the project is trusted and
  each hook is approved.
- **Versions:** local runs used PostgreSQL 14.18, Node 23.11.0, Python 3.13 for the backend
  and system Python 3.9.6 for the launcher. CI covers PostgreSQL 16, Node 22 and Python 3.13.
  Locally, frontend dependencies were not freshly installed with `npm ci`; CI's frontend job
  does install them that way.

These results do not include the release checks excluded above.

## Validation: Yellow Card database suite

Before this change, `test_yellow_cards_db.py` was not a database suite. The DB-less run
collected it and it skipped itself (`429 passed, 1 skipped`), so none of its four tests ran
anywhere in verification or CI. Local results after the change (2026-10-07, PostgreSQL 16.15,
Python 3.13, Node 22; the `--with-db` runs used a non-root account, as `initdb` requires):

- `python3 scripts/verify.py --backend-only`: harness `38 passed, 1 skipped` (the real-psql
  test), 429 DB-less tests with no skip, all eight database suites EXCLUDED.
- `python3 scripts/verify.py --backend-only --with-db --pg-bin /usr/lib/postgresql/16/bin`:
  harness 39/39, 429 DB-less tests, fresh migrations, then 55 database tests: the previous 51
  with the one existing `/pharmapi/errors` skip, plus `PASS (4 passed)` for the Yellow suite,
  run last. No `/tmp/pa-verify-*` cluster was left behind.
- A deliberately broken run that withheld `YELLOW_TEST_DATABASE_URL` from the Yellow suite
  reported `FAIL: Database suite: test_yellow_cards_db.py` and exited 1.
- The new harness regressions fail against a fix that only adds the module to the suite list:
  the private-URL wiring, the refusal of a non-private URL and the zero-skip rule each fail.
- Frontend checks passed separately as the checkout's owner (`--frontend-only`: Vitest 23
  passed, production build); in the full non-root run they could not write build state
  into that checkout.
