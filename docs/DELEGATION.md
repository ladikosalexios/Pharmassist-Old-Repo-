# Delegating PharmAssist development

One lead owns the task's acceptance criteria and integration. Start with one bounded
implementer and one independent reviewer. Add parallel writers only when their file
ownership does not overlap. Native subagents provide separate contexts; writers also
need separate worktrees. A reviewer must not review their own implementation.

This guide is the canonical contract for Codex and Claude Code. The `delegate` skill
is canonical in `.claude/skills/delegate/`; `.agents/skills/delegate` is a relative
symlink to it. `AGENTS.md` and `CLAUDE.md` point here. Keep PharmAssist's harness and
contracts independent of Second Opinion and other repositories.

## Contract the lead supplies before a writer starts

Copy this into the task prompt, filling every field. Local evidence belongs outside
the repository (for example, a task directory under `/tmp`); never include clinical
data, credentials or live-service transcripts.

```text
Task / lead / implementer:
Goal and observable acceptance criteria:
Repository and assigned root: absolute path, or explicit native-generated constraints:
Branch and full base SHA:
Starting HEAD and dirty status (record pending files; never reset or stash them):
Owned literal files or directories ending in /:
Excluded work and files:
Dependencies / order / shared-file owner:
Required commands and expected coverage:
Allowed actions (including whether local commits are allowed):
Handoff destination:
```

The lead owns shared integration files: dependency manifests, migrations, public
contracts and shared configuration need one named owner. If two tasks need the same
file, serialize them or let the lead make the shared edit. Before broadening scope,
record a revised contract, stop affected writers and invalidate old evidence.
An implementer returns a blocker if the base, root, ownership or prerequisite is
wrong. No silent scope expansion, second-level delegation or cleanup of other work.

## Start tasks using native tools

From an existing clean lead worktree, record its full SHA and status. Preserve dirty
files; choose an explicit committed base without copying pending work into workers.
Use a new branch and unused path, never reuse or reset another worker's checkout:

```sh
git rev-parse HEAD
git status --short --untracked-files=all
git worktree list
# Replace BASE_SHA with the recorded full SHA and task-one with a unique name.
git worktree add -b work/task-one /tmp/pharmassist-task-one BASE_SHA
```

Prepare the worker's own dependencies as described in `docs/VERIFY.md`. Do not
symlink mutable dependencies from another checkout. Launch the provider from the
assigned worktree root so repository instructions and skill discovery apply.

**Codex app:** create the lead task under the **Pharmassist** sidebar project. Ask it
to delegate a bounded task to `pharmassist_implementer` in the assigned worktree and
later to `pharmassist_reviewer` for the frozen diff. Native subagents remain attached
to their lead; separate helpers should be created under the same sidebar project.
If a helper opens projectless, move it to Pharmassist through the app; repository
role files cannot control sidebar membership. Do not change global trust to make a
role appear. If custom roles are unavailable in the running client, pass the role's
instructions explicitly to a native worker and disclose the fallback and permissions.

**Codex CLI:** when installed on PATH, start `codex -C /tmp/pharmassist-task-one`.
The lead prompt invokes `$delegate` and requests the appropriate custom role by its
`name`. A role name does not switch the session's directory: supply the assigned root
in the contract and require the worker to confirm it before editing. This installed
app's native subagent API may differ from CLI; verify actual role discovery first.

**Claude Code native isolation:** start `claude` at the lead worktree root. Use
`/delegate` and ask for `pharmassist-implementer` through the Agent tool with
`isolation: "worktree"` on the call. This creates its own new checkout; it does not
use the manually prepared `/tmp/pharmassist-task-one` above. Supply the complete
contract on that call, with the root explicitly authorized as a **new native-generated
worktree registered with this repository, distinct from the lead's absolute root**.
Name the repository and lead root in the contract. The worker first discovers and
records its actual root, branch, HEAD and dirty status, verifies those constraints
and the exact base SHA, and then implements within the unchanged scope. It includes
the resolved absolute root in its handoff. This startup discovery stays inside the
same agent call: returning an empty discovery task can delete the unused worktree.
The role also sets `isolation: worktree`.
Pass isolation on the call even if agent teams are enabled; named teammates can
otherwise run in the parent directory. Native isolation normally starts from the
default branch, so the worker must confirm HEAD equals the contract's base. If it
does not, stop the worker without edits and use the manually prepared worker session
below. Native automatic isolation is suitable when its starting base matches the
contract; use a prepared session when an exact non-default base is required.
Use ordinary native subagents for this workflow; no agent-team activation is required.
For a manually prepared worker **session** instead, start `claude` directly in
`/tmp/pharmassist-task-one` with the filled contract; it already has its own checkout.
Keep the independent reviewer separate from that writer session.

