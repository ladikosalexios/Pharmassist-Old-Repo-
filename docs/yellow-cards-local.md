# Yellow Card local workspace

The pharmacist flow follows the supplied recording: edit a structured Greek report, save a drawn signature, review the completed original EOF PDF, approve the exact email/PDF, and capture it in Mailpit. Only synthetic data belongs in this development workspace.

## Start and sign in

From the PharmAssist repository:

```sh
docker compose -f compose.yellow-cards.local.yaml up --build -d
```

- App: http://localhost:5174/login
- Select **Κίτρινη Κάρτα — τοπική δοκιμή χωρίς ΗΔΥΚΑ**.
- Synthetic account: `yellow.demo@example.com` / `Local-yellow-2026!`
- Captured mail: http://127.0.0.1:8026
- Local API: http://127.0.0.1:8001/docs

The app's three Mailpit shortcuts (top of the page, the captured submission and the history) open `http://127.0.0.1:8026` by default. If your stack publishes Mailpit on another port, pass the optional `VITE_YELLOW_CARDS_MAILPIT_URL` into the frontend container through a Compose override. Exporting it in your shell alone does not forward it to this service. For example, save this as `/tmp/yellow-card-inbox.yaml`, using your stack's actual published inbox URL:

```yaml
services:
  frontend:
    environment:
      VITE_YELLOW_CARDS_MAILPIT_URL: http://127.0.0.1:8028
```

With the stack already running, apply that override and rebuild/recreate only the frontend:

```sh
docker compose -f compose.yellow-cards.local.yaml -f /tmp/yellow-card-inbox.yaml up -d --no-deps --build frontend
```

Keep any other overrides your stack uses in that command too. This setting changes only the link destinations, not published ports or mail transport. When running Vite directly outside Docker, set the variable in the frontend process environment and restart it; production bundles need rebuilding with it. Unset, blank or non-http(s) values keep the default.

Setup applies migrations and non-destructively creates the synthetic account. The stack uses its own database and mail volumes and does not touch another PharmAssist or Second Opinion stack. Rebuild after source changes. All published ports bind to loopback. A gateway exposes the UI and inbox; backend, worker, database and Mailpit remain on an internal network with no external route. SMTP is not published. Mailpit has no relay configuration.

The development encryption/session keys and account are intentionally public test values, not production credentials. `YELLOW_CARDS_MODE=local_capture` is rejected outside development/test. The default remains `disabled`. `PHARMAPI_ENABLED=false` skips upstream secrets, login verification, startup probes and keepalive. Reporting-session cookies are server-restricted to reporting and identity endpoints, even if a full-session upstream context exists in the process.

## Try the workflow

1. Click **Συμπλήρωση συνθετικού παραδείγματος** or enter synthetic information manually. Drafts may be incomplete and can be saved/reopened.
2. Draw a signature with mouse, touch or stylus. Undo, clear and save are available. Replacement/revocation invalidates unsubmitted previews; historical PDFs retain their embedded image.
3. Confirm synthetic data and use of the saved signature. Generate the PDF, inspect both original pages and any continuation pages, and review the email.
4. Approve and send. The queue becomes `CAPTURED_LOCAL` when Mailpit accepts SMTP. This is never EOF submission or acknowledgment.
5. Open Mailpit and inspect `yellow-card.pdf`. The worker sends the stored artifact; it never regenerates the approved PDF.

An owned database ADR can also start a draft from the Side Effects screen when reporting is enabled. No patient name, AMKA or prescription identifier is imported. Mock/fallback ADR rows are not imported.

A changed report revision or signature requires a new preview. Duplicate submission requests return the original submission. `QUEUED` can be cancelled. `FAILED` means a known rejection/pre-send failure; after fixing the local service, create a new preview and approve another attempt. `UNKNOWN` means SMTP might have accepted it: inspect Mailpit using the submission ID in `X-PharmAssist-Submission-ID` / Message-ID before considering another send. There are no automatic retries after an uncertain outcome, nor automated EOF follow-ups/corrections.

