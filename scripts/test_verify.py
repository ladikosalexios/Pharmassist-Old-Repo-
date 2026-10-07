"""Offline regressions for verification boundaries and portable agent hooks."""

import argparse
import contextlib
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import agent_hooks as hooks
import verify


class HarnessTests(unittest.TestCase):
    def test_environment_does_not_inherit_production_settings(self):
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "production",
                "LLM_API_KEY": "secret",
                "SENTRY_DSN": "secret",
                "PYTEST_ADDOPTS": "--ignore=tests",
            },
        ):
            env = verify.environment("private-test-url")
        self.assertEqual(env["DATABASE_URL"], "private-test-url")
        self.assertEqual(env["PHARMAPI_MOCK"], "true")
        self.assertEqual(env["LLM_MOCK"], "true")
        self.assertEqual(env["PHARMAPI_KEEPALIVE_ENABLED"], "false")
        self.assertEqual(env["PYTHON_DOTENV_DISABLED"], "1")
        self.assertFalse(set(env) & {"LLM_API_KEY", "SENTRY_DSN", "PYTEST_ADDOPTS"})

    def test_private_database_has_no_tcp_listener_and_cleans_up_on_failure(self):
        commands = []
        root = None

        def execute(command, cwd, env, **kwargs):
            nonlocal root
            commands.append([str(c) for c in command])
            if "initdb" in str(command[0]):
                data = Path(command[command.index("-D") + 1])
                data.mkdir()
                root = data.parent
            if "start" in command:
                (root / "data/postmaster.pid").write_text("synthetic")
            if "stop" in command:
                (root / "data/postmaster.pid").unlink()

        with (
            patch.object(verify.shutil, "which", return_value=sys.executable),
            patch.object(verify, "must", side_effect=execute),
        ):
            # Use named stub paths, because which above would hide each tool name.
            with tempfile.TemporaryDirectory() as binaries:
                for name in ("initdb", "pg_ctl", "createdb", "psql"):
                    (Path(binaries) / name).touch()
                with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
                    with verify.private_postgres(binaries) as (env, _, sockets):
                        self.assertIn(str(sockets), env["DATABASE_URL"])
                        raise RuntimeError("synthetic failure")
        self.assertTrue(any("listen_addresses=''" in item for cmd in commands for item in cmd))
        self.assertTrue(any("--auth-host=reject" in cmd for cmd in commands))
        self.assertTrue(any("stop" in cmd for cmd in commands))
        self.assertFalse(root.exists())

    def test_selected_scope_reports_failures_and_exclusions(self):
        commands = []

        def execute(command, cwd, env, **kwargs):
            commands.append([str(c) for c in command])
            return 1 if "ruff" in command and "check" in command else 0

        args = argparse.Namespace(
            frontend_only=False,
            backend_only=True,
            with_db=False,
            quick=False,
            python=sys.executable,
            pg_bin=None,
        )
        with (
            patch.object(verify, "call", side_effect=execute),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(verify.verify(args), 1)
        pytest = next(cmd for cmd in commands if "pytest" in cmd)
        self.assertEqual(
            {p for p in pytest if p.startswith("--ignore=")},
            {f"--ignore=tests/{p}" for p in verify.DB_TESTS},
        )
        self.assertEqual(len(verify.DB_TESTS), 7)
        self.assertTrue(any("format" in cmd for cmd in commands))
        self.assertFalse(any("npm" in cmd for cmd in commands))

    def test_failed_database_prerequisites_report_every_unrun_suite(self):
        args = argparse.Namespace(
            frontend_only=False,
            backend_only=True,
            with_db=True,
            quick=False,
            python=sys.executable,
            pg_bin=None,
        )
        for failure in ("setup", "fixtures"):
            with self.subTest(failure=failure):
                output = io.StringIO()

                @contextlib.contextmanager
                def database(*args, failure=failure):
                    if failure == "setup":
                        raise RuntimeError("synthetic setup failure")
                    yield {}, "synthetic-psql", Path("/unused-synthetic-socket")

                with (
                    patch.object(verify, "call", return_value=0),
                    patch.object(verify, "private_postgres", database),
                    patch.object(verify, "must", side_effect=RuntimeError("fixture failure")),
                    contextlib.redirect_stdout(output),
                ):
                    self.assertEqual(verify.verify(args), 1)
                report = output.getvalue()
                for suite in verify.DB_TESTS:
                    self.assertIn(
                        f"NOT RUN: database prerequisites failed: Database suite: {suite}", report
                    )
                if failure == "setup":
                    self.assertIn(
                        "NOT RUN: database prerequisites failed: Fresh database migrations", report
                    )
                else:
                    self.assertIn("PASS: Fresh database migrations", report)

    def test_failed_database_stop_retains_directory_and_reports_path(self):
        root = None

        def execute(command, cwd, env, **kwargs):
            nonlocal root
            if "initdb" in str(command[0]):
                data = Path(command[command.index("-D") + 1])
                data.mkdir()
                root = data.parent
            if "start" in command:
                (root / "data/postmaster.pid").write_text("synthetic")
            if "stop" in command:
                raise RuntimeError("synthetic stop failure")

        output = io.StringIO()
        try:
            with tempfile.TemporaryDirectory() as binaries:
                for name in ("initdb", "pg_ctl", "createdb", "psql"):
                    (Path(binaries) / name).touch()
                with (
                    patch.object(verify, "must", side_effect=execute),
                    contextlib.redirect_stderr(output),
                    self.assertRaisesRegex(RuntimeError, "synthetic stop failure"),
                    verify.private_postgres(binaries),
                ):
                    pass
            self.assertTrue((root / "data/postmaster.pid").exists())
            self.assertIn(f"retained {root}", output.getvalue())
        finally:
            if root is not None:
                # The process and PID file were synthetic; remove only this test's directory.
                verify.shutil.rmtree(root)

    def test_sigterm_stops_before_any_later_stage(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "calls"
            script = (
                "import signal,sys,time\nfrom pathlib import Path\n"
                f"sys.path.insert(0,{str(verify.ROOT / 'scripts')!r})\nimport verify\n"
                "def fake(*a,**kw):\n"
                f" with Path({str(marker)!r}).open('a') as f: f.write('call\\n')\n"
                " time.sleep(30)\n return 0\n"
                "verify.call=fake\nsignal.signal(signal.SIGTERM,verify.interrupted)\n"
                "sys.argv=['verify','--backend-only']\nsys.exit(verify.main())\n"
            )
            process = subprocess.Popen(
                [sys.executable, "-c", script], stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            try:
                deadline = time.monotonic() + 5
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(marker.exists())
                process.send_signal(signal.SIGTERM)
                process.communicate(timeout=5)
                self.assertEqual(process.returncode, 130)
                self.assertEqual(marker.read_text(), "call\n")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()

    def test_dotenv_is_disabled_before_backend_imports(self):
        # Exercise the real bootstrap with harmless stub packages instead of loading app settings.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "dotenv").mkdir()
            (root / "dotenv/__init__.py").write_text("from .main import load_dotenv\n")
            (root / "dotenv/main.py").write_text(
                "def load_dotenv(*a,**kw): raise RuntimeError('must not load .env')\n"
            )
            (root / "pytest.py").write_text(
                "def main(args):\n import dotenv, dotenv.main\n"
                " assert dotenv.load_dotenv() is False\n"
                " assert dotenv.main.load_dotenv() is False\n return 0\n"
            )
            env = {**os.environ, "PYTHONPATH": str(root)}
            code = subprocess.run(
                [sys.executable, str(verify.ROOT / "scripts/verify_backend.py"), "pytest"], env=env
            ).returncode
            self.assertEqual(code, 0)


class HookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pharmassist hooks ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for directory in ("backend", "frontend", "scripts"):
            (self.root / directory).mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        (self.root / "baseline").write_text("base")
        subprocess.run(["git", "add", "baseline"], cwd=self.root, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-qm",
                "base",
            ],
            cwd=self.root,
            check=True,
        )

    def test_stop_finds_work_without_claude_variable_and_propagates_failure(self):
        (self.root / "backend/changed.py").write_text("changed")
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(hooks, "changed_paths", return_value={"backend/changed.py"}),
            patch.object(
                hooks.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)
            ) as run,
        ):
            self.assertEqual(hooks.stop(self.root, {}), 2)
        command = run.call_args.args[0]
        self.assertIn("--backend-only", command)
        self.assertIn("--quick", command)
        self.assertEqual(run.call_args.kwargs["cwd"], self.root)

    def test_pure_conversation_does_not_run_checks(self):
        with (
            patch.object(hooks, "changed_paths", return_value=set()),
            patch.object(hooks.subprocess, "run") as run,
        ):
            self.assertEqual(hooks.stop(self.root, {}), 0)
        run.assert_not_called()

    def test_repeated_stop_allows_failure_report_without_retry_or_false_pass(self):
        output = io.StringIO()
        with patch.object(hooks, "changed_paths") as changed, contextlib.redirect_stdout(output):
            self.assertEqual(hooks.stop(self.root, {"stop_hook_active": True}), 0)
        changed.assert_not_called()
        self.assertIn("not a verification pass", json.loads(output.getvalue())["systemMessage"])

    def test_staged_and_untracked_changes_are_both_seen(self):
        (self.root / "backend/one.py").write_text("one")
        subprocess.run(["git", "add", "backend/one.py"], cwd=self.root, check=True)
        (self.root / "frontend/two.ts").write_text("two")
        self.assertEqual(hooks.changed_paths(self.root), {"backend/one.py", "frontend/two.ts"})

    def test_formatter_reads_stdin_and_handles_spaces_from_other_cwd(self):
        target = self.root / "frontend/file with spaces.ts"
        target.write_text("const x=1;")
        tool = self.root / "frontend/node_modules/.bin/prettier"
        tool.parent.mkdir(parents=True)
        tool.write_text('#!/bin/sh\nprintf formatted > "$2"\n')
        tool.chmod(0o700)
        (self.root / "scripts/agent_hooks.py").write_bytes(Path(hooks.__file__).read_bytes())
        wrapper = self.root / ".codex/hooks/format-on-edit.sh"
        wrapper.parent.mkdir(parents=True)
        wrapper.write_bytes((verify.ROOT / ".codex/hooks/format-on-edit.sh").read_bytes())
        result = subprocess.run(
            ["bash", str(wrapper)],
            cwd="/tmp",
            input=json.dumps({"tool_input": {"file_path": str(target)}}),
            text=True,
            capture_output=True,
            env={"PATH": os.environ["PATH"]},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(target.read_text(), "formatted")

    def test_formatter_rejects_outside_and_symlink_escape(self):
        (self.root / "frontend/link.ts").symlink_to("/etc/hosts")
        for name in ("/etc/hosts", str(self.root / "frontend/link.ts")):
            with self.assertRaisesRegex(ValueError, "outside"):
                hooks.format_edit(self.root, {"tool_input": {"file_path": name}})

    def test_codex_and_claude_configs_are_portable(self):
        for agent, config in ((".codex", "hooks.json"), (".claude", "settings.json")):
            data = json.loads((verify.ROOT / agent / config).read_text())
            for groups in data["hooks"].values():
                for group in groups:
                    for hook in group["hooks"]:
                        command = hook["command"]
                        self.assertNotIn("/Users/", command)
                        self.assertNotIn("CLAUDE_PROJECT_DIR", command)
                        self.assertIn("git rev-parse --show-toplevel", command)
        self.assertFalse((verify.ROOT / "AGENTS.md").is_symlink())
        self.assertTrue((verify.ROOT / "CLAUDE.md").is_file())
        for name in ("audit-log", "screen-convert"):
            self.assertTrue((verify.ROOT / ".agents/skills" / name / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
