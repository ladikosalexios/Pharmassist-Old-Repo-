# AGENTS.md

Read [CLAUDE.md](CLAUDE.md) for the shared PharmAssist architecture and development rules.
Read [docs/VERIFY.md](docs/VERIFY.md) before running checks or claiming completion.

These are tracked repository instructions, available in every checkout and worktree.
Use this worktree's files and dependencies; do not run commands in another checkout.
Do not seed, migrate, or test against a development or production database during verification.
The verification harness creates its own database when explicitly requested.
Codex runs this repository's hooks only after the project and each hook are trusted (`/hooks`),
and in a linked worktree it uses the main checkout's `.codex/hooks.json`. Unless you know they
ran, run `python3 scripts/verify.py` from the worktree root yourself before claiming completion.
