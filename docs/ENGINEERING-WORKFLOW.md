# Shared engineering workflow contract

Contract version: 1. Either Codex or Claude Code can lead. This is the provider-neutral
contract used by this repository's existing delegation workflow, not a second runner.
Keep repository commands and provider launch details in [DELEGATION.md](DELEGATION.md)
and [VERIFY.md](VERIFY.md). Other repositories may adopt this contract with their own
adapter; its presence here makes no claim about their configuration or runtime results.

## Task authority and ownership

Before implementation, name one active lead and one implementation owner. The lead
owns scope, observable acceptance criteria, file ownership, integration decisions and
the final report. The lead may also implement. Otherwise it delegates a bounded task
to one writer. Additional writers require disjoint file ownership and separate worktrees;
each file has exactly one implementation owner at a time. Shared files are serialized.
No worker delegates further without a revised contract from the lead.

Use the task contract in the repository adapter. Record the repository/root, branch,
full base and starting HEAD, dirty files, goal, acceptance criteria, owned files,
exclusions, dependency order, allowed actions, commands and handoff destination.
Preserve existing work and instructions. Missing prerequisites or overlapping ownership
are blockers; they do not authorize broader scope or cleanup.

## Switching the lead

The user can select either provider as lead. A switch changes responsibility, never
permissions. The outgoing lead pauses writers, captures their pending changes and
blockers, and supplies this handoff. If it is unavailable, the incoming lead reconstructs
the state from Git and retained evidence and marks missing evidence UNVERIFIED.

```text
Task ID / contract version:
Outgoing lead identity + provider / incoming lead identity + provider:
Goal / observable acceptance criteria / explicit exclusions:
Repository / absolute worktree / branch / full base SHA / current full HEAD:
Dirty and untracked files / full diff location / pending work locations:
Implementation owner per file or directory / active workers and paused status:
Allowed actions / restrictions / prerequisite order:
Tests: command, cwd, tested HEAD + fingerprint, exit, counts, skips, log location:
Review: status, independent reviewer, reviewed base + HEAD + fingerprint, report location:
Findings disposition / acceptance criteria met and outstanding:
Next bounded action / blockers / unresolved approval or uncertain operations:
Incoming lead acknowledgment: verified state, accepted ownership, next action:
```

The incoming lead reads the repository instructions, checks the exact root, branch,
base, HEAD, dirty state and file contents against the handoff, then explicitly accepts
lead ownership. Until then no new writer starts. The outgoing lead stops issuing work;
two providers must never act as simultaneous leads. Resume existing workers only after
confirming their root, scope and state. The provider switch alone does not invalidate
unchanged evidence, but the incoming lead must recheck it; any missing or changed input
requires fresh verification/review. Never infer successful integration from a summary.

## Independent review and evidence

Freeze implementation before review. A separate reviewer who did not implement the
change receives the actual complete diff, source access, acceptance criteria, full
base/HEAD, worktree fingerprint and actual command logs. Reviewers return findings and
validation gaps; they do not edit, approve, publish or run tests. Self-review may help
preparation but cannot satisfy independent review. Resolve findings through the named
implementation owner, then freeze and review the resulting revision again.

Every local review report has exactly one status:

| Status | Required meaning |
| --- | --- |
| COMPLETED | Independent reviewer inspected the supplied frozen revision and returned a complete report with exact identity, findings (including zero), acceptance assessment and validation gaps. This is reported review evidence, not approval. |
| SKIPPED | No review ran; record the reason and pending review action. |
| FAILED | A started review could not finish because of an error, denial or interruption; record the failed action and retained partial evidence. |
| UNVERIFIED | A report/identity is missing, incomplete, inconsistent or stale, or independence cannot be established. A zero process exit does not fix this. |

Findings and completion are separate: COMPLETED can contain unresolved defects and
does not imply acceptance. A denied action is FAILED if it prevents completion, even
if the provider exits zero. Do not retry a denied action without materially new relevant
authorization; check an uncertain outcome before any retry. Preserve blockers across
lead switches. For CI retain the existing repository reporter's richer labels and
semantics (including reused prior attestations); local records do not replace CI records.

Record each check's command, cwd, exact tested HEAD/fingerprint, exit and actual counts,
with skipped/excluded/not-run checks and reasons. Preserve logs and reviewer reports
outside the checkout. Static configuration checks, role discovery, hook readiness,
synthetic adapters and live execution are distinct evidence. Record provider versions
and effective permissions for live probes. Never relabel configuration as runtime proof.

Use the existing scope/revision helper before and after review. Edits, commits (even
with identical bytes), base/scope changes, conflict resolution and integration invalidate
earlier evidence. Run affected checks and independent review on the final revision.
Without a local commit, report the base/HEAD plus dirty fingerprint and full patch;
describe it as an uncommitted candidate, not a reviewed commit.

## Completion and safety boundaries

The active lead reports acceptance results, changed files, branch/worktree, exact
revision, complete diff, tests, review status, unresolved findings, pending work and
blockers. A task with pending review or failed checks is a reviewable handoff with those
limits, not an unqualified completion. Keep task evidence and worktrees until their
owner authorizes cleanup.

Use existing native subagents and repository roles when available. If role discovery
or isolation is unavailable, disclose the fallback and effective boundaries; do not
silently grant tools or claim isolation. Agent teams need not be enabled. Do not change
global settings, trust, permissions, credentials or models to make a test pass. Normal
existing approval gates remain in force. Pushes, external messages, PR publication,
merges, deployments and cross-repository changes require separate task authorization.
