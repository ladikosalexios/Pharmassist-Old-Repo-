"""Deterministic SPC (ΠΧΠ) / patient-leaflet (ΦΟΧ) section parsing.

The document formats are rigidly templated across the EU: an SPC carries
numbered sections (1 … 6.6, QRD template) and a ΦΟΧ/PIL carries six standard
patient-facing headings — so a deterministic splitter is the extraction core.
The LLM (services/spc_extract.py) only *cleans up* what this module found;
it never replaces it.

PDF text extraction is isolated in ``extract_text`` (pypdf today;
pdfminer.six is the designated fallback if extraction quality on real ΕΟΦ
PDFs proves poor — swap inside that one function).
"""

import io
import re
from collections import Counter

from pypdf import PdfReader

# ── Text extraction ──────────────────────────────────────────────────────────


def extract_text(pdf: bytes) -> str:
    """Whole-document text from a PDF, cleaned for section splitting.

    Cleanups: repeated per-page header/footer lines stripped (any identical
    line appearing on ≥60% of pages when there are ≥3 pages), hyphenated
    line-wraps re-joined, whitespace normalised. Returns "" for image-only
    (no text layer) or unreadable PDFs — callers treat that as parse failure,
    never an exception.
    """
    try:
        reader = PdfReader(io.BytesIO(pdf))
        pages = [(page.extract_text() or "") for page in reader.pages]
    except Exception:
        return ""

    if len(pages) >= 3:
        line_counts: Counter[str] = Counter()
        for text in pages:
            for line in {ln.strip() for ln in text.splitlines() if ln.strip()}:
                line_counts[line] += 1
        threshold = max(2, int(len(pages) * 0.6))
        repeated = {ln for ln, n in line_counts.items() if n >= threshold and len(ln) < 120}
        pages = [
            "\n".join(ln for ln in text.splitlines() if ln.strip() not in repeated)
            for text in pages
        ]

    text = "\n".join(pages)
    # Re-join words hyphen-split across line breaks ("φαρμακο-\nποιό").
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    # Collapse >2 blank lines; strip trailing spaces.
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── Section splitting ────────────────────────────────────────────────────────

# SPC (QRD template): numbered headings like "4.2 Δοσολογία και τρόπος
# χορήγησης" / "4.2 Posology and method of administration". A heading line is
# a number (with optional sub-number) followed by non-numeric title text.
_SPC_HEADING_RE = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2})?)\.?\s+([^\d\s].*)$", re.MULTILINE)

# PIL/ΦΟΧ: six standard headings, numbered 1-6, Greek + English stems.
_PIL_STEMS = (
    (r"τι\s+είναι|what\s+.{0,60}\bis\b", "1"),
    (r"τι\s+πρέπει\s+να\s+γνωρίζετε|what\s+you\s+need\s+to\s+know|before\s+you", "2"),
    (r"πώς\s+να\s+(πάρετε|χρησιμοποιήσετε|λάβετε)|how\s+to\s+(take|use)", "3"),
    (r"πιθαν\S*\s+ανεπιθύμητ|possible\s+side\s+effects", "4"),
    (r"πώς\s+να\s+φυλάσσετε|how\s+to\s+store", "5"),
    (r"περιεχόμεν\S*\s+τ\S*\s+συσκευασία|contents\s+of\s+the\s+pack", "6"),
)
_PIL_HEADING_RES = [
    (re.compile(rf"^\s*{num}\.?\s+(?:{stem})", re.IGNORECASE | re.MULTILINE), num)
    for stem, num in _PIL_STEMS
]


def _slice_between(text: str, marks: list[tuple[int, str]]) -> dict[str, str]:
    """Given sorted (offset, section_id) heading marks, slice section bodies."""
    sections: dict[str, str] = {}
    for i, (start, sid) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        body = text[start:end]
        # Drop the heading line itself.
        body = body.split("\n", 1)[1] if "\n" in body else ""
        body = body.strip()
        if body and sid not in sections:
            sections[sid] = body
    return sections


def split_spc_sections(text: str) -> dict[str, str]:
    """All numbered SPC sections as {section_id: body}.

    Every heading is captured (not only the wanted ones) because a section's
    body ends at the NEXT heading — §4.2's text ends where §4.3 starts.
    """
    marks: list[tuple[int, str]] = []
    for m in _SPC_HEADING_RE.finditer(text):
        sid, title = m.group(1), m.group(2).strip()
        # Guards against body text masquerading as a heading:
        # (a) titles start with a letter;
        # (b) QRD heading titles are noun phrases, never sentences — a line
        #     like "3 έτη. Μετά το άνοιγμα…" (§6.3's shelf-life BODY) starts
        #     with a number and contains sentence punctuation;
        # (c) bare-integer ids (top-level 1..10) are ALL-CAPS in the QRD
        #     template ("1 ΟΝΟΜΑΣΙΑ…", "1 NAME OF…") — a lowercase title on a
        #     bare integer is body text.
        if not re.match(r"^[A-Za-zΑ-Ωα-ωΆ-Ώά-ώ]", title):
            continue
        if ". " in title or title.endswith("."):
            continue
        if "." not in sid:
            letters = [ch for ch in title if ch.isalpha()]
            if letters and sum(ch.isupper() for ch in letters) / len(letters) < 0.8:
                continue
        marks.append((m.start(), sid))
    marks.sort()
    return _slice_between(text, marks)


