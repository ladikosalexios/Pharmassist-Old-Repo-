# One row per ingested SPC (ΠΧΠ) / patient-leaflet (ΦΟΧ) document. The parsed
# JSONB feeds the review page's SPC extras and the instruction sheets; the full
# sections map is the future RAG chunk source. raw_pdf is stored for EVERY
# source — ΕΟΦ document URLs are JSF-session-bound and expire, so the "verify
# against source" link must be able to serve our own copy, and keeping the
# bytes lets us re-parse when the splitter improves without re-hitting a
# brittle source (size-capped at settings.spc_max_pdf_bytes on ingest).
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, LargeBinary, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class SpcDocument(Base, TimestampMixin):
    __tablename__ = "spc_documents"
    __table_args__ = (
        Index("ix_spc_documents_barcode", "barcode"),
        Index("ix_spc_documents_atc_code", "atc_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    # ΕΟΦ barcode (drug_catalog.gns_code). Nullable: EMA/ATC-level documents
    # aren't tied to one national pack presentation.
    barcode: Mapped[str | None] = mapped_column(String)
    atc_code: Mapped[str] = mapped_column(String, nullable=False)
    doc_type: Mapped[str] = mapped_column(String(10), nullable=False)  # spc | pil | combined
    source: Mapped[str] = mapped_column(String(10), nullable=False)  # eof | ema | upload
    source_url: Mapped[str | None] = mapped_column(Text)
    # No DB unique — the same PDF legitimately serves several barcodes; dedupe
    # is code-level per (barcode, doc_type, sha256) at ingest.
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    language: Mapped[str] = mapped_column(String(2), nullable=False, server_default=text("'el'"))
    raw_pdf: Mapped[bytes | None] = mapped_column(LargeBinary)
    full_text: Mapped[str | None] = mapped_column(Text)
    # Complete {section_id: text} map from the deterministic splitter — every
    # numbered section, not only the ones mapped into `parsed`.
    sections: Mapped[dict | None] = mapped_column(JSONB)
    # SpcDetails-shaped payload served by resolve_spc.
    parsed: Mapped[dict | None] = mapped_column(JSONB)
    extraction_method: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'deterministic'")
    )  # deterministic | llm
    parse_status: Mapped[str] = mapped_column(String(10), nullable=False)  # parsed|partial|failed
    # Pharmacist review upgrade — auto-extracted content is served immediately
    # but labeled; verification only changes the label, never gates serving.
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    verified_by: Mapped[str | None] = mapped_column(String)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
