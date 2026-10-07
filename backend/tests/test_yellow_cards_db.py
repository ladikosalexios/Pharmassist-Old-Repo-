"""Run separately against the isolated migrated yellow_tests database; no live Pharmapi."""

import os

import pytest

if not os.getenv("YELLOW_TEST_DATABASE_URL"):
    pytest.skip("Requires isolated YELLOW_TEST_DATABASE_URL", allow_module_level=True)

import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import bcrypt
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.db.models.pharmacist import Pharmacist
from app.db.models.pharmacist_pharmacy import PharmacistPharmacy
from app.db.models.pharmacy import Pharmacy
from app.db.models.yellow_card import YellowReport, YellowSubmission
from app.db.session import get_session
from app.routers import auth
from main import create_app
from scripts import yellow_worker
from tests.test_yellow_pdf import example, signature

URL = os.environ["YELLOW_TEST_DATABASE_URL"]
engine = create_async_engine(URL, poolclass=NullPool)
sessions = async_sessionmaker(engine, expire_on_commit=False)


async def session_override():
    async with sessions() as db:
        yield db


@pytest.fixture()
def app(monkeypatch):
    settings = get_settings().model_copy(
        update={
            "yellow_cards_mode": "local_capture",
            "pharmapi_enabled": False,
            "yellow_cards_key": "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
        }
    )
    monkeypatch.setattr("app.routers.yellow_cards.get_settings", lambda: settings)
    monkeypatch.setattr("app.services.yellow_crypto.get_settings", lambda: settings)
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_session] = session_override

    async def seed():
        async with sessions() as db:
            ids = []
            for _ in range(2):
                ident = uuid.uuid4()
                pharmacy = Pharmacy(name="Synthetic", pharmapi_unit_id=0, active=True)
                pharmacist = Pharmacist(
                    id=ident,
                    email=f"{ident}@example.com",
                    password_hash=bcrypt.hashpw(
                        b"test-password", bcrypt.gensalt(rounds=4)
                    ).decode(),
                    full_name="Δοκιμή",
                    eof_licence_no=str(ident),
                    active=True,
                )
                db.add_all([pharmacy, pharmacist])
                await db.flush()
                db.add(
                    PharmacistPharmacy(
                        pharmacist_id=ident, pharmacy_id=pharmacy.id, is_default=True
                    )
                )
                ids.append(pharmacist.email)
            await db.commit()
            return ids

    application.test_emails = asyncio.run(seed())
    return application


def login(app, index=0):
    client = TestClient(app)
    response = client.post(
        "/auth/login",
        json={"email": app.test_emails[index], "password": "test-password", "mode": "reporting"},
    )
    assert response.status_code == 200, response.text
    return client


def prepared(client):
    sig = client.post(
        "/yellow-cards/signature", files={"file": ("sig.png", signature(), "image/png")}
    )
    assert sig.status_code == 201, sig.text
    report = client.post("/yellow-cards", json=example().model_dump(mode="json"))
    assert report.status_code == 201, report.text
    request = {"revision": 1, "signature_id": sig.json()["id"], "synthetic_data": True}
    preview = client.post(f"/yellow-cards/{report.json()['id']}/previews", json=request)
    assert preview.status_code == 201, preview.text
    return report.json(), sig.json(), preview.json()


def test_local_login_isolation_stale_approval_and_history(app, monkeypatch):
    upstream = AsyncMock(side_effect=AssertionError("Must not call Pharmapi"))
    monkeypatch.setattr(auth, "verify_pharmapi_credentials_with_decrypted", upstream)
    a = login(app)
    b = login(app, 1)
    assert a.get("/auth/me").json()["pharmapi_username"] is None
    assert a.get("/prescriptions").status_code == 403
    report, sig, preview = prepared(a)
    assert b.get("/yellow-cards").json() == []
    assert b.get(f"/yellow-cards/artifacts/{preview['id']}").status_code == 404
    assert b.get(f"/yellow-cards/signature/{sig['id']}/image").status_code == 404
    assert (
        b.patch(
            f"/yellow-cards/{report['id']}", json={"revision": 1, "data": report["data"]}
        ).status_code
        == 404
    )
    payload = {"preview_id": preview["id"], "approved": True}
    headers = {"Idempotency-Key": str(uuid.uuid4())}
    response = a.post("/yellow-cards/submissions", json=payload, headers=headers)
    assert response.status_code == 202, response.text
    assert (
        a.post("/yellow-cards/submissions", json=payload, headers=headers).json()["id"]
        == response.json()["id"]
    )
    assert (
        a.post(
            "/yellow-cards/submissions",
            json={**payload, "preview_id": str(uuid.uuid4())},
            headers=headers,
        ).status_code
        == 409
    )
    assert (
        a.post(
            "/yellow-cards/submissions",
            json={**payload, "approved": False},
            headers={"Idempotency-Key": "false"},
        ).status_code
        == 422
    )
    # New preview and revision become stale after a change.
    p = a.post(
        f"/yellow-cards/{report['id']}/previews",
        json={"revision": 1, "signature_id": sig["id"], "synthetic_data": True},
    ).json()
    assert (
        a.patch(
            f"/yellow-cards/{report['id']}", json={"revision": 1, "data": report["data"]}
        ).status_code
        == 200
    )
    assert (
        a.patch(
            f"/yellow-cards/{report['id']}", json={"revision": 1, "data": report["data"]}
        ).status_code
        == 409
    )
    assert (
        a.post(
            "/yellow-cards/submissions",
            json={"preview_id": p["id"], "approved": True},
            headers={"Idempotency-Key": "stale"},
        ).status_code
        == 409
    )
    a.delete("/yellow-cards/signature")
    assert a.get(f"/yellow-cards/signature/{sig['id']}/image").status_code == 404
    assert a.get(f"/yellow-cards/artifacts/{preview['id']}").status_code == 200
    upstream.assert_not_called()