In `/agents`, confirm the two project roles and their tool lists. `claude --agent
pharmassist-implementer` selects a **main session** role, not an independent subagent;
do not assume its `isolation` field creates a worktree in that mode. A main worker
session should be started explicitly in `/tmp/pharmassist-task-one` instead.

Example lead prompt (append the filled contract):

```text
Use the delegate skill. Lead acceptance criteria and integration. Assign this
contract to one implementer in its isolated worktree. After its handoff, freeze
writers and ask a different reviewer to inspect the actual diff and requirements.
Collect the report before finishing. Add no parallel writer unless ownership is
separable. Return blockers, exact evidence and the final combined harness result.
```

## Handoff and exact-revision checks

The implementer returns task ID, worktree, base/head SHAs, commits and full diff,
changed files, acceptance results, command/exit/count evidence, failures, skips,
exclusions and remaining blockers. The lead compares the file list to ownership.
For example, with ownership of `frontend/src/pages/` and one exact test file:

```sh
# Use an existing private evidence directory outside the worktree.
python3 scripts/delegation.py snapshot --base BASE_SHA \
  --scope frontend/src/pages/ --scope frontend/src/lib/api.test.ts \
  > /tmp/pharmassist-task-evidence/snapshot.json
python3 scripts/delegation.py check /tmp/pharmassist-task-evidence/snapshot.json \
  --base BASE_SHA --scope frontend/src/pages/ --scope frontend/src/lib/api.test.ts
git diff --no-ext-diff --no-textconv --no-renames BASE_SHA HEAD
git diff --no-ext-diff --no-textconv --no-renames HEAD
git diff --cached --no-ext-diff --no-textconv --no-renames HEAD
```

Replace `BASE_SHA` with the full contract SHA. Run these commands in the worker's
root. The helper uses literal file scopes and trailing-slash directory scopes;
globs, absolute paths and traversal are rejected. It checks committed, staged,
unstaged and non-ignored untracked changes, including both sides of renames.
Read any new untracked source separately: `git diff` does not show it. Prefer a
clean local commit before review when the task authorizes commits.

Snapshot exits: **0** within scope, **1** out of scope, **2** unusable configuration.
Check exits: **0** current and within scope, **1** stale or out of scope, **2** unusable.
The fingerprint binds the worktree root, full base/head, Git status, tracked diffs
and untracked file contents and modes; symlink targets are recorded without following
them. Ignored dependencies and generated files are excluded. Evidence files must stay
outside the worktree so they do not invalidate their own snapshot.

This helper reads Git/files and prints evidence. It writes no files, runs no agents
or tests and performs no integration. It is a change detector, not a sandbox, lock,
signed attestation or approval. Freeze writers while capturing/reviewing: the status
recheck cannot detect every concurrent write race or changes to ignored inputs.

The lead gives the independent reviewer the filled contract, full actual diff,
changed files, source access, exact base/head, snapshot fingerprint and verification
evidence. The lead runs `check` immediately before and after collecting the review.
The reviewer returns:

```text
Task / reviewer identity (different from implementer):
Reviewed worktree / base SHA / head SHA / fingerprint:
Completion: completed or incomplete, with missing inputs:
Findings: severity, file:line, concrete impact and suggested validation:
Acceptance criteria assessed and validation gaps:
Remaining risk / blockers (say explicitly when no concrete findings):
```

