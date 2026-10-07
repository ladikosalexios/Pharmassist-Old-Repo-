"""Deterministic overlay of the supplied EOF template, with explicit continuation pages."""

import hashlib
import io
import json
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader, PdfWriter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from ..schemas.yellow_card import ReportData

ASSETS = Path(__file__).resolve().parents[1] / "assets" / "yellow-card"
LAYOUT = json.loads((ASSETS / "layout.json").read_text())
TEMPLATE_VERSION = LAYOUT["version"]
for name, file in [("YC", "NotoSans-Regular.ttf"), ("YC-Bold", "NotoSans-Bold.ttf")]:
    pdfmetrics.registerFont(TTFont(name, str(ASSETS / file)))


def normalize_signature(raw: bytes) -> bytes:
    if len(raw) > 1_000_000:
        raise ValueError("Η εικόνα υπογραφής είναι πολύ μεγάλη")
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.format != "PNG" or source.width * source.height > 2_000_000:
                raise ValueError("Απαιτείται εικόνα PNG έως 2 megapixels")
            im = source.convert("RGBA")
            # Empty/white canvases carry no visible ink. Keep only dark, nontransparent ink.
            pixels = list(im.getdata())
            ink = Image.new("RGBA", im.size)
            ink.putdata(
                [
                    (0, 0, 0, a) if a > 16 and min(r, g, b) < 200 else (0, 0, 0, 0)
                    for r, g, b, a in pixels
                ]
            )
            box = ink.getbbox()
            if not box or (box[2] - box[0]) * (box[3] - box[1]) < 16:
                raise ValueError("Σχεδιάστε την υπογραφή σας πριν την αποθήκευση")
            ink = ink.crop(box)
            out = Image.new("RGBA", (ink.width + 16, ink.height + 16))
            out.paste(ink, (8, 8))
            buf = io.BytesIO()
            out.save(buf, format="PNG")
            return buf.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Μη έγκυρη εικόνα υπογραφής") from exc


def display(value):
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%d/%m/%Y")
    return str(value)


def paragraph(text, size=8.5):
    return Paragraph(
        escape(display(text)).replace("\n", "<br/>"),
        ParagraphStyle("yc", fontName="YC", fontSize=size, leading=size * 1.15),
    )


