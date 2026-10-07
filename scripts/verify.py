"""PharmAssist verification. No installs, shared databases, live seeds or deployments."""

import argparse
import base64
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
DB_TESTS = (
    "test_endpoints_integration.py",
    "test_v1_tenant_isolation.py",
    "test_b2b_admin_audit.py",
    "test_ai_cache_db.py",
    "test_v1_safety_explain_cache_db.py",
    "test_spc_ingest_api.py",
    "test_v1_retrieval_free_db.py",
)


def environment(database_url):
    """Never inherit database/provider credentials, telemetry or pytest overrides."""
    return {
        **{
            k: os.environ[k]
            for k in ("PATH", "HOME", "TMPDIR", "LANG", "SYSTEMROOT")
            if k in os.environ
        },
        "ENV": "test",
        "CI": "true",
        "PHARMAPI_MOCK": "true",
        "LLM_MOCK": "true",
        "COOKIE_SECURE": "false",
        "SECRET_KEY": "verification-only-not-a-real-secret",
        "PHARMAPI_USERNAME": "verify",
        "PHARMAPI_PASSWORD": "verify",
        "PHARMAPI_API_KEY": "verify",
        "CREDENTIAL_ENCRYPTION_KEY": base64.b64encode(b"\x01" * 32).decode(),
        "PHARMAPI_BASE": "http://127.0.0.1:9/disabled",
        "LLM_API_BASE": "http://127.0.0.1:9/disabled",
        "PHARMAPI_KEEPALIVE_ENABLED": "false",
        "SPC_FETCH_EOF_ENABLED": "false",
        "SPC_FETCH_EMA_ENABLED": "false",
        "PYTHON_DOTENV_DISABLED": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "DATABASE_URL": database_url,
    }


def call(command, cwd, env, *, input=None, timeout=900):
    """Terminate our own process group on interruption/timeout; never other services."""
    print("+ " + " ".join(map(str, command)), flush=True)
    process = subprocess.Popen(
        list(map(str, command)),
        cwd=cwd,
        env=env,
        stdin=subprocess.PIPE if input else None,
        start_new_session=True,
    )
    try:
        process.communicate(input=input.encode() if input else None, timeout=timeout)
        return process.returncode
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()


def must(command, cwd, env, **kwargs):
    code = call(command, cwd, env, **kwargs)
    if code:
        raise RuntimeError(f"Command failed ({code}): {command[0]}")


def database_url(socket_dir):
    return "postgresql+asyncpg://verify@/pharmassist_verify?host=" + quote(
        str(socket_dir), safe="/"
    )


@contextmanager
def private_postgres(pg_bin=None):
    """A new socket-only cluster. No caller-supplied DB URL is accepted."""
    names = ("initdb", "pg_ctl", "createdb", "psql")
    binaries = {name: str(Path(pg_bin) / name) if pg_bin else shutil.which(name) for name in names}
    if any(not path or not Path(path).is_file() for path in binaries.values()):
        raise RuntimeError("--with-db needs initdb, pg_ctl, createdb and psql (PATH or --pg-bin)")
    root = Path(tempfile.mkdtemp(prefix="pa-verify-", dir="/tmp")).resolve()
    try:
        data, sockets = root / "data", root / "socket"
        sockets.mkdir(mode=0o700)
        env = environment(database_url(sockets))
        must(
            [
                binaries["initdb"],
                "-D",
                data,
                "-U",
                "verify",
                "--auth-local=trust",
                "--auth-host=reject",
                "--encoding=UTF8",
                "--locale=C",
            ],
            ROOT,
            env,
        )
        try:
            must(
                [
                    binaries["pg_ctl"],
                    "-D",
                    data,
                    "-l",
                    root / "postgres.log",
                    "-w",
                    "-t",
                    "30",
                    "-o",
                    f"-F -c listen_addresses='' -c unix_socket_directories='{sockets}' "
                    "-c unix_socket_permissions=0700",
                    "start",
                ],
                ROOT,
                env,
            )
            must(
                [binaries["createdb"], "-h", sockets, "-U", "verify", "pharmassist_verify"],
                ROOT,
                env,
            )
            yield env, binaries["psql"], sockets
        finally:
            # A failed/interrupted start can still have left the child server running.
            if (data / "postmaster.pid").exists():
                must(
                    [binaries["pg_ctl"], "-D", data, "-m", "immediate", "-w", "-t", "30", "stop"],
                    ROOT,
                    env,
                )

    finally:
        if (root / "data/postmaster.pid").exists():
            print(f"Private Postgres may still be running; retained {root}", file=sys.stderr)
        else:
            shutil.rmtree(root)


def backend_command(python, action, *arguments):
    return [python, ROOT / "scripts/verify_backend.py", action, *arguments]