# The package leaflet (ΦΟΧ) starts here in a combined/multilingual document —
# anchor to the LAST such marker so the SmPC's own numbered sections and any
# table-of-contents never hijack the six patient headings.
_LEAFLET_START_RE = re.compile(
    r"ΦΥΛΛΟ ΟΔΗΓΙ\w*\s+ΧΡΗΣ|PACKAGE LEAFLET|Package leaflet", re.IGNORECASE
)


def split_pil_sections(text: str) -> dict[str, str]:
    """The six standard ΦΟΧ/PIL sections as {"1".."6": body}.

    Real leaflets repeat every heading (a mini table of contents, then the
    body, plus running headers), so within the leaflet block we take each
    heading's LAST occurrence — the actual section, past its TOC echo.
    """
    starts = list(_LEAFLET_START_RE.finditer(text))
    block = text[starts[-1].start() :] if starts else text
    marks: list[tuple[int, str]] = []
    for heading_re, num in _PIL_HEADING_RES:
        hits = list(heading_re.finditer(block))
        if hits:
            marks.append((hits[-1].start(), num))
    marks.sort()
    return _slice_between(block, marks)


# ── Mapping sections → SpcDetails fields ─────────────────────────────────────

_BULLET_RE = re.compile(r"^\s*(?:[-–—•·•]|\d{1,2}[.)])\s+", re.MULTILINE)
_AFTER_OPENING_RE = re.compile(
    r"μετά το άνοιγμα|μετά την ανασύστασ|ανασύστασ|διάλυσ|"
    r"after (?:first )?opening|reconstitut|once opened",
    re.IGNORECASE,
)
_FOOD_RE = re.compile(r"τροφή|φαγητό|γεύμα|φαγητ|food|meal|φαγώσιμ", re.IGNORECASE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;·])\s+")

_MAX_LIST_ITEMS = 12
_MAX_FIELD_CHARS = 1200


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _bullet_split(section: str, cap: int = _MAX_LIST_ITEMS) -> list[str]:
    """Split a section into list items on bullet/numbered-line boundaries.

    Falls back to the whole (cleaned, truncated) section as a single item —
    messy but honest raw text beats losing the content.
    """
    parts = [p for p in _BULLET_RE.split(section) if _clean(p)]
    if not parts:
        return []
    if len(parts) == 1:
        # Single item — bullet marker (if any) already consumed by the split.
        return [_clean(parts[0])[:_MAX_FIELD_CHARS]]
    items = [_clean(p)[:_MAX_FIELD_CHARS] for p in parts]
    # The text before the first bullet is usually a lead-in sentence, not
    # an item — drop it when there are real bullets after it.
    if not _BULLET_RE.match(section.lstrip()) and len(items) > 1:
        items = items[1:]
    return items[:cap]


def _sentences_matching(section: str, pattern: re.Pattern) -> str | None:
    hits = [_clean(s) for s in _SENTENCE_SPLIT_RE.split(section) if s.strip() and pattern.search(s)]
    return " ".join(hits)[:_MAX_FIELD_CHARS] or None


def map_to_details(spc_sections: dict[str, str], pil_sections: dict[str, str]) -> tuple[dict, str]:
    """Map split sections into the SpcDetails-shaped ``parsed`` payload.

    Patient-language (PIL) wording wins for patient-facing fields (storage,
    food); the SPC feeds the professional fields (contraindications,
    precautions, dosage). ``majorInteractions`` is deterministically empty —
    structured {drug, effect} pairs are an LLM-only extraction; the raw §4.5
    text stays reachable via the stored sections/full text.

    Returns (parsed, parse_status) with parse_status ∈ parsed|partial|failed.
    """
    s = spc_sections
    p = pil_sections

    drug_name = _clean(s.get("1", "").split("\n", 1)[0])[:200] or None

    # Patient dosage text is patient-facing → prefer the ΦΟΧ "how to take"
    # section (patient language) over the professional SmPC §4.2.
    dosage_src = p.get("3") or s.get("4.2") or ""
    recommended_dosage = _clean(dosage_src)[:_MAX_FIELD_CHARS] or None

    contraindications = _bullet_split(s["4.3"]) if s.get("4.3") else []
    precautions = _bullet_split(s["4.4"]) if s.get("4.4") else []

    storage_src = p.get("5") or s.get("6.4") or ""
    storage_conditions = _clean(storage_src)[:_MAX_FIELD_CHARS] or None
    after_opening = None
    for candidate in (s.get("6.3"), p.get("5")):
        if candidate:
            after_opening = _sentences_matching(candidate, _AFTER_OPENING_RE)
            if after_opening:
                break
    disposal = None
    if s.get("6.6"):
        disposal = _clean(s["6.6"])[:_MAX_FIELD_CHARS] or None

    food = None
    for candidate in (p.get("3"), s.get("4.2")):
        if candidate:
            food = _sentences_matching(candidate, _FOOD_RE)
            if food:
                break

    parsed = {
        "drugName": drug_name,
        "recommendedDosage": recommended_dosage,
        "contraindications": contraindications,
        "majorInteractions": [],
        "precautions": precautions,
        "storage": (
            {
                "conditions": storage_conditions,
                "afterOpening": after_opening,
                "disposal": disposal,
            }
            if storage_conditions or after_opening or disposal
            else None
        ),
        "foodInstructions": food,
    }

    targets_found = sum(
        1
        for present in (
            recommended_dosage,
            contraindications,
            precautions,
            storage_conditions or after_opening,
            food,
        )
        if present
    )
    if targets_found >= 3:
        status = "parsed"
    elif targets_found >= 1:
        status = "partial"
    else:
        status = "failed"
    return parsed, status
