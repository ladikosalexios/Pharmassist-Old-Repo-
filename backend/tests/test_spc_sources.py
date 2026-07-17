"""Tests for the SPC source adapters (services/spc_sources/)."""

import asyncio
import base64
import io
import os

os.environ.setdefault("ENV", "test")
os.environ.setdefault("PHARMAPI_MOCK", "true")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", base64.b64encode(b"\x01" * 32).decode())
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("PHARMAPI_USERNAME", "u")
os.environ.setdefault("PHARMAPI_PASSWORD", "p")
os.environ.setdefault("PHARMAPI_API_KEY", "k")

import httpx  # noqa: E402
import pytest  # noqa: E402
from openpyxl import Workbook  # noqa: E402

from app.db.models.drug_catalog import DrugCatalog  # noqa: E402
from app.services.spc_sources import base, ema, eof  # noqa: E402


@pytest.fixture(autouse=True)
def _no_throttle(monkeypatch):
    async def instant(source):  # noqa: ARG001
        return None

    monkeypatch.setattr(base, "_throttle", instant)
    monkeypatch.setattr(eof, "_throttle", instant)
    monkeypatch.setattr(ema, "_throttle", instant)
    yield
    base._transport = None
    ema._dataset = None
    ema._dataset_loaded_at = 0.0


def _product(**kw) -> DrugCatalog:
    defaults = dict(gns_code="2801234567890", atc_code="N05AH03", name_gr="OLENXA 20MG")
    defaults.update(kw)
    return DrugCatalog(**defaults)


# ── ΕΟΦ adapter ──────────────────────────────────────────────────────────────

EOF_HOME = """
<html><body><form id="searchForm">
<input type="hidden" name="javax.faces.ViewState" value="VS-123" />
</form></body></html>
"""

EOF_RESULTS = """
<html><body><table>
<tr><td>
  <a href="/human-search/document?uuid=abc" title="ΠΧΠ">Περίληψη Χαρακτηριστικών</a>
  <a href="/human-search/document?uuid=def" title="ΦΟΧ">Φύλλο Οδηγιών Χρήσης</a>
  <a href="/human-search/other">Άλλο</a>
</td></tr>
</table></body></html>
"""


def test_eof_happy_path():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text=EOF_HOME)
        assert request.method == "POST"
        body = request.content.decode()
        assert "VS-123" in body  # ViewState echoed back
        return httpx.Response(200, text=EOF_RESULTS)

    base._transport = httpx.MockTransport(handler)
    result = asyncio.run(eof.resolve(_product(eof_code="12345")))
    assert result.error is None
    types = {d.doc_type for d in result.docs}
    assert types == {"spc", "pil"}
    assert all(d.url.startswith("https://services.eof.gr/") for d in result.docs)


def test_eof_missing_viewstate_is_contained():
    base._transport = httpx.MockTransport(lambda r: httpx.Response(200, text="<html/>"))
    result = asyncio.run(eof.resolve(_product()))
    assert result.docs == []
    assert "ViewState" in result.error


def test_eof_transport_failure_is_contained():
    def boom(request):
        raise httpx.ConnectError("network down")

    base._transport = httpx.MockTransport(boom)
    result = asyncio.run(eof.resolve(_product()))
    assert result.docs == []
    assert "eof:" in result.error


def test_eof_no_links_is_contained():
    def handler(request):
        return httpx.Response(200, text=EOF_HOME if request.method == "GET" else "<html/>")

    base._transport = httpx.MockTransport(handler)
    result = asyncio.run(eof.resolve(_product(eof_code="12345")))
    assert result.docs == []
    assert "no ΠΧΠ/ΦΟΧ" in result.error


# ── EMA adapter ──────────────────────────────────────────────────────────────


def _dataset_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["Category", "Medicine name", "Medicine URL"])
    ws.append(
        [
            "Human",
            "Olanzapine Test",
            "https://www.ema.europa.eu/en/medicines/human/EPAR/olanzapine-test",
        ]
    )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_ema_resolves_via_dataset_and_head():
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith(".xlsx"):
            return httpx.Response(200, content=_dataset_xlsx())
        if request.method == "HEAD":
            return httpx.Response(200)
        raise AssertionError(f"unexpected request {url}")

    base._transport = httpx.MockTransport(handler)
    result = asyncio.run(ema.resolve(_product(name_en="Olanzapine Test")))
    assert result.error is None
    (doc,) = result.docs
    assert doc.doc_type == "combined"
    assert doc.url.endswith("olanzapine-test-epar-product-information_el.pdf")


def test_ema_falls_back_to_page_scrape():
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith(".xlsx"):
            return httpx.Response(200, content=_dataset_xlsx())
        if request.method == "HEAD":
            return httpx.Response(404)
        if "medicines/human" in url:
            return httpx.Response(
                200,
                text='<a href="/documents/product-information/olanzapine-test-epar-product-information_el.pdf">EL</a>',
            )
        raise AssertionError(f"unexpected request {url}")

    base._transport = httpx.MockTransport(handler)
    result = asyncio.run(ema.resolve(_product(name_en="Olanzapine Test")))
    assert result.error is None
    assert result.docs[0].url.startswith("https://www.ema.europa.eu/documents/")


def test_ema_no_match_is_contained():
    base._transport = httpx.MockTransport(lambda r: httpx.Response(200, content=_dataset_xlsx()))
    result = asyncio.run(ema.resolve(_product(name_en="Nonexistol", name_gr="ΑΝΥΠΑΡΚΤΟ")))
    assert result.docs == []
    assert "no dataset match" in result.error


def test_ema_dataset_failure_is_contained():
    def boom(request):
        raise httpx.ConnectError("down")

    base._transport = httpx.MockTransport(boom)
    result = asyncio.run(ema.resolve(_product(name_en="Olanzapine Test")))
    assert result.docs == []
    assert "ema:" in result.error


# ── download() plumbing ──────────────────────────────────────────────────────


def test_download_size_cap(monkeypatch):
    base._transport = httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * 64))
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "spc_max_pdf_bytes", 10, raising=False)
    with pytest.raises(ValueError):
        asyncio.run(base.download("https://example.org/big.pdf", source="eof"))
