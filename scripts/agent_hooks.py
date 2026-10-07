"""Shared, worktree-local hook implementation for Claude Code and Codex."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Formatter scopes mirror .pre-commit-config.yaml; CI checks nothing outside them.
RUFF_SCOPE = ("backend/", "scripts/")
PRETTIER_SCOPE = "frontend/"
PRETTIER_EXCLUDED = ("frontend/node_modules/", "frontend/dist/", "frontend/build/")
PRETTIER_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".json", ".css", ".md", ".yml", ".yaml")
# Agent hook/instruction wiring is covered by the harness regressions.
TOOLING = (".claude/", ".codex/", ".agents/", ".github/workflows/", "CLAUDE.md", "AGENTS.md")
# Keep Stop feedback readable; the full log is one `python3 scripts/verify.py` away.
FEEDBACK_LINES = 60


def git(directory, *args):
    output = subprocess.check_output(
        ["git", "--no-optional-locks", *args], cwd=directory, stderr=subprocess.DEVNULL, text=True
    )
    return output.strip()


def registered_worktrees(root):
    output = git(root, "worktree", "list", "--porcelain")
    prefix = "worktree "
    return {
        Path(line[len(prefix) :]).resolve()
        for line in output.splitlines()
        if line.startswith(prefix)
    }


def worktree_for(root, directory):
    """The worktree registered with root's repository that contains directory, else root.

    Hooks follow the agent into this repository's own worktrees (whose code they then run),
    but never into an unrelated repository, a directory outside Git, or a directory whose
    planted .git file merely points at this repository.
    """
    try:
        candidate = Path(git(directory, "rev-parse", "--show-toplevel")).resolve()
        registered = candidate in registered_worktrees(root)
    except (OSError, subprocess.CalledProcessError):
        return root
    if not registered or candidate == Path(root).resolve():
        return root
    return candidate


def changed_paths(root):
    paths = set()
    for args in (
        ("diff", "--name-only", "-z", "HEAD"),
        ("ls-files", "--others", "--exclude-standard", "-z"),
    ):
        output = subprocess.check_output(["git", "--no-optional-locks", *args], cwd=root)
        paths.update(p.decode() for p in output.split(b"\0") if p)
    return paths


def stop(root, payload):
    if payload.get("stop_hook_active"):
        print(
            json.dumps(
                {
                    "systemMessage": "A previous Stop check blocked completion. "
                    "Report its failure or missing prerequisites explicitly; "
                    "this repeat-stop guard is not a verification pass."
                }
            )
        )
        return 0
    target = worktree_for(root, payload["cwd"]) if payload.get("cwd") else root
    paths = changed_paths(target)
    backend = any(p.startswith(("backend/", "scripts/", *TOOLING)) for p in paths)
    frontend = any(p.startswith("frontend/") for p in paths)
    if any(p in (".github/workflows/lint.yml", ".pre-commit-config.yaml") for p in paths):
        backend = frontend = True
    if not backend and not frontend:
        print("No backend/frontend/tooling changes; stop checks not needed.", file=sys.stderr)
        return 0
    command = [sys.executable, str(target / "scripts/verify.py"), "--quick"]
    if not frontend:
        command.append("--backend-only")
    elif not backend:
        command.append("--frontend-only")
    # Codex rejects non-JSON stdout from a Stop hook that exits 0, so the runner's log
    # never reaches stdout; on failure its tail (with the coverage summary) goes to stderr.
    result = subprocess.run(
        command, cwd=target, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    if result.returncode:
        print("\n".join(result.stdout.splitlines()[-FEEDBACK_LINES:]), file=sys.stderr)
        print(
            f"Stop checks failed or could not run in {target}. "
            "Run python3 scripts/verify.py and report gaps.",
            file=sys.stderr,
        )
        return 2
    return 0


def format_edit(root, payload):
    raw = payload.get("tool_input", {}).get("file_path")
    if not raw:
        # apply_patch and shell-based edits have no stable file_path; the Stop
        # hook still checks their changed files. Never parse/execute patch text.
        print("No single file_path; formatting deferred to verification.", file=sys.stderr)
        return 0
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = Path(payload.get("cwd", str(root))) / candidate
    target = candidate.resolve()
    # Includes worktrees nested in the project, e.g. .claude/worktrees/.
    tree = worktree_for(root, target.parent) if target.parent.is_dir() else root
    if not target.is_file() or not target.is_relative_to(tree.resolve()):
        # Agent memory, scratch files and other repositories are not ours to format.
        print("Edited file is outside this repository's worktrees; not formatted.", file=sys.stderr)
        return 0
    relative = target.relative_to(tree.resolve()).as_posix()
    if target.suffix == ".py" and relative.startswith(RUFF_SCOPE):
        # --force-exclude honours Ruff's excludes (e.g. migrations) for explicit paths,
        # as ruff-pre-commit does.
        arguments = ["ruff", "format", "--force-exclude", str(target)]
        python = tree / "backend/.venv/bin/python"
        command = [str(python), "-m", *arguments] if python.is_file() else None
        if command is None and shutil.which("ruff"):
            command = arguments
        cwd = tree / "backend"
    elif (
        target.suffix in PRETTIER_SUFFIXES
        and relative.startswith(PRETTIER_SCOPE)
        and not relative.startswith(PRETTIER_EXCLUDED)
    ):
        prettier = tree / "frontend/node_modules/.bin/prettier"
        command = [str(prettier), "--write", str(target)] if prettier.is_file() else None
        cwd = tree / "frontend"
    else:
        return 0
    if command is None:
        print(
            "Formatter unavailable; verification must report the missing dependency.",
            file=sys.stderr,
        )
        return 0
    code = subprocess.run(command, cwd=cwd).returncode
    if code:
        print("Formatter failed; run verification before claiming completion.", file=sys.stderr)
    return 0


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Hook input must be an object")
        action = sys.argv[1]
        return stop(ROOT, payload) if action == "stop" else format_edit(ROOT, payload)
    except (OSError, ValueError, IndexError, subprocess.SubprocessError) as exc:
        print(f"Hook could not run: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
