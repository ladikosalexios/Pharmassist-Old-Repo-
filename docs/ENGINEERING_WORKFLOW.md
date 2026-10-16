# Shared engineering workflow contract

Contract version: 1. Either Codex or Claude Code can lead. This is the provider-neutral
contract used by this repository's existing delegation workflow, not a second runner.
Keep repository commands and provider launch details in the repository adapter linked
by the local entrypoints. Existing runners and their JSON schemas remain unchanged;
handoff records live alongside their artifacts. Adoption of this contract makes no
claim about any repository's configuration or runtime results.

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
the state from Git and retained evidence and marks missing evidence unverified.

```text
Task ID / contract version:
Outgoing lead identity + provider / incoming lead identity + provider:
Goal / observable acceptance criteria / explicit exclusions:
Repository / absolute worktree / branch / full base SHA / current full HEAD:
Dirty and untracked files / full diff location and hash / pending work locations:
Implementation owner / file assignments / active workers, processes and paused status:
Authorization / allowed actions / restrictions / prerequisite order:
Tests: command, cwd, tested HEAD + fingerprint, exit, counts, skips, log location:
Review: execution state, verdict, evidence validity, independent reviewer,
reviewed base + candidate commits + fingerprint, report and findings locations:
Findings disposition / acceptance criteria met and outstanding:
Next bounded action and owner / blockers / unresolved approval or uncertain operations:
Remaining limits and unverified runtime behavior:
Outgoing lead acknowledgment: workers paused, state captured, authority handed off:
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

Local review execution uses exactly one state, separately from verdict and evidence validity:

| Execution state | Required meaning |
| --- | --- |
| pending | Review is planned, awaiting inputs or still running; no completed report is available. |
| completed | Independent reviewer inspected the supplied frozen revision and returned a complete report with exact identity, findings (including zero), acceptance assessment and validation gaps. |
| failed | A started review could not finish because of an error, denial or interruption; retain the failed action and partial evidence. A zero process exit cannot turn this into completed. |
| skipped | Review was deliberately not run; record the reason and next owner/action. |

For a completed review record a separate verdict: `approved` or `changes_requested`.
These are local recommendations, never submitted approvals. A completed review can
contain unresolved defects and a changes_requested verdict; completion alone does not
establish acceptance. Pending, failed and skipped reviews have no approval verdict.

Record evidence validity separately as `current`, `stale` or `unverified`. Missing,
incomplete or inconsistent identity/report, or uncertain reviewer independence, leaves
evidence unverified. Changed inputs make earlier evidence stale: preserve the historical
execution result and mark the current candidate's required review pending. Neither
stale nor unverified evidence satisfies final review, even with an approved verdict.

A denied action that prevents a started review from completing means failed. Do not
retry a denied action without materially new relevant authorization; check an uncertain
outcome before any retry. Preserve blockers across lead switches. For CI retain the
existing repository reporter's richer labels and semantics (including unverified or
reused prior attestations); local handoffs do not modify or replace runner/CI records.

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
