"""Synthetic-only PDF, signature and mail tests; no live services required."""

import hashlib
import io
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pypdfium2 as pdfium
import pytest
from PIL import Image, ImageChops, ImageDraw
from pypdf import PdfReader

from app.schemas.yellow_card import Medicine, Reaction, ReportData
from app.services import yellow_crypto
from app.services.yellow_mail import LocalCaptureTransport, compose_message
from app.services.yellow_pdf import ASSETS, LAYOUT, normalize_signature, render_pdf


def signature():
    im = Image.new("RGBA", (600, 200))
    draw = ImageDraw.Draw(im)
    draw.line(
        [(30, 130), (80, 40), (110, 140), (150, 70), (190, 120), (250, 90), (390, 140), (560, 65)],
        fill="black",
        width=5,
    )
    out = io.BytesIO()
    im.save(out, format="PNG")
    return normalize_signature(out.getvalue())


def example():
    return ReportData(
        initials="Δ.Α.",
        age="67",
        weight="88",
        height="190",
        sex="male",
        serious=True,
        seriousness=["hospitalisation"],
        reactions=[Reaction(description="Δοκιμαστικό εξάνθημα", onset="2026-10-01", outcome=2)],
        suspected=[
            Medicine(
                name="Δοκιμαστικό Α",
                lot="LOT123",
                route="Στόμα",
                dose="1 / ημέρα",
                start="2026-09-30",
                indication="Δοκιμή",
            )
        ],
        observations="Συνθετικά δεδομένα. Καμία πραγματική αναφορά.",
        reporter_name="Δοκιμαστικός Φαρμακοποιός",
        reporter_address="Οδός Δοκιμής 1, Αθήνα",
        reporter_phone="2100000000",
        reporter_email="demo@example.test",
        report_date="2026-10-07",
    )


def render_image(pdf, page=0):
    doc = pdfium.PdfDocument(pdf)
    image = doc[page].render(scale=150 / 72).to_pil().convert("RGB")
    doc.close()
    return image


def test_signature_blank_invalid_and_limits():
    out = io.BytesIO()
    Image.new("RGBA", (600, 200), "white").save(out, format="PNG")
    for raw in [out.getvalue(), b"not an image", b"x" * 1_000_001]:
        with pytest.raises(ValueError):
            normalize_signature(raw)
    im = Image.open(io.BytesIO(signature()))
    assert im.mode == "RGBA" and im.width < 600 and not im.info


def test_pdf_contents_template_preserved_and_golden():
    pdf = render_pdf(example(), signature(), "SYNTHETIC-TEST")
    doc = PdfReader(io.BytesIO(pdf))
    text = " ".join(page.extract_text() for page in doc.pages)
    assert len(doc.pages) == 2
    for value in [
        "Δ.Α.",
        "Δοκιμαστικό εξάνθημα",
        "LOT123",
        "Δοκιμαστικός Φαρμακοποιός",
        "07/10/2026",
    ]:
        assert value in text
    source = (ASSETS / "KITRINI-KARTA_2021.pdf").read_bytes()
    assert ImageChops.difference(render_image(source, 1), render_image(pdf, 1)).getbbox() is None
    actual = render_image(pdf)
    golden = Path(__file__).parent / "fixtures/yellow-card/golden.png"
    assert golden.exists(), "Generate and visually review the synthetic golden before committing it"
    assert ImageChops.difference(actual, Image.open(golden).convert("RGB")).getbbox() is None
    # Outside entries and the declared local-test banner/footer, preserve the official form.
    diff = ImageChops.difference(actual, render_image(source))
    mask = ImageDraw.Draw(diff)
    scale = 150 / 72
    for x, y, w, h in LAYOUT["fields"].values():
        mask.rectangle(
            ((x - 2) * scale, (y - 2) * scale, (x + w + 2) * scale, (y + h + 2) * scale),
            fill="black",
        )
    for x, y in LAYOUT["checkboxes"].values():
        mask.rectangle(
            ((x - 5) * scale, (y - 5) * scale, (x + 5) * scale, (y + 5) * scale), fill="black"
        )
    mask.rectangle((0, 0, actual.width, 25 * scale), fill="black")
    mask.rectangle((0, actual.height - 20 * scale, actual.width, actual.height), fill="black")
    assert diff.getbbox() is None


def test_overflow_keeps_complete_rows_and_escapes_markup():
    data = example()
    data.observations = "<b>Αναφορά</b> " + ("Μεγάλο κείμενο με ελληνικούς τόνους. " * 200)
    data.suspected = [Medicine(name=f"Φάρμακο-{i}", dose="Δόση " * 30) for i in range(8)]
    pdf = render_pdf(data, signature(), "OVERFLOW")
    doc = PdfReader(io.BytesIO(pdf))
    text = " ".join(p.extract_text() for p in doc.pages)
    assert len(doc.pages) > 2
    for i in range(8):
        assert f"Φάρμακο-{i}" in text
    assert "<b>Αναφορά</b>" in text
    assert "Συνέχεια" in text


def test_encrypt_context_and_mail_attachment(monkeypatch):
    monkeypatch.setattr(
        yellow_crypto,
        "get_settings",
        lambda: SimpleNamespace(yellow_cards_key="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="),
    )
    data = b"private"
    encrypted = yellow_crypto.seal(data, "one")
    assert data not in encrypted
    from cryptography.exceptions import InvalidTag

    with pytest.raises(InvalidTag):
        yellow_crypto.unseal(encrypted, "two")
    import json

    pdf = render_pdf(example(), signature(), "EMAIL")
    envelope = json.dumps(
        {
            "to": "yellowcard@eof.test",
            "from": "yellow-cards@pharmassist.test",
            "reply_to": "pharmacist@pharmassist.test",
            "subject": "Δοκιμή",
            "body": "Τοπική δοκιμή",
        }
    ).encode()
    preview = SimpleNamespace(
        id="p",
        pdf=yellow_crypto.seal(pdf, "pdf:p"),
        sha256=hashlib.sha256(pdf).hexdigest(),
        envelope=yellow_crypto.seal(envelope, "envelope:p"),
        envelope_sha256=hashlib.sha256(envelope).hexdigest(),
    )
    msg = compose_message(SimpleNamespace(id="s", approved_at=datetime.now(UTC)), preview)
    assert list(msg.iter_attachments())[0].get_payload(decode=True) == pdf
    assert msg["To"] == "yellowcard@eof.test"
    preview.sha256 = "tampered"
    with pytest.raises(ValueError):
        compose_message(SimpleNamespace(id="s"), preview)


@pytest.mark.parametrize(
    "failure,expected", [("connect", "FAILED"), ("send", "UNKNOWN"), ("none", "CAPTURED_LOCAL")]
)
def test_smtp_failure_boundaries(failure, expected):
    from app.services import yellow_mail

    with (
        patch.object(
            yellow_mail,
            "get_settings",
            return_value=SimpleNamespace(yellow_cards_mode="local_capture"),
        ),
        patch.object(yellow_mail.smtplib, "SMTP") as smtp,
    ):
        if failure == "connect":
            smtp.return_value.connect.side_effect = OSError("offline")
        if failure == "send":
            smtp.return_value.send_message.side_effect = OSError("lost response")
        assert LocalCaptureTransport().send(None)[0] == expected
        smtp.return_value.connect.assert_called_once_with("mailpit", 1025)