def test_concurrent_submissions_worker_and_encrypted_storage(app, monkeypatch):
    a = login(app)
    report, sig, preview = prepared(a)

    def send(_):
        with TestClient(app) as c:
            c.cookies.update(a.cookies)
            return c.post(
                "/yellow-cards/submissions",
                json={"preview_id": preview["id"], "approved": True},
                headers={"Idempotency-Key": "same-click"},
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(send, range(2)))
    assert all(r.status_code == 202 for r in responses), [r.text for r in responses]
    assert responses[0].json()["id"] == responses[1].json()["id"]
    captured = []

    class Capture:
        def send(self, msg):
            captured.append(msg)
            return "CAPTURED_LOCAL", None

    monkeypatch.setattr(yellow_worker, "AsyncSessionLocal", sessions)
    monkeypatch.setattr(yellow_worker, "LocalCaptureTransport", Capture)

    async def run():
        # Only this test's queue; cancel unrelated prior tests' queued rows.
        async with sessions() as db:
            rows = (
                await db.scalars(
                    select(YellowSubmission).where(YellowSubmission.status == "QUEUED")
                )
            ).all()
            for row in rows:
                if str(row.id) != responses[0].json()["id"]:
                    row.status = "CANCELLED"
            r = await db.get(YellowReport, uuid.UUID(report["id"]))
            assert "Δοκιμαστικό".encode() not in r.payload
            await db.commit()
        await asyncio.gather(yellow_worker.once(), yellow_worker.once())
        async with sessions() as db:
            row = await db.get(YellowSubmission, uuid.UUID(responses[0].json()["id"]))
            assert row.status == "CAPTURED_LOCAL"
            row.status = "SENDING"
            row.attempted_at = datetime.now(UTC) - timedelta(minutes=6)
            await db.commit()
        await yellow_worker.once()
        async with sessions() as db:
            row = await db.get(YellowSubmission, uuid.UUID(responses[0].json()["id"]))
            assert row.status == "UNKNOWN"

    asyncio.run(run())
    assert len(captured) == 1
    attachment = list(captured[0].iter_attachments())[0].get_payload(decode=True)
    assert attachment == a.get(f"/yellow-cards/artifacts/{preview['id']}").content


def test_revoked_signature_cancellation_and_membership(app):
    client = login(app)
    report, sig, preview = prepared(client)
    client.delete("/yellow-cards/signature")
    response = client.post(
        "/yellow-cards/submissions",
        json={"preview_id": preview["id"], "approved": True},
        headers={"Idempotency-Key": "revoked"},
    )
    assert response.status_code == 409
    report, sig, preview = prepared(client)
    submission = client.post(
        "/yellow-cards/submissions",
        json={"preview_id": preview["id"], "approved": True},
        headers={"Idempotency-Key": "cancel"},
    ).json()
    assert (
        client.post(f"/yellow-cards/submissions/{submission['id']}/cancel").json()["status"]
        == "CANCELLED"
    )

    async def remove_membership():
        from sqlalchemy import delete

        async with sessions() as db:
            ident = await db.scalar(
                select(Pharmacist.id).where(Pharmacist.email == app.test_emails[0])
            )
            await db.execute(
                delete(PharmacistPharmacy).where(PharmacistPharmacy.pharmacist_id == ident)
            )
            await db.commit()

    asyncio.run(remove_membership())
    assert client.get("/auth/me").status_code == 401
    assert client.get(f"/yellow-cards/artifacts/{preview['id']}").status_code == 401


def test_migration_rejects_invalid_revision(app):
    from sqlalchemy.exc import IntegrityError

    client = login(app)
    report = client.post("/yellow-cards", json=example().model_dump(mode="json")).json()

    async def reject():
        async with sessions() as db:
            row = await db.get(YellowReport, uuid.UUID(report["id"]))
            row.revision = 0
            with pytest.raises(IntegrityError, match="ck_yellow_reports_positive_revision"):
                await db.flush()
            await db.rollback()

    asyncio.run(reject())