def verify(args):
    results = []
    backend = not args.frontend_only
    frontend = not args.backend_only
    python = Path(args.python).absolute() if args.python else ROOT / "backend/.venv/bin/python"
    if not python.is_file() and not args.python:
        python = Path(sys.executable)

    def step(name, command, cwd, env):
        print(f"\n== {name} ==", flush=True)
        try:
            code = call(command, cwd, env)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"ERROR: {exc}", flush=True)
            code = 1
        results.append((name, "PASS" if code == 0 else "FAIL"))
        return code == 0

    with tempfile.TemporaryDirectory(prefix="pa-check-") as temporary:
        scratch = Path(temporary)
        # Even the DB-less subset gets a private, nonexistent socket; never localhost:5432.
        env = environment(database_url(scratch / "no-database"))
        step(
            "Harness and hook regressions",
            [sys.executable, "-m", "unittest", "discover", "-s", "scripts", "-p", "test_*.py"],
            ROOT,
            env,
        )
        if backend:
            step(
                "Backend + tooling lint",
                [
                    python,
                    "-m",
                    "ruff",
                    "check",
                    "--no-cache",
                    ".",
                    "../scripts",
                ],
                ROOT / "backend",
                env,
            )
            step(
                "Backend + tooling format",
                [
                    python,
                    "-m",
                    "ruff",
                    "format",
                    "--check",
                    ".",
                    "../scripts",
                ],
                ROOT / "backend",
                env,
            )
            ignored = [f"--ignore=tests/{name}" for name in DB_TESTS]
            if not args.quick:
                step(
                    "Backend DB-less tests",
                    backend_command(
                        python,
                        "pytest",
                        "-q",
                        "-ra",
                        "-p",
                        "anyio.pytest_plugin",
                        "-p",
                        "no:cacheprovider",
                        *ignored,
                    ),
                    ROOT / "backend",
                    env,
                )
            else:
                results.append(("Backend tests", "EXCLUDED: --quick"))
            if args.with_db:
                try:
                    with private_postgres(args.pg_bin) as (db_env, psql, sockets):
                        migrated = step(
                            "Fresh database migrations",
                            backend_command(python, "alembic", "upgrade", "head"),
                            ROOT / "backend",
                            db_env,
                        )
                        if migrated:
                            # Synthetic FK fixtures, not scripts.seed (which calls Pharmapi).
                            must(
                                [
                                    psql,
                                    "-h",
                                    sockets,
                                    "-U",
                                    "verify",
                                    "-d",
                                    "pharmassist_verify",
                                    "-v",
                                    "ON_ERROR_STOP=1",
                                ],
                                ROOT,
                                db_env,
                                input=(
                                    "INSERT INTO pharmacies (name,pharmapi_unit_id,active) "
                                    "VALUES ('Verification Pharmacy',1,true);\n"
                                    "INSERT INTO pharmacists (email,password_hash,full_name,"
                                    "eof_licence_no,role,active) "
                                    "VALUES ('verify@example.invalid','unusable',"
                                    "'Verification Pharmacist','VERIFY','pharmacist',true);\n"
                                ),
                            )
                            must(backend_command(python, "fixtures"), ROOT / "backend", db_env)
                            for test in DB_TESTS:
                                # Separate processes avoid the application's module-level pools and
                                # dependency overrides leaking between unrelated DB test modules.
                                step(
                                    f"Database suite: {test}",
                                    backend_command(
                                        python,
                                        "pytest",
                                        "-q",
                                        "-ra",
                                        "-p",
                                        "anyio.pytest_plugin",
                                        "-p",
                                        "no:cacheprovider",
                                        f"tests/{test}",
                                    ),
                                    ROOT / "backend",
                                    db_env,
                                )
                        else:
                            results.extend(
                                (f"Database suite: {name}", "NOT RUN: migrations failed")
                                for name in DB_TESTS
                            )
                except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                    print(f"Database verification failed: {exc}", flush=True)
                    results.append(("Private database setup/cleanup", "FAIL"))
                    recorded = {name for name, _ in results}
                    results.extend(
                        (name, "NOT RUN: database prerequisites failed")
                        for name in (
                            "Fresh database migrations",
                            *(f"Database suite: {test}" for test in DB_TESTS),
                        )
                        if name not in recorded
                    )
            else:
                results.extend(
                    (f"Database suite: {name}", "EXCLUDED: use --with-db") for name in DB_TESTS
                )
        else:
            results.append(("Backend checks", "EXCLUDED: --frontend-only"))
        if frontend:
            for name, command in (
                ("Frontend typecheck", ["npm", "run", "typecheck"]),
                ("Frontend lint", ["npm", "run", "lint"]),
                ("Frontend format", ["npm", "run", "format:check"]),
                ("Frontend unit tests", ["npm", "run", "test"]),
                (
                    "Frontend production build",
                    ["npm", "run", "build", "--", "--outDir", str(scratch / "frontend-dist")],
                ),
            ):
                if args.quick and name in ("Frontend unit tests", "Frontend production build"):
                    results.append((name, "EXCLUDED: --quick"))
                    continue
                step(name, command, ROOT / "frontend", env)
        else:
            results.append(("Frontend checks", "EXCLUDED: --backend-only"))
    print("\nVerification coverage:", flush=True)
    for name, outcome in results:
        print(f"  {outcome}: {name}", flush=True)
    failed = any(outcome == "FAIL" or outcome.startswith("NOT RUN") for _, outcome in results)
    print(
        "Verification FAILED."
        if failed
        else "Selected checks PASSED; exclusions above are not passes.",
        flush=True,
    )
    return int(failed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--backend-only", action="store_true")
    group.add_argument("--frontend-only", action="store_true")
    parser.add_argument(
        "--with-db",
        action="store_true",
        help="Run seven DB suites in a disposable socket-only Postgres",
    )
    parser.add_argument(
        "--quick", action="store_true", help="Lint/format/typecheck only, used by Stop hooks"
    )
    parser.add_argument("--pg-bin", help="Directory containing installed PostgreSQL tools")
    parser.add_argument(
        "--python", help="Backend Python interpreter (default backend/.venv/bin/python)"
    )
    args = parser.parse_args()
    if args.frontend_only and args.with_db:
        parser.error("--with-db cannot be combined with --frontend-only")
    if args.quick and args.with_db:
        parser.error("--with-db cannot be combined with --quick")
    try:
        return verify(args)
    except (KeyboardInterrupt, InterruptedError):
        print("Verification interrupted; unfinished checks are NOT RUN.", file=sys.stderr)
        return 130


def interrupted(signum, frame):
    raise KeyboardInterrupt(f"Signal {signum}")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, interrupted)
    sys.exit(main())
