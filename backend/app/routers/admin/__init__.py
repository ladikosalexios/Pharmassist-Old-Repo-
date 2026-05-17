"""Company admin portal — /admin/* endpoints (staff auth, onboarding, pharmacy views).

`main.py` includes `admin.router`; this package keeps that contract while
splitting the surface into focused sub-routers.
"""

from fastapi import APIRouter

from . import auth, invitations, pharmacies

router = APIRouter(prefix="/admin", tags=["admin"])

for _sub in (auth, invitations, pharmacies):
    router.include_router(_sub.router)
