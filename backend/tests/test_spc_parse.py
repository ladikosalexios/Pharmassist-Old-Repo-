"""Tests for the deterministic SPC/ΦΟΧ parser (services/spc_parse.py).

Two layers, split deliberately:
- The PDF pipeline (extract_text → split) is exercised with an ENGLISH QRD
  fixture generated in-test with reportlab — the bundled reportlab fonts have
  no Greek glyphs, and real ΕΟΦ PDFs embed their own fonts, so English is the
  honest way to test the PDF layer without binary fixtures in git.
- The Greek heading regexes and field mapping are exercised on plain STRINGS
  (the splitters take text, not PDFs), using realistic Greek section text.
"""

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

from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from app.services.spc_parse import (  # noqa: E402
    _bullet_split,
    extract_text,
    map_to_details,
    split_pil_sections,
    split_spc_sections,
)


def _make_pdf(lines: list[str]) -> bytes:
    """Render plain text lines into a minimal multi-page-capable PDF."""
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


# English QRD-template SPC — same numbered structure real documents carry.
SPC_PDF_LINES = [
    "1 NAME OF THE MEDICINAL PRODUCT",
    "TESTOFEN 500 mg tablets",
    "2 QUALITATIVE AND QUANTITATIVE COMPOSITION",
    "Each tablet contains 500 mg of testofen.",
    "4.1 Therapeutic indications",
    "Symptomatic relief of pain.",
    "4.2 Posology and method of administration",
    "Adults: 500 mg twice daily. Take with food to reduce gastric upset.",
    "4.3 Contraindications",
    "- Hypersensitivity to the active substance",
    "- Severe hepatic impairment",
    "- Active gastric bleeding",
    "4.4 Special warnings and precautions for use",
    "- Renal function should be monitored",
    "- Caution in elderly patients",
    "4.5 Interaction with other medicinal products",
    "Concomitant warfarin increases bleeding risk.",
    "6.3 Shelf life",
    "3 years. After first opening the bottle, use within 30 days.",
    "6.4 Special precautions for storage",
    "Do not store above 25 C.",
    "6.6 Special precautions for disposal",
    "Any unused product should be disposed of in accordance with local requirements.",
]

# Greek text blocks — exercise the Greek heading regexes and field mapping.
GREEK_SPC_TEXT = """\
1 ΟΝΟΜΑΣΙΑ ΤΟΥ ΦΑΡΜΑΚΕΥΤΙΚΟΥ ΠΡΟΪΟΝΤΟΣ
TESTOFEN 500 mg δισκία
4.2 Δοσολογία και τρόπος χορήγησης
Ενήλικες: 500 mg δύο φορές ημερησίως. Να λαμβάνεται με τροφή για μείωση της γαστρικής ενόχλησης.
4.3 Αντενδείξεις
- Υπερευαισθησία στη δραστική ουσία
- Σοβαρή ηπατική ανεπάρκεια
- Ενεργός γαστρορραγία
4.4 Ειδικές προειδοποιήσεις και προφυλάξεις κατά τη χρήση
- Απαιτείται παρακολούθηση της νεφρικής λειτουργίας
- Προσοχή σε ηλικιωμένους ασθενείς
4.5 Αλληλεπιδράσεις με άλλα φαρμακευτικά προϊόντα
Η συγχορήγηση με βαρφαρίνη αυξάνει τον κίνδυνο αιμορραγίας.
6.3 Διάρκεια ζωής
3 έτη. Μετά το άνοιγμα της φιάλης, να χρησιμοποιείται εντός 30 ημερών.
6.4 Ιδιαίτερες προφυλάξεις κατά τη φύλαξη του προϊόντος
Φυλάσσετε σε θερμοκρασία μικρότερη των 25 °C.
6.6 Ιδιαίτερες προφυλάξεις απόρριψης
Κάθε αχρησιμοποίητο προϊόν πρέπει να απορρίπτεται σύμφωνα με τις κατά τόπους ισχύουσες διατάξεις.
"""

GREEK_PIL_TEXT = """\
ΦΥΛΛΟ ΟΔΗΓΙΩΝ ΧΡΗΣΗΣ: ΠΛΗΡΟΦΟΡΙΕΣ ΓΙΑ ΤΟΝ ΧΡΗΣΤΗ
1. Τι είναι το TESTOFEN και ποια είναι η χρήση του
Το TESTOFEN είναι αναλγητικό φάρμακο.
2. Τι πρέπει να γνωρίζετε πριν πάρετε το TESTOFEN
Μην πάρετε το TESTOFEN σε περίπτωση αλλεργίας.
3. Πώς να πάρετε το TESTOFEN
Πάρτε το φάρμακο με το φαγητό ή αμέσως μετά το γεύμα. Καταπιείτε το δισκίο με νερό.
4. Πιθανές ανεπιθύμητες ενέργειες
Ναυτία, ζάλη.
5. Πώς να φυλάσσετε το TESTOFEN
Φυλάσσετε το φάρμακο μακριά από παιδιά. Μετά το άνοιγμα, χρησιμοποιήστε εντός 30 ημερών.
6. Περιεχόμενα της συσκευασίας και λοιπές πληροφορίες
Δισκία των 500 mg σε κυψέλες.
"""


