"""Shared, worktree-local hook implementation for Claude Code and Codex."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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
    paths = changed_paths(root)
    backend = any(p.startswith(("backend/", "scripts/")) for p in paths)
    frontend = any(p.startswith("frontend/") for p in paths)
    if any(p in (".github/workflows/lint.yml", ".pre-commit-config.yaml") for p in paths):
        backend = frontend = True
    if not backend and not frontend:
        print("No backend/frontend/tooling changes; stop checks not needed.", file=sys.stderr)
        return 0
    command = [sys.executable, str(root / "scripts/verify.py"), "--quick"]
    if not frontend:
        command.append("--backend-only")
    elif not backend:
        command.append("--frontend-only")
    result = subprocess.run(command, cwd=root)
    if result.returncode:
        print(
            "Stop checks failed or could not run. Run python3 scripts/verify.py and report gaps.",
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
    if not target.is_relative_to(root.resolve()) or not target.is_file():
        raise ValueError("Edited file is outside this worktree or no longer exists")
    if target.suffix == ".py":
        python = root / "backend/.venv/bin/python"
        command = [str(python), "-m", "ruff", "format", str(target)] if python.is_file() else None
        if command is None and shutil.which("ruff"):
            command = ["ruff", "format", str(target)]
        cwd = root / "backend"
    elif target.suffix in (".ts", ".tsx", ".js", ".jsx", ".json", ".css", ".md", ".yml", ".yaml"):
        prettier = root / "frontend/node_modules/.bin/prettier"
        command = [str(prettier), "--write", str(target)] if prettier.is_file() else None
        cwd = root / "frontend"
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
