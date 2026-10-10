---
name: delegate
description: Use when delegating PharmAssist development to bounded implementers and independent reviewers, or integrating their handoffs. One lead owns acceptance criteria and the combined verification.
---

Read `docs/DELEGATION.md` from this worktree before delegation. It is the canonical
contract for both providers. Read `AGENTS.md`, `CLAUDE.md` and `docs/VERIFY.md` too.

1. Keep one lead responsible for acceptance criteria, file ownership and integration.
   Start with one implementer and one independent reviewer; add workers only for
   separable file ownership. Do not start a swarm or unattended provider sessions.
2. Give every writer a distinct worktree and an explicit base SHA, acceptance criteria,
   owned files, exclusions, dependencies and verification command. Preserve pending
   files and existing worktrees. Stop on an ownership collision or missing prerequisite.
3. Use the provider's native roles when discovery is confirmed. Otherwise pass their
   instructions explicitly and report the fallback. Names alone do not load a role.
4. Have the lead run `scripts/delegation.py snapshot` with the contract's base and scope,
   freeze writers and give the independent reviewer the actual diff and exact revisions.
   Reviewers return findings only. The lead checks the snapshot before and after review.
5. Fix real findings in the owned worktree. Every edit, new commit, changed base, scope
   amendment or integration invalidates earlier verification/review evidence. Repeat
   affected checks and independent review, then run `python3 scripts/verify.py --with-db`
   on the final combined revision. Never use a shared database or live clinical data.
6. Return the handoff contract and exact evidence with failures, skips and exclusions.
   Integration, publishing and deployment remain separate actions with their own scope.

Provider roles: `pharmassist_implementer` / `pharmassist_reviewer` in Codex;
`pharmassist-implementer` / `pharmassist-reviewer` in Claude Code. Skills are
instructions, not permission enforcement. See the guide for activation limits.
