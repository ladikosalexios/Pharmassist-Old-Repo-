---
name: delegate
description: Use when Codex or Claude Code leads bounded PharmAssist implementation, independent review, integration or a lead handoff.
---

Read `docs/ENGINEERING_WORKFLOW.md` for the shared workflow contract, then
`docs/DELEGATION.md` for PharmAssist task fields, native launch procedures, exact
revision checks and observed provider limits. Read `AGENTS.md`, `CLAUDE.md` and
`docs/VERIFY.md` from this worktree too. These documents own the procedure.

Name one active lead and one implementation owner per file. A lead switch requires
paused workers, a complete handoff and explicit incoming-lead acknowledgment.
Use separate writer worktrees and an independent reviewer of the frozen final diff.
Use existing native roles only after discovery; disclose instruction fallbacks.
Confirm effective reviewer permissions; never change trust or broaden tools to pass.
Run the existing scope/revision helper and repository harness; report actual command
and review evidence with pending, completed, failed or skipped execution state;
record verdict and evidence validity separately, with pending work. Never substitute static checks or historical observations for runtime evidence.

Codex roles: `pharmassist_implementer` / `pharmassist_reviewer`.
Claude roles: `pharmassist-implementer` / `pharmassist-reviewer`.
No unattended provider sessions, further worker delegation, publishing, merging,
deployment or permission changes follow from invoking this skill.
