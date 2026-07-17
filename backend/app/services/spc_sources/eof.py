"""ΕΟΦ portal adapter — services.eof.gr/human-search (JSF/ViewState app).

The authoritative source for every Greek-market product's ΠΧΠ (SPC) and ΦΟΧ
(patient leaflet), but a stateful JSF application with no API: this adapter
performs the session dance (GET → cookies + javax.faces.ViewState → POST the
search form → parse result rows → document links). Scraping a JSF app is
brittle BY NATURE — every selector, form-field name, and regex lives in the
CONSTANTS block below so a portal change is a one-block fix, and every
failure is contained into ``AdapterResult.error`` (surfaced via
``spc_fetch_state.last_error`` + the admin status endpoint), never raised.

IMPLEMENTER NOTE: the form-field names below are the plausible JSF ids as of
the last capture; before first live enablement, capture the real names once
with browser devtools against the live portal (submit one search, copy the
form-data keys) and update ONLY this block. The adapter ships disabled
(``spc_fetch_eof_enabled`` defaults False) precisely so this calibration is
an ops step, not a release blocker.
"""

import logging
import re

from lxml import html as lxml_html

from ...db.models.drug_catalog import DrugCatalog
from .base import AdapterResult, FoundDoc, _client, _throttle

logger = logging.getLogger(__name__)

SOURCE = "eof"

# ── CONSTANTS — the ONLY place portal selectors live ─────────────────────────
BASE_URL = "https://services.eof.gr/human-search"
HOME_URL = f"{BASE_URL}/home.xhtml"
_VIEWSTATE_RE = re.compile(
    r'name="javax\.faces\.ViewState"[^>]*value="([^"]+)"',
)
# JSF form + field ids (capture real values per the implementer note above).
FORM_ID = "searchForm"
FIELD_PRODUCT_CODE = "searchForm:productCode"
FIELD_PRODUCT_NAME = "searchForm:productName"
FIELD_SEARCH_BUTTON = "searchForm:searchButton"
# Result rows: anchors whose href points at a document download.
_DOC_LINK_XPATH = "//a[contains(@href, 'document') or contains(@href, 'get_file')]"
# Classify a link as SPC vs PIL from its label text.
_SPC_LABEL_RE = re.compile(r"ΠΧΠ|SPC|χαρακτηριστικ", re.IGNORECASE)
_PIL_LABEL_RE = re.compile(r"ΦΟΧ|φύλλο|οδηγι|leaflet|PIL", re.IGNORECASE)
# ──────────────────────────────────────────────────────────────────────────────


def _classify(label: str) -> str | None:
    if _SPC_LABEL_RE.search(label):
        return "spc"
    if _PIL_LABEL_RE.search(label):
        return "pil"
    return None


def _absolutize(href: str) -> str:
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return f"https://services.eof.gr{href}"
    return f"{BASE_URL}/{href}"


async def resolve(product: DrugCatalog) -> AdapterResult:
    """Find ΠΧΠ/ΦΟΧ document links for one catalog product. Never raises."""
    try:
        await _throttle(SOURCE)
        async with _client(follow_redirects=True) as client:
            # 1. GET the search page → session cookies + ViewState token.
            home = await client.get(HOME_URL)
            home.raise_for_status()
            m = _VIEWSTATE_RE.search(home.text)
            if not m:
                return AdapterResult(error="eof: ViewState token not found on home page")
            viewstate = m.group(1)

            # 2. POST the search — by ΕΟΦ product code when the catalog has
            #    it (exact), else by the brand token of the Greek name.
            form: dict[str, str] = {
                FORM_ID: FORM_ID,
                "javax.faces.ViewState": viewstate,
                FIELD_SEARCH_BUTTON: FIELD_SEARCH_BUTTON,
                FIELD_PRODUCT_CODE: "",
                FIELD_PRODUCT_NAME: "",
            }
            if product.eof_code:
                form[FIELD_PRODUCT_CODE] = product.eof_code
            else:
                brand = (product.name_gr or "").split(" ")[0]
                if not brand:
                    return AdapterResult(error="eof: no eof_code and no name to search by")
                form[FIELD_PRODUCT_NAME] = brand

            await _throttle(SOURCE)
            results = await client.post(HOME_URL, data=form)
            results.raise_for_status()

            # 3. Parse document links out of the results page.
            tree = lxml_html.fromstring(results.text)
            docs: list[FoundDoc] = []
            for a in tree.xpath(_DOC_LINK_XPATH):
                label = " ".join(
                    filter(None, (a.text_content(), a.get("title", ""), a.get("aria-label", "")))
                )
                doc_type = _classify(label)
                href = a.get("href")
                if doc_type and href:
                    docs.append(FoundDoc(url=_absolutize(href), doc_type=doc_type, source=SOURCE))
            if not docs:
                return AdapterResult(error="eof: search returned no ΠΧΠ/ΦΟΧ links")
            return AdapterResult(docs=docs)
    except Exception as exc:
        logger.warning("[spc][eof] resolve failed for %s: %s", product.gns_code, exc)
        return AdapterResult(error=f"eof: {type(exc).__name__}: {exc}")
