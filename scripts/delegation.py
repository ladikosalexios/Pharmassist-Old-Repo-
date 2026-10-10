"""Read-only scope and revision checks for local PharmAssist delegation handoffs."""

import argparse
import hashlib
import json
import re
import stat
import subprocess
from pathlib import Path, PurePosixPath


def git(root, *arguments):
    return subprocess.check_output(
        ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", *arguments], cwd=root
    )


def scope_paths(paths):
    """Literal files, or directory prefixes ending in /; never globs or traversal."""
    if not paths:
        raise ValueError("At least one owned file or directory is required")
    for path in paths:
        parts = PurePosixPath(path).parts
        if (
            not path
            or path.startswith("/")
            or "\\" in path
            or any(c in path for c in "*?[]")
            or any(ord(c) < 32 for c in path)
            or any(part in (".", "..", ".git") for part in path.split("/"))
            or not parts
            or str(PurePosixPath(path)) != path.rstrip("/")
            or path.endswith("//")
        ):
            raise ValueError("Scope must contain literal repository-relative paths")
    return sorted(set(paths))


def in_scope(path, scopes):
    return any(path.startswith(scope) if scope.endswith("/") else path == scope for scope in scopes)


def snapshot(root, base, scopes):
    scopes = scope_paths(scopes)
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", base):
        raise ValueError("Base must be a full lowercase commit SHA")
    if git(root, "rev-parse", f"{base}^{{commit}}").decode().strip() != base:
        raise ValueError("Base must identify a commit")
    subprocess.run(
        ["git", "--no-optional-locks", "merge-base", "--is-ancestor", base, "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    head = git(root, "rev-parse", "HEAD").decode().strip()
    status = git(root, "status", "--porcelain=v1", "--untracked-files=all", "-z")
    untracked = git(root, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0")
    changes = set(p for p in untracked if p)
    digest = hashlib.sha256()

    def add(value):
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)

    for value in (str(root.resolve()).encode(), base.encode(), head.encode(), status):
        add(value)
    # Include commit, index and working tree independently. This catches an edit restored
    # to base in the working tree, staged changes and renames' old AND new paths.
    for revision in ((base, "HEAD"), ("HEAD",), ("--cached", "HEAD")):
        options = ("--no-ext-diff", "--no-textconv", "--no-renames")
        changes.update(
            p
            for p in git(root, "diff", *options, "--name-only", "-z", *revision, "--").split(b"\0")
            if p
        )
        add(git(root, "diff", *options, "--binary", *revision, "--"))
    for name in sorted(p for p in untracked if p):
        path = root / name.decode("utf-8")
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            content = path.readlink().as_posix().encode()
        elif stat.S_ISREG(mode):
            content = path.read_bytes()
        else:
            raise ValueError("Untracked special files cannot form handoff evidence")
        add(name)
        add(str(mode).encode())
        add(content)
    # Detect ordinary concurrent edits while collecting evidence; the lead must still
    # freeze writers and recheck before/after review, this is not a transactional lock.
    if (
        git(root, "rev-parse", "HEAD").decode().strip() != head
        or git(root, "status", "--porcelain=v1", "--untracked-files=all", "-z") != status
    ):
        raise ValueError("Revision changed while capturing; stop writers and retry")
    paths = sorted(p.decode("utf-8") for p in changes)
    return {
        "schema": 1,
        "worktree": str(root.resolve()),
        "base_sha": base,
        "head_sha": head,
        "scope": scopes,
        "dirty": bool(status),
        "changed_paths": paths,
        "out_of_scope": [p for p in paths if not in_scope(p, scopes)],
        "fingerprint": digest.hexdigest(),
    }


def check(record, current):
    """A snapshot is identity evidence, never a test pass or reviewer approval."""
    if not isinstance(record, dict) or type(record.get("schema")) is not int:
        raise ValueError("Invalid handoff snapshot")
    if record != current:
        return "STALE: worktree, revision, content, base or scope changed; rerun checks and review"
    if current["out_of_scope"]:
        return "OUT OF SCOPE: lead must resolve ownership before integration"
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("snapshot", "check"))
    parser.add_argument("record", nargs="?", help="Saved snapshot JSON, required for check")
    parser.add_argument(
        "--base", required=True, help="Full ancestor commit SHA from the task contract"
    )
    parser.add_argument("--scope", action="append", required=True, help="Owned file or directory/")
    args = parser.parse_args()
    if (args.action == "check") != bool(args.record):
        parser.error("Only check requires a saved snapshot path")
    try:
        root = Path(git(Path.cwd(), "rev-parse", "--show-toplevel").decode().strip())
        current = snapshot(root, args.base, args.scope)
        if args.action == "snapshot":
            print(json.dumps(current, indent=2))
            return int(bool(current["out_of_scope"]))
        error = check(json.loads(Path(args.record).read_text()), current)
        print(error or "CURRENT: scope and revision match; this is not verification or approval")
        return int(bool(error))
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(2, f"Cannot establish handoff evidence: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
