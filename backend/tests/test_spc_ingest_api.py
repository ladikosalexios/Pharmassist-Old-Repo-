"""Integration tests: SPC upload → parse → serve → verify (runs against the
compose dev DB like tests/test_endpoints_integration.py).

Every spc_documents row created here is deleted in the module teardown so the
dev stack's SPC resolution (review page, instructions) is untouched.
"""

import base64
import io
import os

os.environ.setdefault("ENV", "test")
os.environ.setdefault("PHARMAPI_MOCK", "true")
os.environ.setdefault("LLM_MOCK", "true")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", base64.b64encode(b"\x01" * 32).decode())
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("PHARMAPI_USERNAME", "u")
os.environ.setdefault("PHARMAPI_PASSWORD", "p")
os.environ.setdefault("PHARMAPI_API_KEY", "k")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://pharmassist:pharmassist_dev@localhost:5432/pharmassist",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from app.deps import get_current_user  # noqa: E402
from main import create_app  # noqa: E402

# ATC deliberately chosen to ALSO exist in MOCK_SPC — proves DB documents win.
TEST_ATC = "B01AA03"
TEST_BARCODE = "2800000000017"


def _fake_admin() -> dict:
    return {
        "pharmacist_id": "00000000-0000-0000-0000-000000000000",
        "pharmacy_id": "00000000-0000-0000-0000-000000000000",
        "pharmacy": "TEST",
        "email": "admin@example.com",
        "name": "Admin",
        "eof_licence_no": "EOF-00000",
        "role": "admin",
    }


app = create_app()
app.dependency_overrides[get_current_user] = _fake_admin


@pytest.fixture(scope="module")
def client():
    # The shared async engine pools connections bound to whichever event loop
    # first used them; under a full-suite run an earlier module's loop owns
    # them and this module's TestClient loop would trip "attached to a
    # different loop". Abandon the pool (close=False — the old loop is gone,
    # closing would need it) so connections are recreated on THIS loop.
    import asyncio

    from app.db.session import engine

    asyncio.run(engine.dispose(close=False))
    with TestClient(app) as c:
        yield c
    # Teardown: remove every document row this module created.

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    async def _cleanup():
        eng = create_async_engine(os.environ["DATABASE_URL"])
        try:
            async with eng.begin() as conn:
                await conn.execute(
                    text("DELETE FROM spc_documents WHERE atc_code = :atc"),
                    {"atc": TEST_ATC},
                )
        finally:
            await eng.dispose()

    asyncio.run(_cleanup())


