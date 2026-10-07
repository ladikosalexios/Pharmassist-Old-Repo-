"""Run with python -m scripts.yellow_worker. Claims committed before SMTP; never blind retries."""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.config import get_settings
from app.db.models.yellow_card import YellowEvent, YellowPreview, YellowSubmission
from app.db.session import AsyncSessionLocal
from app.services.yellow_mail import LocalCaptureTransport, compose_message


async def once():
    async with AsyncSessionLocal() as db:
        # A crashed sender might have delivered. Quarantine stale claims, don't requeue.
        stale = (
            await db.scalars(
                select(YellowSubmission)
                .where(
                    YellowSubmission.status == "SENDING",
                    YellowSubmission.attempted_at < datetime.now(UTC) - timedelta(minutes=5),
                )
                .with_for_update(skip_locked=True)
            )
        ).all()
        for row in stale:
            row.status = "UNKNOWN"
            row.failure_code = "worker_interrupted"
            db.add(YellowEvent(submission_id=row.id, kind="UNKNOWN"))
        row = await db.scalar(
            select(YellowSubmission)
            .where(YellowSubmission.status == "QUEUED")
            .order_by(YellowSubmission.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if row is None:
            await db.commit()
            return False
        row.status = "SENDING"
        row.attempted_at = datetime.now(UTC)
        ident = row.id
        db.add(YellowEvent(submission_id=ident, kind="SENDING"))
        await db.commit()
        preview = await db.get(YellowPreview, row.preview_id)
        try:
            msg = compose_message(row, preview)
        except Exception:
            result, code = "FAILED", "artifact_invalid"
        else:
            await db.rollback()
            try:
                result, code = await asyncio.to_thread(LocalCaptureTransport().send, msg)
            except Exception:
                result, code = "UNKNOWN", "transport_interrupted"
        # Do not hold a DB transaction while sending over the network.
        await db.rollback()
        row = await db.scalar(
            select(YellowSubmission).where(YellowSubmission.id == ident).with_for_update()
        )
        if row.status == "SENDING":
            row.status = result
            row.failure_code = code
            db.add(YellowEvent(submission_id=ident, kind=result))
            await db.commit()
        return True


async def main():
    if get_settings().yellow_cards_mode != "local_capture":
        raise RuntimeError("Local capture mode required")
    while True:
        await once()
        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