Do not manufacture a completion record from a successful process exit or a worker's
summary. Keep the independent report and harness log next to the snapshot. An edit,
new commit, base change, worktree change, scope amendment, conflict resolution or
integration invalidates earlier verification and review. Rerun the affected checks
and get independent review of the resulting revision; even a commit with identical
file contents changes its identity. This supplements `scripts/review_evidence.py`
and `scripts/review_checkpoint.py`, which already bind **CI PR** reviews to exact
head/base SHAs. Local handoffs do not write CI cache records or replace CI review.

## Integrate and verify

The lead confirms worker ownership, current evidence, acceptance criteria and review
findings. Resolve concrete findings before integration. Where local integration is
authorized, cherry-pick the reported commits into the isolated lead branch:

```sh
# In the lead worktree; replace WORKER_COMMIT with the reviewed commit.
git cherry-pick WORKER_COMMIT
python3 scripts/verify.py --with-db
```

Review the combined diff and obtain fresh review and scope evidence for this final
lead revision too; worker evidence cannot cover conflict resolution or combinations.
The same canonical harness runs synthetic offline tests, private socket-only
PostgreSQL suites, frontend checks and builds. Record counts and skips from its
coverage summary. Partial checks, a Stop hook's `--quick` result, or stale logs do
not prove the final combined revision passed. See `docs/VERIFY.md` for all exclusions.
Never use a development/production DB, live seed, live email, provider services or
clinical data. No production deployment, push, PR creation or merge follows from
using this skill. Retain worktrees and pending files until their owner permits cleanup.

## Enforcement and provider compatibility

| Boundary | What enforces it |
| --- | --- |
| Separate writer contexts | Native subagent sessions |
| Separate files/checkouts | Git worktrees; Claude native isolation when active |
| File ownership, acceptance, no publishing | Instructions and lead review; scope helper detects violations after writes |
| Claude reviewer source reads | `tools: Read, Grep, Glob` removes shell, edit, connector and delegation tools in that native role |
| Codex reviewer filesystem writes | `sandbox_mode = "read-only"` when applied; live parent overrides can replace this default |
| Codex reviewer no tests, connectors or escalation | Instructions; filesystem sandbox alone does not constrain every inherited tool |
| Stale local evidence | Explicit helper checks against the frozen state; no automatic approval gate |
| Tests and DB isolation | Existing canonical harness and its private DB/mock environment; trusted code, not an OS/network sandbox |
| Hooks | Existing provider hooks only when activated; global/project/hook trust remains a user decision |

Project roles use supported standalone Codex TOML files and Claude YAML-frontmatter
Markdown. Only the two named team roles are allowlisted in Git; personal ignored
Codex presets/config and existing PR-focused `code-reviewer` are retained separately.
No global settings, model pins, credentials, trust, permission expansion or branch
protection changes are needed. Both roles inherit the lead's selected model.

Official references checked 2026-10-10:

- [Codex custom subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents):
  project `.codex/agents/*.toml`, required fields and parent runtime overrides.
- [Codex skill discovery](https://learn.chatgpt.com/docs/build-skills): repository
  `.agents/skills`, including symlinked directories.
- [Claude custom subagents](https://code.claude.com/docs/en/sub-agents): supported
  frontmatter, tool allowlists, isolation, skills preloading and agent-team caveats.
- [Claude skills](https://code.claude.com/docs/en/skills): project `.claude/skills`.

Do not claim both installed providers loaded these roles just because syntax passed.
Claude's offline `claude plugin validate .claude/agents --strict` may return an
empty `contents` list even on success; that does not validate the roles. The repo's
regressions validate a bounded JSON-quoted frontmatter/TOML subset and the fields
used against the documented schema. Python 3.11+ also parses the complete TOML with
`tomllib`; the Python 3.9 frontend-only runner needs no backend or third-party parser.
Confirm live Claude discovery in `/agents` when the user starts a session. In Codex,
check actual role discovery in the target client; prompt fallback is available if
the client's native API cannot select custom roles. No paid/live session is needed
to run the repository's offline regressions. Record actual local compatibility and
remaining activation limits in the task handoff.