# ── PDF layer (English fixture) ──────────────────────────────────────────────


def test_extract_text_roundtrip():
    text = extract_text(_make_pdf(SPC_PDF_LINES))
    assert "Posology" in text
    assert "TESTOFEN" in text


def test_extract_text_garbage_returns_empty():
    assert extract_text(b"not a pdf at all") == ""


def test_pdf_pipeline_end_to_end_english():
    text = extract_text(_make_pdf(SPC_PDF_LINES))
    sections = split_spc_sections(text)
    assert "500 mg twice daily" in sections["4.2"]
    assert "Hypersensitivity" not in sections["4.2"]  # §4.2 ends at §4.3
    assert "Hypersensitivity" in sections["4.3"]
    parsed, status = map_to_details(sections, {})
    assert status == "parsed"
    assert "with food" in parsed["foodInstructions"].lower()
    assert "30 days" in parsed["storage"]["afterOpening"]


# ── Greek regexes + mapping (string fixtures) ────────────────────────────────


def test_split_spc_sections_greek():
    sections = split_spc_sections(GREEK_SPC_TEXT)
    assert "500 mg δύο φορές" in sections["4.2"]
    assert "Υπερευαισθησία" not in sections["4.2"]
    assert "Υπερευαισθησία" in sections["4.3"]
    assert "νεφρικής λειτουργίας" in sections["4.4"]
    assert "Μετά το άνοιγμα" in sections["6.3"]
    assert "25" in sections["6.4"]
    assert "απορρίπτεται" in sections["6.6"]


def test_split_pil_sections_greek():
    sections = split_pil_sections(GREEK_PIL_TEXT)
    assert "με το φαγητό" in sections["3"]
    assert "μακριά από παιδιά" in sections["5"]
    assert "αλλεργίας" in sections["2"]


def test_map_to_details_full_greek_document():
    spc = split_spc_sections(GREEK_SPC_TEXT)
    pil = split_pil_sections(GREEK_PIL_TEXT)
    parsed, status = map_to_details(spc, pil)

    assert status == "parsed"
    assert parsed["drugName"] and "ΟΝΟΜΑΣΙΑ" not in parsed["drugName"]
    assert "500 mg" in parsed["recommendedDosage"]
    assert any("Υπερευαισθησία" in c for c in parsed["contraindications"])
    assert len(parsed["contraindications"]) == 3
    assert any("νεφρικής" in p for p in parsed["precautions"])
    # Deterministic pass never invents structured interactions.
    assert parsed["majorInteractions"] == []
    # PIL wording wins for patient-facing storage.
    assert "μακριά από παιδιά" in parsed["storage"]["conditions"]
    assert "30 ημερών" in parsed["storage"]["afterOpening"]
    assert "απορρίπτεται" in parsed["storage"]["disposal"]
    # Food guidance prefers the PIL's patient language.
    assert "φαγητό" in parsed["foodInstructions"]


def test_map_to_details_spc_only_fallback_paths():
    spc = split_spc_sections(GREEK_SPC_TEXT)
    parsed, status = map_to_details(spc, {})
    assert status == "parsed"  # SPC alone still covers ≥3 targets
    # Storage falls back to §6.4; food falls back to §4.2's food sentence.
    assert "25" in parsed["storage"]["conditions"]
    assert "τροφή" in parsed["foodInstructions"]


def test_map_to_details_empty_is_failed():
    parsed, status = map_to_details({}, {})
    assert status == "failed"
    assert parsed["contraindications"] == []
    assert parsed["storage"] is None


def test_map_to_details_single_section_is_partial():
    parsed, status = map_to_details({"4.3": "- Υπερευαισθησία"}, {})
    assert status == "partial"
    assert parsed["contraindications"] == ["Υπερευαισθησία"]


# ── Pure helpers ─────────────────────────────────────────────────────────────


def test_bullet_split_fallback_single_block():
    assert _bullet_split("Συνεχές κείμενο χωρίς κουκκίδες.") == ["Συνεχές κείμενο χωρίς κουκκίδες."]


def test_bullet_split_drops_lead_in_and_caps():
    section = "Αντενδείκνυται στις εξής περιπτώσεις:\n" + "\n".join(
        f"- Περίπτωση {i}" for i in range(1, 20)
    )
    items = _bullet_split(section)
    assert len(items) == 12  # capped
    assert items[0] == "Περίπτωση 1"  # lead-in dropped
