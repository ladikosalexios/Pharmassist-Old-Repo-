"""Active safety alerts for the dashboard."""

from fastapi import APIRouter, Depends

from ..deps import get_current_user
from ..services.alerts import MOCK_ACTIVE_ALERTS

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/active")
async def get_active_alerts(current: dict = Depends(get_current_user)):
    """Return active safety alerts for the dashboard."""
    return {"alerts": MOCK_ACTIVE_ALERTS}
