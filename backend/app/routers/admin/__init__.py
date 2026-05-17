"""Company admin portal — /admin/* endpoints (staff auth + management).

`main.py` includes `admin.router`; this package keeps that contract while
splitting the surface into focused sub-routers.
"""

from fastapi import APIRouter

from . import audit, auth, demo, invitations, pharmacies, pharmacists, reference, staff

router = APIRouter(prefix="/admin", tags=["admin"])

for _sub in (auth, invitations, pharmacies, pharmacists, staff, reference, demo, audit):
    router.include_router(_sub.router)