def _make_pdf(lines: list[str]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for line in lines:
        if y < 60:
            c.showPage()
            y = 800
        c.drawString(40, y, line)
        y -= 16
    c.save()
    return buf.getvalue()


SPC_PDF = _make_pdf(
    [
        "1 NAME OF THE MEDICINAL PRODUCT",
        "UPLOADIN 10 mg tablets",
        "4.2 Posology and method of administration",
        "Adults: 10 mg once daily. Take with food.",
        "4.3 Contraindications",
        "- Hypersensitivity to uploadin",
        "- Severe renal impairment",
        "4.4 Special warnings and precautions for use",
        "- Monitor liver function",
        "6.3 Shelf life",
        "2 years. After first opening, use within 60 days.",
        "6.4 Special precautions for storage",
        "Store below 30 C.",
        "6.6 Special precautions for disposal",
        "Dispose via pharmacy take-back.",
    ]
)


def _upload(client, **form):
    data = {"atc_code": TEST_ATC, "doc_type": "spc", **form}
    return client.post(
        "/admin/spc/upload",
        files={"file": ("spc.pdf", SPC_PDF, "application/pdf")},
        data=data,
    )


def test_upload_parses_and_serves(client):
    r = _upload(client, barcode=TEST_BARCODE)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["parse_status"] == "parsed"
    # LLM is mocked — extraction must stay deterministic; [MOCK] text is
    # never persisted into a document.
    assert body["extraction_method"] == "deterministic"

    r2 = client.get(f"/spc/{TEST_ATC}", params={"barcode": TEST_BARCODE})
    assert r2.status_code == 200, r2.text
    spc = r2.json()
    # The ingested document beats the MOCK_SPC entry for the same ATC.
    assert spc["source"] == "upload"
    assert spc["verified"] is False
    assert spc["documentId"]
    assert "10 mg once daily" in spc["recommendedDosage"]
    assert any("Hypersensitivity" in c for c in spc["contraindications"])
    assert "60 days" in spc["storage"]["afterOpening"]
    assert "food" in spc["foodInstructions"].lower()
    assert "[MOCK]" not in str(spc)


def test_upload_is_idempotent_per_sha(client):
    first = _upload(client, barcode=TEST_BARCODE).json()
    second = _upload(client, barcode=TEST_BARCODE).json()
    assert first["id"] == second["id"]


def test_atc_level_resolution_without_barcode(client):
    r = client.get(f"/spc/{TEST_ATC}")
    assert r.status_code == 200
    assert r.json()["source"] == "upload"  # ATC pool still finds the doc


def test_mock_fallback_when_no_documents(client):
    # A10BA02 (metformin) exists only in MOCK_SPC — no doc rows.
    r = client.get("/spc/A10BA02")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "mock"
    assert body["documentId"] is None
    assert body["foodInstructions"]  # the hand-written metformin food text


def test_unknown_atc_404(client):
    assert client.get("/spc/Z99ZZ99").status_code == 404


def test_verify_flips_flag_and_resolution_prefers_verified(client):
    doc_id = client.get(f"/spc/{TEST_ATC}").json()["documentId"]
    r = client.post(f"/spc/documents/{doc_id}/verify", json={"verified": True})
    assert r.status_code == 200 and r.json()["verified"] is True
    assert client.get(f"/spc/{TEST_ATC}").json()["verified"] is True
    # Revoke works too.
    r = client.post(f"/spc/documents/{doc_id}/verify", json={"verified": False})
    assert r.json()["verified"] is False


def test_document_pdf_roundtrip(client):
    doc_id = client.get(f"/spc/{TEST_ATC}").json()["documentId"]
    r = client.get(f"/spc/documents/{doc_id}/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content == SPC_PDF


def test_upload_rejects_garbage_as_failed_not_500(client):
    r = client.post(
        "/admin/spc/upload",
        files={"file": ("junk.pdf", b"not a pdf", "application/pdf")},
        data={"atc_code": TEST_ATC, "doc_type": "spc"},
    )
    # Unreadable PDF is not an HTTP error — it lands as a failed parse with
    # the bytes retained for future re-parse.
    assert r.status_code == 201
    assert r.json()["parse_status"] == "failed"


def test_upload_rejects_unknown_doc_type(client):
    r = client.post(
        "/admin/spc/upload",
        files={"file": ("spc.pdf", SPC_PDF, "application/pdf")},
        data={"atc_code": TEST_ATC, "doc_type": "poster"},
    )
    assert r.status_code == 422


def test_instructions_render_mock_parity(client, monkeypatch):
    # is_mock_pharmapi() re-reads the env per call, so this forces the mock
    # branch even when the surrounding container runs live.
    monkeypatch.setenv("PHARMAPI_MOCK", "true")
    # RX2024-010's first med is metformin (A10BA02, mock SPC); the ingested
    # TEST_ATC doc shouldn't affect it — mock-mode parity stays intact.
    r = client.post(
        "/instructions/generate",
        json={"rxId": "RX2024-010", "language": "el", "options": {}},
    )
    assert r.status_code == 200, r.text
    content = r.json()["content"]
    assert "Take WITH or immediately AFTER meals" in content  # mock metformin SPC text


def test_batch_fetch_scope_validation(client):
    r = client.post("/admin/spc/fetch", json={"scope": "everything"})
    assert r.status_code == 422
    r = client.post("/admin/spc/fetch", json={"scope": "catalog", "top": 5})
    assert r.status_code == 202
