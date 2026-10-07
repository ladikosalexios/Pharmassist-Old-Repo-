"""One concrete transport: isolated Mailpit SMTP. No arbitrary host or live adapter."""

import hashlib
import json
import smtplib
from email.message import EmailMessage
from email.policy import SMTP

from ..config import get_settings
from .yellow_crypto import unseal


def compose_message(submission, preview):
    pdf = unseal(preview.pdf, f"pdf:{preview.id}")
    raw = unseal(preview.envelope, f"envelope:{preview.id}")
    if (
        hashlib.sha256(pdf).hexdigest() != preview.sha256
        or hashlib.sha256(raw).hexdigest() != preview.envelope_sha256
    ):
        raise ValueError("artifact_integrity")
    envelope = json.loads(raw)
    if (
        envelope["to"] != "yellowcard@eof.test"
        or envelope["from"] != "yellow-cards@pharmassist.test"
        or envelope["reply_to"] != "pharmacist@pharmassist.test"
    ):
        raise ValueError("local_envelope_only")
    msg = EmailMessage(policy=SMTP)
    for key, value in [
        ("From", envelope["from"]),
        ("To", envelope["to"]),
        ("Reply-To", envelope["reply_to"]),
        ("Subject", envelope["subject"]),
    ]:
        msg[key] = value
    msg["Message-ID"] = f"<{submission.id}@pharmassist.test>"
    msg["X-PharmAssist-Submission-ID"] = str(submission.id)
    msg["Date"] = submission.approved_at
    msg.set_content(envelope["body"])
    msg.add_attachment(pdf, maintype="application", subtype="pdf", filename="yellow-card.pdf")
    return msg


class LocalCaptureTransport:
    def send(self, msg):
        if get_settings().yellow_cards_mode != "local_capture":
            raise ValueError("transport_disabled")
        smtp = smtplib.SMTP(timeout=20)
        try:
            smtp.connect("mailpit", 1025)
        except (OSError, smtplib.SMTPException):
            smtp.close()
            return "FAILED", "connect_failed"
        try:
            smtp.send_message(msg)
        except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError):
            return "FAILED", "smtp_rejected"
        except (OSError, smtplib.SMTPException):
            return "UNKNOWN", "smtp_outcome_unknown"
        finally:
            smtp.close()
        return "CAPTURED_LOCAL", None
