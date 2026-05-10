"""Health probe — public, no auth required."""

from datetime import UTC, datetime

from fastapi import APIRouter

from ..services.pharmapi import PHARMAPI_API_KEY, session_is_valid

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "pharmapi_session_valid": session_is_valid(),
        "pharmapi_api_key_set": bool(PHARMAPI_API_KEY),
        "timestamp": datetime.now(UTC).isoformat(),
    }