## Implementation boundaries

- `yellow_reports`: encrypted current drafts with optimistic revision checks.
- `yellow_signatures`: private normalized PNG versions. Raw stroke timing/pressure stays in browser memory and is discarded.
- `yellow_previews`: immutable encrypted revision snapshot, final PDF and email envelope/body, with hashes and template/signature versions.
- `yellow_submissions`: approval record plus transactional outbox. Approval/queue/event commit together. Owner lock serializes signature, report and approval mutations. Worker claims use row locks with `SKIP LOCKED`, commit before SMTP, and quarantine interrupted claims after five minutes.
- `yellow_events`: clinical-content-free delivery transition events.

AES-256-GCM uses a dedicated `YELLOW_CARDS_KEY` and binds ciphertext to its row and purpose. Artifact/image responses are owner-scoped and `no-store`. Clinical fields and signatures are not logged. The drawn image and approval record do not constitute a certificate-backed PDF signature.

The versioned template is `KITRINI-KARTA_2021.pdf` (SHA-256 `98dc0472671ea0b53283beab6502e81b07517e800a3bd450ad7cb7baca296ca7`). `layout.json` uses top-left PDF-point rectangles. Noto Sans is bundled under the adjacent OFL licence. Checkbox centres were extracted from the PDF structure. Text overlays use 8.5 points, reducing only to 7.5 before moving content to numbered continuation pages. Complete medicine/reaction rows stay together. The original instructions page is retained unchanged; a local-test banner/footer is added to page one.

## Verification

Frontend: `npm run typecheck`, `npm run lint`, `npm run format:check`, `npm test`, `npm run build` from `frontend/`.

Backend unit/visual tests: `pytest -q tests/test_yellow_pdf.py`. Run using the pinned PDFium dependency in `requirements-dev.txt`; the reference PNG contains only synthetic information. When updating the template/layout or rendering libraries, render and visually inspect the synthetic example before replacing the baseline. Tests also check unchanged pixels outside entry regions and exact preservation of page two; do not blindly update snapshots.

Real-database tests (`tests/test_yellow_cards_db.py`) cover ownership, no upstream calls, stale signatures/revisions, encryption, simultaneous duplicate submissions, concurrent worker claims and interrupted delivery. The shared verifier runs them, with no Docker stack, in its disposable socket-only PostgreSQL cluster:

```sh
python3 scripts/verify.py --backend-only --with-db --pg-bin /path/to/postgresql/16/bin
```

It migrates a fresh database, runs the other database suites, then runs this module last with `YELLOW_TEST_DATABASE_URL` set to that private database only. Any skip, an empty run or a missing result fails verification. CI's `backend-db` job runs the same command on PostgreSQL 16. The default DB-less run explicitly excludes the module rather than skipping it. Mail stays mocked; see [VERIFY.md](VERIFY.md#yellow-card-suite).

To run it against this Compose stack instead, use an isolated test database:

```sh
docker build -f backend/Dockerfile.yellow-test -t pharmassist-yellow-tests backend
docker compose -f compose.yellow-cards.local.yaml exec db createdb -U yellow yellow_tests
```

Use the reporting environment from the Compose file, with `ENV=test` and both `DATABASE_URL` and `YELLOW_TEST_DATABASE_URL` set to `postgresql+asyncpg://yellow:local-yellow@db:5432/yellow_tests`. Run `alembic upgrade head`, then `pytest -q tests/test_yellow_cards_db.py` in the test image on network `pharmassist-yellow_default`. Without `YELLOW_TEST_DATABASE_URL` the module skips itself, so check that all its tests ran.

## Stop and clear

```sh
# Stop; retain reports and captured messages.
docker compose -f compose.yellow-cards.local.yaml down
# Deliberately delete this workspace's synthetic reports, signatures and messages.
docker compose -f compose.yellow-cards.local.yaml down --volumes
```

Local data has no scheduled purge; use the explicit cleanup command. Live EOF mail, AWS SES, production retention/backups, real-patient onboarding and certificate signing are deferred. No production configuration was changed.
