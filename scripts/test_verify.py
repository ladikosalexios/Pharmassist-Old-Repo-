"""Offline regressions for verification boundaries and portable agent hooks."""

import argparse
import contextlib
import io
import json
import os
import shutil
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


def reporting_call(results):
    """Fake verify.call: return results(command), writing a passing report where one is due."""

    def execute(command, cwd, env, **kwargs):
        command = [str(c) for c in command]
        report = next((c.split("=", 1)[1] for c in command if c.startswith("--junitxml=")), None)
        if verify.HARNESS_COMMAND in command:
            report = command[-1]
        if report:
            Path(report).write_text('<testsuite tests="2" skipped="0" failures="0" errors="0"/>')
        return results(command)

    return execute


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

        def results(command):
            commands.append(command)
            return 1 if "ruff" in command and "check" in command else 0

        args = argparse.Namespace(
            frontend_only=False,
            backend_only=True,
            with_db=False,
            quick=False,
            python=sys.executable,
            pg_bin=None,
        )
        output = io.StringIO()
        with (
            patch.object(verify, "call", side_effect=reporting_call(results)),
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(verify.verify(args), 1)
        self.assertIn("  FAIL: Backend + tooling lint", output.getvalue())
        self.assertIn("  PASS (2 passed): Backend DB-less tests", output.getvalue())
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
                fixtures = []

                def fixture_failure(command, *args, fixtures=fixtures, **kwargs):
                    fixtures.append([str(c) for c in command])
                    raise RuntimeError("fixture failure")

                @contextlib.contextmanager
                def database(*args, failure=failure):
                    if failure == "setup":
                        raise RuntimeError("synthetic setup failure")
                    yield {}, "synthetic-psql", Path("/unused-synthetic-socket")

                with (
                    patch.object(verify, "call", side_effect=reporting_call(lambda command: 0)),
                    patch.object(verify, "private_postgres", database),
                    patch.object(verify, "must", side_effect=fixture_failure),
                    contextlib.redirect_stdout(output),
                ):
                    self.assertEqual(verify.verify(args), 1)
                if failure == "fixtures":
                    # The real wiring, not only the helper, must ignore psql startup files.
                    self.assertEqual(fixtures[0][0], "synthetic-psql")
                    self.assertIn("-X", fixtures[0])
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

    def test_frontend_unit_tests_report_counts(self):
        args = argparse.Namespace(
            frontend_only=True,
            backend_only=False,
            with_db=False,
            quick=False,
            python=sys.executable,
            pg_bin=None,
        )
        output = io.StringIO()

        def results(command):
            report = next((c.split("=", 1)[1] for c in command if "--outputFile.junit=" in c), 0)
            if report:
                Path(report).write_text(
                    '<testsuites><testsuite tests="8" skipped="8"/></testsuites>'
                )
            return 0

        with (
            patch.object(verify, "call", side_effect=reporting_call(results)),
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(verify.verify(args), 1)
        self.assertIn("NOT RUN: 0 passed, 8 skipped: Frontend unit tests", output.getvalue())

    def test_skipped_tests_are_not_reported_as_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "report.xml"
            self.assertEqual(verify.outcome(1, report), "FAIL")
            self.assertEqual(verify.outcome(0), "PASS")
            self.assertEqual(verify.outcome(0, report), "FAIL: no test report")
            report.write_text(
                '<testsuites><testsuite tests="7" skipped="7" failures="0" errors="0"/>'
                "</testsuites>"
            )
            self.assertEqual(verify.outcome(0, report), "NOT RUN: 0 passed, 7 skipped")
            report.write_text('<testsuite tests="5" skipped="1" failures="0" errors="0"/>')
            self.assertEqual(verify.outcome(0, report), "PASS (4 passed, 1 skipped)")

    def test_fully_skipped_database_suite_fails_verification(self):
        args = argparse.Namespace(
            frontend_only=False,
            backend_only=True,
            with_db=True,
            quick=False,
            python=sys.executable,
            pg_bin=None,
        )

        @contextlib.contextmanager
        def database(*args):
            yield {}, "synthetic-psql", Path("/unused-synthetic-socket")

        def results(command):
            report = next((c.split("=", 1)[1] for c in command if "--junitxml=" in c), None)
            if report and any(c.endswith(verify.DB_TESTS[0]) for c in command):
                # e.g. fixtures silently missing: every test skips, pytest still exits 0.
                Path(report).write_text('<testsuite tests="3" skipped="3"/>')
            return 0

        output = io.StringIO()
        with (
            patch.object(verify, "call", side_effect=reporting_call(results)),
            patch.object(verify, "private_postgres", database),
            patch.object(verify, "must"),
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(verify.verify(args), 1)
        self.assertIn(
            f"NOT RUN: 0 passed, 3 skipped: Database suite: {verify.DB_TESTS[0]}",
            output.getvalue(),
        )

    def test_harness_runner_counts_skips(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "scripts").mkdir()
            (root / "scripts/test_sample.py").write_text(
                "import unittest\n"
                "class T(unittest.TestCase):\n"
                " def test_runs(self): pass\n"
                " @unittest.skip('synthetic') \n"
                " def test_skips(self): pass\n"
            )
            with (
                patch.object(verify, "ROOT", root),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(verify.harness_tests(root / "report.xml"), 0)
            self.assertEqual(verify.report_counts(root / "report.xml"), (1, 1))

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


@unittest.skipUnless(
    "PA_VERIFY_PG_BIN" in os.environ,
    "needs real PostgreSQL tools; runs under verify.py --with-db",
)
class FixtureStartupFileTests(unittest.TestCase):
    """Real psql against the harness's own disposable socket-only cluster, never another DB."""

    SCHEMA = (
        "CREATE TABLE pharmacies (name text, pharmapi_unit_id int, active bool);"
        "CREATE TABLE pharmacists (email text, password_hash text, full_name text,"
        " eof_licence_no text, role text, active bool);"
    )

    def test_fixture_load_ignores_synthetic_psql_startup_files(self):
        pg_bin = os.environ["PA_VERIFY_PG_BIN"]
        names = ("initdb", "pg_ctl", "createdb", "psql")
        real = {n: str(Path(pg_bin) / n) if pg_bin else shutil.which(n) for n in names}
        self.assertTrue(all(real.values()), real)
        startups = {
            # Each one silently loses the fixtures while psql still exits 0.
            "transaction behaviour": "\\set AUTOCOMMIT off\n",
            "reconnect elsewhere": "\\connect decoy\n",
        }
        for label, startup in startups.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as temporary:
                tools = Path(temporary)
                for name in ("initdb", "pg_ctl", "createdb"):
                    (tools / name).symlink_to(real[name])
                # A synthetic installation whose psql has a startup file, as the system
                # psqlrc, the account's ~/.psqlrc or PSQLRC would supply one.
                (tools / "startup.psqlrc").write_text(startup)
                (tools / "psql").write_text(
                    f'#!/bin/sh\nPSQLRC="{tools}/startup.psqlrc" exec "{real["psql"]}" "$@"\n'
                )
                (tools / "psql").chmod(0o700)
                with verify.private_postgres(tools) as (env, psql, sockets):
                    connect = [real["psql"], "-X", "-h", sockets, "-U", "verify", "-qAt", "-d"]
                    verify.must(
                        [real["createdb"], "-h", sockets, "-U", "verify", "decoy"], verify.ROOT, env
                    )
                    for database in ("pharmassist_verify", "decoy"):
                        verify.must([*connect, database, "-c", self.SCHEMA], verify.ROOT, env)

                    def rows(connect=connect, env=env):
                        query = (
                            "SELECT (SELECT count(*) FROM pharmacies)"
                            " + (SELECT count(*) FROM pharmacists)"
                        )
                        return {
                            database: subprocess.run(
                                [*map(str, connect), database, "-c", query],
                                env=env,
                                check=True,
                                capture_output=True,
                                text=True,
                            ).stdout.strip()
                            for database in ("pharmassist_verify", "decoy")
                        }

                    command = verify.fixture_command(psql, sockets)
                    # Control: the same command without -X proves the startup file is live.
                    control = [c for c in command if c not in ("-X", "--no-psqlrc")]
                    self.assertEqual(
                        verify.call(control, verify.ROOT, env, input=verify.FIXTURE_SQL), 0
                    )
                    before = rows()
                    self.assertEqual(before["pharmassist_verify"], "0")
                    verify.must(command, verify.ROOT, env, input=verify.FIXTURE_SQL)
                    after = rows()
                self.assertEqual(after["pharmassist_verify"], "2")
                self.assertEqual(after["decoy"], before["decoy"])


class FixtureCommandTests(unittest.TestCase):
    def test_fixture_command_never_reads_startup_files(self):
        command = verify.fixture_command("psql", Path("/socket"))
        self.assertTrue({"-X", "--no-psqlrc"} & set(command))
        self.assertEqual(command[command.index("-d") + 1], "pharmassist_verify")


HOOK_FILES = (
    ".claude/settings.json",
    ".claude/hooks/format-on-edit.sh",
    ".claude/hooks/typecheck-on-stop.sh",
    ".codex/hooks.json",
    ".codex/hooks/format-on-edit.sh",
    ".codex/hooks/typecheck-on-stop.sh",
    "scripts/agent_hooks.py",
)
# Stands in for scripts/verify.py: records where it ran, prints plain text like the real log.
STUB_VERIFY = """import os, sys
from pathlib import Path
with open(os.environ["STUB_LOG"], "a") as log:
    log.write(str(Path(__file__).resolve().parents[1]) + "\\n")
print("== plain-text verification log ==")
sys.exit(int(os.environ.get("STUB_EXIT", "0")))
"""


def registered(agent, event):
    config = ".claude/settings.json" if agent == "claude" else ".codex/hooks.json"
    data = json.loads((verify.ROOT / config).read_text())
    return data["hooks"][event][0]["hooks"][0]["command"]


def git(cwd, *args):
    subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            *args,
        ],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


class HookTests(unittest.TestCase):
    def install_project(self):
        """Copy the real hook wiring into the synthetic repository, with a stub runner."""
        for name in HOOK_FILES:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((verify.ROOT / name).read_bytes())
        (self.root / "scripts/verify.py").write_text(STUB_VERIFY)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "hooks")

    def run_hook(self, command, cwd, payload, **env):
        return subprocess.run(
            ["bash", "-c", command],
            cwd=cwd,
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            env={"PATH": os.environ["PATH"], "STUB_LOG": str(self.log), **env},
        )

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pharmassist hooks ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for directory in ("backend", "frontend", "scripts"):
            (self.root / directory).mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        (self.root / "baseline").write_text("base")
        git(self.root, "add", "baseline")
        git(self.root, "commit", "-qm", "base")
        self.log = self.root.parent / f"{self.root.name}.log"
        self.addCleanup(lambda: self.log.unlink(missing_ok=True))

    def test_stop_finds_work_without_claude_variable_and_propagates_failure(self):
        (self.root / "backend/changed.py").write_text("changed")
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(hooks, "changed_paths", return_value={"backend/changed.py"}),
            patch.object(
                hooks.subprocess,
                "run",
                return_value=subprocess.CompletedProcess([], 1, stdout="ruff failed"),
            ) as run,
            contextlib.redirect_stderr(io.StringIO()) as feedback,
        ):
            self.assertEqual(hooks.stop(self.root, {}), 2)
        self.assertIn("ruff failed", feedback.getvalue())
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

    def test_formatter_skips_outside_and_symlink_escape_without_error(self):
        # Agent memory/scratch edits are routine: no formatter, no error fed back.
        tool = self.root / "frontend/node_modules/.bin/prettier"
        tool.parent.mkdir(parents=True)
        tool.write_text(f'#!/bin/sh\necho "$2" >> "{self.log}"\n')
        tool.chmod(0o700)
        outside = Path(self.temp.name + " outside.ts")
        outside.write_text("outside")
        self.addCleanup(outside.unlink)
        (self.root / "frontend/link.ts").symlink_to(outside)
        relative = self.root / "frontend/../../" / outside.name
        for name in (str(outside), str(self.root / "frontend/link.ts"), str(relative)):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(
                    hooks.format_edit(self.root, {"tool_input": {"file_path": name}}), 0
                )
        self.assertFalse(self.log.exists())

    def test_formatter_uses_ruff_force_exclude_like_pre_commit(self):
        python = self.root / "backend/.venv/bin/python"
        python.parent.mkdir(parents=True)
        python.write_text(f'#!/bin/sh\necho "$@" >> "{self.log}"\n')
        python.chmod(0o700)
        (self.root / "backend/alembic").mkdir()
        (self.root / "backend/alembic/migration.py").write_text("x=1")
        hooks.format_edit(
            self.root,
            {"tool_input": {"file_path": str(self.root / "backend/alembic/migration.py")}},
        )
        self.assertIn("ruff format --force-exclude", self.log.read_text())

    def test_formatter_follows_worktree_nested_in_project(self):
        self.install_project()
        nested = self.root / ".claude/worktrees/feature"
        git(self.root, "worktree", "add", "-q", "--detach", str(nested))
        tool = nested / "frontend/node_modules/.bin/prettier"
        tool.parent.mkdir(parents=True)
        tool.write_text('#!/bin/sh\nprintf formatted > "$2"\n')
        tool.chmod(0o700)
        target = nested / "frontend/page.ts"
        target.write_text("original")
        hooks.format_edit(self.root, {"tool_input": {"file_path": str(target)}})
        self.assertEqual(target.read_text(), "formatted")

    def test_planted_gitfile_is_not_followed_as_a_worktree(self):
        self.install_project()
        (self.root / "backend/changed.py").write_text("changed")
        planted = Path(self.temp.name + " planted")
        self.addCleanup(shutil.rmtree, planted, True)
        (planted / "scripts").mkdir(parents=True)
        (planted / "scripts/verify.py").write_text(STUB_VERIFY)
        (planted / ".git").write_text(f"gitdir: {self.root / '.git'}\n")
        result = self.run_hook(
            registered("claude", "Stop"),
            planted,
            {"cwd": str(planted)},
            CLAUDE_PROJECT_DIR=str(self.root),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log.read_text().splitlines(), [str(self.root.resolve())])

    def test_claude_commands_report_missing_project_directory(self):
        for event in ("Stop", "PostToolUse"):
            result = self.run_hook(registered("claude", event), self.root, {})
            # Non-blocking (not 2, which could loop) and not silent.
            self.assertEqual(result.returncode, 1)
            self.assertIn("CLAUDE_PROJECT_DIR is not set", result.stderr)

    def test_formatter_scope_matches_pre_commit(self):
        tool = self.root / "frontend/node_modules/.bin/prettier"
        tool.parent.mkdir(parents=True)
        tool.write_text('#!/bin/sh\nprintf formatted > "$2"\n')
        tool.chmod(0o700)
        expected = {
            "frontend/src/notes.md": "formatted",
            "docs/PricingNotes.md": "original",
            "CLAUDE.md": "original",
            ".github/workflows/review.yml": "original",
            "frontend/dist/bundle.js": "original",
        }
        for name in expected:
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            (self.root / name).write_text("original")
            hooks.format_edit(self.root, {"tool_input": {"file_path": str(self.root / name)}})
        self.assertEqual({n: (self.root / n).read_text() for n in expected}, expected)

    def test_tooling_only_changes_run_harness_checks(self):
        for changed in (".codex/hooks.json", ".claude/settings.json", ".agents/skills/x"):
            with (
                patch.object(hooks, "changed_paths", return_value={changed}),
                patch.object(
                    hooks.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "")
                ) as run,
            ):
                self.assertEqual(hooks.stop(self.root, {}), 0)
            self.assertIn("--backend-only", run.call_args.args[0])

    def test_registered_stop_never_runs_another_repositorys_hooks(self):
        self.install_project()
        (self.root / "backend/changed.py").write_text("changed")
        foreign = Path(self.temp.name + " foreign")
        self.addCleanup(shutil.rmtree, foreign, True)
        for agent in (".claude", ".codex"):
            script = foreign / agent / "hooks/typecheck-on-stop.sh"
            script.parent.mkdir(parents=True)
            script.write_text(f'touch "{foreign}/FOREIGN-HOOK-RAN"\n')
        subprocess.run(["git", "init", "-q"], cwd=foreign, check=True)
        # Claude Code's hook cwd follows `cd`; its project directory does not.
        result = self.run_hook(
            registered("claude", "Stop"),
            foreign,
            {"cwd": str(foreign)},
            CLAUDE_PROJECT_DIR=str(self.root),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((foreign / "FOREIGN-HOOK-RAN").exists())
        self.assertEqual(self.log.read_text().splitlines(), [str(self.root.resolve())])

    def test_registered_commands_outside_git_never_block_repeatedly(self):
        self.install_project()
        outside = Path(self.temp.name + " outside")
        outside.mkdir()
        self.addCleanup(shutil.rmtree, outside, True)
        payload = {"cwd": str(outside), "stop_hook_active": True}
        for agent in ("claude", "codex"):
            for event in ("Stop", "PostToolUse"):
                with self.subTest(agent=agent, event=event):
                    result = self.run_hook(
                        registered(agent, event),
                        outside,
                        {**payload, "tool_input": {"file_path": str(outside / "x.md")}},
                        CLAUDE_PROJECT_DIR=str(self.root),
                    )
                    # Exit 2 would bypass the repeat-stop guard (Codex has no loop cap).
                    self.assertNotEqual(result.returncode, 2, result.stderr)

    def test_stop_follows_agent_into_linked_worktree_and_keeps_stdout_json(self):
        self.install_project()
        linked = Path(self.temp.name + " linked")
        self.addCleanup(shutil.rmtree, linked, True)
        git(self.root, "worktree", "add", "-q", "--detach", str(linked))
        (linked / "backend").mkdir()  # untracked empty directories are not checked out
        (linked / "backend/changed.py").write_text("changed")
        for agent, env in (
            ("claude", {"CLAUDE_PROJECT_DIR": str(self.root)}),
            # Codex runs hooks in the session cwd; worktree sessions use the main hooks.
            ("codex", {}),
        ):
            for code in ("0", "1"):
                with self.subTest(agent=agent, exit=code):
                    self.log.unlink(missing_ok=True)
                    result = self.run_hook(
                        registered(agent, "Stop"),
                        linked / "backend",
                        {"cwd": str(linked / "backend")},
                        STUB_EXIT=code,
                        **env,
                    )
                    self.assertEqual(self.log.read_text().splitlines(), [str(linked.resolve())])
                    # Codex fails a Stop hook whose exit-0 stdout is plain text.
                    self.assertEqual(result.stdout, "")
                    self.assertEqual(result.returncode, 0 if code == "0" else 2)
                    if code == "1":
                        self.assertIn("plain-text verification log", result.stderr)

    def test_codex_and_claude_configs_are_portable(self):
        for agent, config in ((".codex", "hooks.json"), (".claude", "settings.json")):
            data = json.loads((verify.ROOT / agent / config).read_text())
            for groups in data["hooks"].values():
                for group in groups:
                    for hook in group["hooks"]:
                        command = hook["command"]
                        self.assertNotIn("/Users/", command)
                        if agent == ".claude":
                            # Trusted project root, quoted for paths with spaces.
                            self.assertIn('"$CLAUDE_PROJECT_DIR/.claude/hooks/', command)
                        else:
                            # Codex sets no project variable and runs hooks in the session cwd.
                            self.assertIn("git rev-parse --show-toplevel", command)
                            self.assertNotIn("exit 2", command)
        self.assertFalse((verify.ROOT / "AGENTS.md").is_symlink())
        self.assertTrue((verify.ROOT / "CLAUDE.md").is_file())
        for name in ("audit-log", "screen-convert"):
            self.assertTrue((verify.ROOT / ".agents/skills" / name / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