def render_pdf(data: ReportData, signature: bytes, reference: str) -> bytes:
    original = (ASSETS / "KITRINI-KARTA_2021.pdf").read_bytes()
    if hashlib.sha256(original).hexdigest() != LAYOUT["template_sha256"]:
        raise RuntimeError("Yellow Card template checksum changed; review layout before rendering")
    source = PdfReader(io.BytesIO(original))
    width, height = map(float, source.pages[0].mediabox[2:])
    overlay = io.BytesIO()
    c = canvas.Canvas(overlay, pagesize=(width, height), invariant=1)
    continuations = []

    def fits(text, key, size):
        x, top, w, h = LAYOUT["fields"][key]
        p = paragraph(text, size)
        _, ph = p.wrap(w, h)
        return ph <= h

    def paint(text, key, size=8.5):
        if not display(text):
            return
        x, top, w, h = LAYOUT["fields"][key]
        p = paragraph(text, size)
        _, ph = p.wrap(w, h)
        p.drawOn(c, x, height - top - ph)

    def field(text, key, label=None):
        if fits(text, key, 8.5):
            paint(text, key)
        elif fits(text, key, 7.5):
            paint(text, key, 7.5)
        else:
            continuations.append((label or key, display(text)))
            paint(f"[{len(continuations)}]", key, 7.5)

    labels = {
        "initials": "Αρχικά ασθενούς",
        "age": "Ηλικία",
        "weight": "Βάρος",
        "height": "Ύψος",
        "death_cause": "Αιτία θανάτου",
        "death_date": "Ημερομηνία θανάτου",
        "observations": "Συμπληρωματικές παρατηρήσεις",
        "reporter_name": "Όνομα αναφέροντος",
        "reporter_address": "Διεύθυνση αναφέροντος",
        "reporter_institution": "Ίδρυμα",
        "reporter_phone": "Τηλέφωνο",
        "report_date": "Ημερομηνία αναφοράς",
    }
    for key in [
        "initials",
        "age",
        "weight",
        "height",
        "death_cause",
        "death_date",
        "observations",
        "reporter_name",
        "reporter_address",
        "reporter_institution",
        "reporter_phone",
        "report_date",
    ]:
        value = getattr(data, key)
        if key == "observations" and data.reporter_email:
            value = f"Email αναφέροντος: {data.reporter_email}\n{value}"
        field(value, key, labels[key])

    def tick(key):
        x, top = LAYOUT["checkboxes"][key]
        y = height - top
        c.setLineWidth(0.8)
        c.line(x - 2, y, x, y - 2)
        c.line(x, y - 2, x + 3, y + 3)

    if data.sex:
        tick(data.sex)
    if data.serious is not None:
        tick("serious_yes" if data.serious else "serious_no")
    for key in data.seriousness:
        tick(key)
    tick("pharmacist")
    for kind, rows, capacity, attrs in [
        ("reaction", data.reactions, 5, ["description", "onset", "end", "outcome"]),
        (
            "suspected",
            data.suspected,
            2,
            ["name", "lot", "route", "dose", "start", "end", "indication"],
        ),
        (
            "concomitant",
            data.concomitant,
            5,
            ["name", "lot", "route", "dose", "start", "end", "indication"],
        ),
    ]:
        used = 0
        for index, row in enumerate(rows):
            values = {key: display(getattr(row, key)) for key in attrs}
            if kind == "reaction" and row.onset_unknown:
                values["onset"] = "Άγνωστη"
            # Never split a medicine/reaction across unrelated rows.
            if used < capacity and all(
                fits(v, f"{kind}.{used}.{k}", 7.5) for k, v in values.items()
            ):
                for key, value in values.items():
                    field(value, f"{kind}.{used}.{key}")
                used += 1
            else:
                table_labels = {
                    "reaction": "Αντίδραση",
                    "suspected": "Ύποπτο φάρμακο",
                    "concomitant": "Συγχορηγούμενο φάρμακο",
                }
                column_labels = {
                    "description": "Περιγραφή",
                    "onset": "Έναρξη",
                    "end": "Λήξη",
                    "outcome": "Έκβαση",
                    "name": "Ονομασία",
                    "lot": "Παρτίδα",
                    "route": "Οδός",
                    "dose": "Δόση",
                    "start": "Έναρξη",
                    "indication": "Ένδειξη",
                }
                continuations.append(
                    (
                        f"{table_labels[kind]} {index + 1}",
                        " · ".join(f"{column_labels[k]}: {v}" for k, v in values.items() if v),
                    )
                )
                if used < capacity:
                    paint(f"[{len(continuations)}]", f"{kind}.{used}.{attrs[0]}", 7.5)
                    used += 1
    x, top, w, h = LAYOUT["fields"]["signature"]
    c.drawImage(
        ImageReader(io.BytesIO(signature)),
        x,
        height - top - h,
        width=w,
        height=h,
        preserveAspectRatio=True,
        anchor="c",
        mask="auto",
    )
    # Local-only notice is outside the original form's entry regions and tested separately.
    c.setFont("YC-Bold", 7)
    c.drawCentredString(
        width / 2, height - 20, "ΤΟΠΙΚΗ ΔΟΚΙΜΗ — ΣΥΝΘΕΤΙΚΑ ΔΕΔΟΜΕΝΑ — ΔΕΝ ΥΠΟΒΑΛΛΕΤΑΙ ΣΤΟΝ ΕΟΦ"
    )
    c.setFont("YC", 6)
    c.drawCentredString(width / 2, 12, f"PharmAssist · {reference} · {TEMPLATE_VERSION}")
    if continuations:
        c.drawString(60, height - 685, "Συνέχεια: βλ. πρόσθετες σελίδες και αριθμημένες αναφορές.")
    c.save()
    writer = PdfWriter()
    writer.add_page(source.pages[0])
    writer.add_page(source.pages[1])
    writer.pages[0].merge_page(PdfReader(overlay).pages[0])
    if continuations:
        buf = io.BytesIO()
        cc = canvas.Canvas(buf, pagesize=(width, height), invariant=1)
        y = height - 65
        page = 3

        def header():
            cc.setFont("YC-Bold", 10)
            cc.drawString(
                40, height - 30, "Κίτρινη Κάρτα — Συμπληρωματικά στοιχεία (τοπική δοκιμή)"
            )
            cc.setFont("YC", 8)
            cc.drawString(40, height - 44, f"Αναφορά {reference} · Σελίδα {page}")

        header()
        for i, (label, value) in enumerate(continuations, 1):
            p = paragraph(f"[{i}] {label}\n{value}")
            while True:
                _, ph = p.wrap(width - 80, y - 40)
                if ph <= y - 40:
                    p.drawOn(cc, 40, y - ph)
                    y -= ph + 14
                    break
                parts = p.split(width - 80, y - 40)
                if parts:
                    first = parts[0]
                    _, fh = first.wrap(width - 80, y - 40)
                    first.drawOn(cc, 40, y - fh)
                    if len(parts) == 1:
                        break
                    p = parts[1]
                cc.showPage()
                page += 1
                header()
                y = height - 65
        cc.save()
        for page_obj in PdfReader(buf).pages:
            writer.add_page(page_obj)
    writer.add_metadata({"/Title": "PharmAssist — Κίτρινη Κάρτα — τοπική δοκιμή"})
    result = io.BytesIO()
    writer.write(result)
    return result.getvalue()
