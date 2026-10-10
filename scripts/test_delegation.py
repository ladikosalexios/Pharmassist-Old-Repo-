"""Synthetic Git handoffs and provider role/skill consistency; no provider sessions."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import delegation
import verify

ROOT = Path(__file__).resolve().parents[1]


def quoted_fields(source, separator):
    """Our bounded YAML/TOML header subset uses JSON-quoted strings/lists only."""
    result = {}
    for line in source.strip().splitlines():
        key, value = line.split(separator, 1)
        if key in result or key.strip() != key:
            raise ValueError("Duplicate or malformed role field")
        result[key] = json.loads(value)
    return result


def codex_fields(source):
    header, prompt = source.split('developer_instructions = """\n')
    if not prompt.endswith('"""\n') or '"""' in prompt[:-4] or "\\" in prompt:
        raise ValueError("Role instructions must use our literal multiline TOML subset")
    fields = {**quoted_fields(header, " = "), "developer_instructions": prompt[:-4]}
    try:
        import tomllib
    except ImportError:
        return fields  # Python 3.9 frontend-only verification needs no backend dependencies.
    if tomllib.loads(source) != fields:
        raise ValueError("TOML parse differs from role subset")
    return fields


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pa-delegation-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        self.root.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Synthetic Worker")
        self.git("config", "user.email", "worker@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "core.hooksPath", "/dev/null")
        (self.root / "owned").mkdir()
        (self.root / "owned/a.txt").write_text("base\n")
        (self.root / "shared.txt").write_text("shared\n")
        (self.root / ".gitignore").write_text("cache/\n")
        self.git("add", ".")
        self.git("commit", "-qm", "Synthetic base")
        self.base = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.check_output(
            ["git", "--no-optional-locks", *args],
            cwd=self.root,
            env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull},
            stderr=subprocess.DEVNULL,
            text=True,
        )

    def capture(self, scopes=None, base=None):
        return delegation.snapshot(self.root, base or self.base, scopes or ["owned/"])

    def test_unchanged_snapshot_is_current_and_read_only(self):
        record = self.capture()
        files = sorted(self.root.rglob("*"))
        self.assertIsNone(delegation.check(record, self.capture()))
        self.assertFalse(record["dirty"])
        self.assertEqual(record["changed_paths"], [])
        self.assertEqual(files, sorted(self.root.rglob("*")))

    def test_scope_distinguishes_literal_files_and_directory_boundaries(self):
        self.assertTrue(delegation.in_scope("owned/a.txt", ["owned/"]))
        self.assertFalse(delegation.in_scope("owned-other/a.txt", ["owned/"]))
        self.assertFalse(delegation.in_scope("owned/a.txt", ["owned"]))
        self.assertFalse(delegation.in_scope("a.txt.extra", ["a.txt"]))
        self.assertTrue(delegation.in_scope("a.txt", ["a.txt"]))
        for bad in (
            "",
            "/tmp/a",
            "../a",
            "a/../b",
            "a/./b",
            ".git/",
            "a//b",
            "a//",
            "a*",
            "a\\b",
            "a\nb",
        ):
            with self.subTest(scope=bad), self.assertRaises(ValueError):
                delegation.scope_paths([bad])
        with self.assertRaises(ValueError):
            delegation.scope_paths([])

    def test_rename_and_delete_include_every_owned_path(self):
        self.git("mv", "shared.txt", "owned/moved.txt")
        (self.root / "owned/a.txt").unlink()
        record = self.capture()
        self.assertEqual(record["changed_paths"], ["owned/a.txt", "owned/moved.txt", "shared.txt"])
        self.assertEqual(record["out_of_scope"], ["shared.txt"])
        self.assertIn("OUT OF SCOPE", delegation.check(record, self.capture()))

    def test_untracked_content_and_staged_edits_invalidate_evidence(self):
        extra = self.root / "owned/new.txt"
        extra.write_text("first")
        initial = self.capture()
        self.assertEqual(initial["changed_paths"], ["owned/new.txt"])
        extra.write_text("other")  # Same status and byte count.
        self.assertIn("STALE", delegation.check(initial, self.capture()))
        initial = self.capture()
        self.git("add", "owned/new.txt")
        self.assertIn("STALE", delegation.check(initial, self.capture()))

    def test_tracked_edit_commit_and_base_changes_invalidate_evidence(self):
        initial = self.capture()
        source = self.root / "owned/a.txt"
        source.write_text("edit\n")
        self.assertIn("STALE", delegation.check(initial, self.capture()))
        dirty = self.capture()
        source.write_text("more\n")  # Same status and byte count.
        self.assertIn("STALE", delegation.check(dirty, self.capture()))
        self.git("add", "owned/a.txt")
        self.git("commit", "-qm", "Implement")
        committed = self.capture()
        self.git("commit", "--allow-empty", "-qm", "New revision")
        self.assertIn("STALE", delegation.check(committed, self.capture()))
        new_base = self.git("rev-parse", "HEAD").strip()
        self.assertIn("STALE", delegation.check(committed, self.capture(base=new_base)))

    def test_scope_amendment_and_worktree_identity_invalidate_evidence(self):
        initial = self.capture()
        self.assertIn("STALE", delegation.check(initial, self.capture(["owned/", "shared.txt"])))
        other = Path(self.temporary.name) / "copy"
        shutil.copytree(self.root, other)
        self.assertIn(
            "STALE", delegation.check(initial, delegation.snapshot(other, self.base, ["owned/"]))
        )

    def test_committed_change_restored_to_base_is_still_in_scope_check(self):
        (self.root / "shared.txt").write_text("changed")
        self.git("add", "shared.txt")
        self.git("commit", "-qm", "Out of scope commit")
        (self.root / "shared.txt").write_text("shared\n")
        self.assertEqual(self.capture()["out_of_scope"], ["shared.txt"])

    def test_ignored_dependencies_do_not_invalidate_and_symlinks_are_not_followed(self):
        (self.root / "cache").mkdir()
        (self.root / "cache/output").write_text("ignored")
        target = Path(self.temporary.name) / "outside"
        target.write_text("outside")
        (self.root / "owned/link").symlink_to(target)
        initial = self.capture()
        target.write_text("do not read this")
        (self.root / "cache/output").write_text("changed ignored dependency")
        self.assertIsNone(delegation.check(initial, self.capture()))
        (self.root / "owned/link").unlink()
        (self.root / "owned/link").symlink_to("new-target")
        self.assertIn("STALE", delegation.check(initial, self.capture()))

    def test_untracked_mode_and_invalid_records_fail_closed(self):
        path = self.root / "owned/new"
        path.write_text("test")
        initial = self.capture()
        path.chmod(0o755)
        self.assertIn("STALE", delegation.check(initial, self.capture()))
        for invalid in (None, [], {"schema": True}):
            with self.subTest(record=invalid), self.assertRaises(ValueError):
                delegation.check(invalid, self.capture())
        with self.assertRaises(ValueError):
            self.capture(base="HEAD")
        with self.assertRaises(subprocess.CalledProcessError):
            self.capture(base="0" * 40)

    def test_cli_detects_scope_and_staleness_without_writing_worktree(self):
        command = [sys.executable, str(ROOT / "scripts/delegation.py")]
        options = ["--base", self.base, "--scope", "owned/"]
        result = subprocess.run(
            command + ["snapshot", *options], cwd=self.root, capture_output=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = Path(self.temporary.name) / "snapshot.json"
        evidence.write_bytes(result.stdout)
        current = subprocess.run(
            command + ["check", str(evidence), *options], cwd=self.root, capture_output=True
        )
        self.assertEqual(current.returncode, 0, current.stderr)
        (self.root / "owned/a.txt").write_text("edited")
        stale = subprocess.run(
            command + ["check", str(evidence), *options], cwd=self.root, capture_output=True
        )
        self.assertEqual(stale.returncode, 1)
        (self.root / "shared.txt").write_text("out of scope")
        outside = subprocess.run(
            command + ["snapshot", *options], cwd=self.root, capture_output=True
        )
        self.assertEqual(outside.returncode, 1)
        self.assertEqual(json.loads(outside.stdout)["out_of_scope"], ["shared.txt"])
        evidence.write_text("{malformed")
        malformed = subprocess.run(
            command + ["check", str(evidence), *options], cwd=self.root, capture_output=True
        )
        self.assertEqual(malformed.returncode, 2)


class ProviderContractTests(unittest.TestCase):
    def test_shared_skill_and_entry_points_reach_canonical_contract(self):
        canonical = ROOT / ".claude/skills/delegate/SKILL.md"
        alias = ROOT / ".agents/skills/delegate/SKILL.md"
        self.assertEqual(alias.resolve(), canonical.resolve())
        for entry in ("AGENTS.md", "CLAUDE.md", ".claude/skills/delegate/SKILL.md"):
            self.assertIn("docs/DELEGATION.md", (ROOT / entry).read_text())
        self.assertIn("name: delegate\n", canonical.read_text())

    def test_codex_toml_is_valid_and_contains_only_supported_role_fields(self):
        for role in ("implementer", "reviewer"):
            path = ROOT / f".codex/agents/pharmassist-{role}.toml"
            config = codex_fields(path.read_text())
            self.assertEqual(config["name"], f"pharmassist_{role}")
            self.assertTrue(config["description"])
            self.assertEqual(
                set(config),
                {"name", "description", "developer_instructions"}
                | ({"sandbox_mode"} if role == "reviewer" else set()),
            )
            prompt = config["developer_instructions"]
            for reference in ("docs/DELEGATION.md", "CLAUDE.md", "docs/VERIFY.md"):
                self.assertIn(reference, prompt)
            if role == "reviewer":
                self.assertEqual(config["sandbox_mode"], "read-only")
                self.assertIn("parent live settings can override", prompt)

    def test_claude_frontmatter_ownership_isolation_and_read_only_tool_pool(self):
        for role in ("implementer", "reviewer"):
            path = ROOT / f".claude/agents/pharmassist-{role}.md"
            header, prompt = path.read_text().split("---\n")[1:]
            fields = quoted_fields(header, ": ")
            self.assertEqual(fields["name"], f"pharmassist-{role}")
            self.assertTrue(fields["description"])
            self.assertEqual(fields["model"], "inherit")
            self.assertEqual(
                set(fields),
                {"name", "description", "tools", "model"}
                | ({"isolation", "skills"} if role == "implementer" else set()),
            )
            for reference in ("docs/DELEGATION.md", "CLAUDE.md", "docs/VERIFY.md"):
                self.assertIn(reference, prompt)
            if role == "reviewer":
                self.assertEqual(fields["tools"], "Read, Grep, Glob")
            else:
                self.assertEqual(fields["isolation"], "worktree")
                self.assertEqual(fields["skills"], ["delegate"])

    def test_provider_checks_need_no_backend_runtime_or_third_party_parsers(self):
        # Simulate the Python 3.9 frontend-only runner without a local backend venv.
        # An external --python backend selection must not be needed for these checks.
        with (
            patch.object(Path, "exists", side_effect=AssertionError("No venv lookup permitted")),
            patch.object(subprocess, "check_output", side_effect=AssertionError("No subprocess")),
            patch.dict(sys.modules, {"tomllib": None, "yaml": None}),
        ):
            self.test_codex_toml_is_valid_and_contains_only_supported_role_fields()
            self.test_claude_frontmatter_ownership_isolation_and_read_only_tool_pool()

    def test_role_subset_rejects_duplicates_and_unquoted_values(self):
        for source in ("name: unquoted", 'name: "one"\nname: "two"'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                quoted_fields(source, ": ")

    def test_only_team_presets_are_trackable_in_clean_clone(self):
        with tempfile.TemporaryDirectory(prefix="pa-roles-") as temporary:
            root = Path(temporary)
            env = {**verify.environment("unused"), "GIT_CONFIG_NOSYSTEM": "1"}
            env["GIT_CONFIG_GLOBAL"] = os.devnull
            subprocess.run(["git", "init", "-q", root], check=True, env=env)
            shutil.copy(ROOT / ".gitignore", root / ".gitignore")
            for provider, suffix in ((".claude", "md"), (".codex", "toml")):
                for name in ("pharmassist-implementer", "pharmassist-reviewer", "personal"):
                    path = root / provider / "agents" / f"{name}.{suffix}"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.touch()
                    code = subprocess.run(
                        [
                            "git",
                            "-c",
                            "core.excludesfile=/dev/null",
                            "check-ignore",
                            "-q",
                            str(path),
                        ],
                        cwd=root,
                        env=env,
                    ).returncode
                    self.assertEqual(code, int(name != "personal"), path)


if __name__ == "__main__":
    unittest.main()
