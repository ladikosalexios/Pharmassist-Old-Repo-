"""
PharmAssist POC — FastAPI Backend
----------------------------------
Auth flow (per ΗΔΥΚΑ docs):
  1. Pharmacist logs into PharmAssist  → gets our JWT
  2. Our backend calls Pharmapi GET /api/v1user/me (Basic Auth + Api-Key header)
       → "creates active connection" in ΗΔΥΚΑ, valid for 24h
  3. All other Pharmapi calls work for 24h using same Basic Auth + Api-Key
  4. After 24h, must call /api/v1user/me again to refresh

Required env vars:
  PHARMAPI_USERNAME   e.g. medcare1pharmapi
  PHARMAPI_PASSWORD   e.g. Aa900919081908!!
  PHARMAPI_API_KEY    static key from your ΗΔΥΚΑ registration email
                      (per-app, shared across all pharmacists using your software)

Known Pharmapi error codes:
  G12  You must create first connection        → call /api/v1user/me
  G14  Connection time limit exceeded (24h)   → call /api/v1user/me again
  G15  No api key provided                    → add Api-Key header
  G11  Api key invalid                        → wrong key

Project layout:
  app/schemas/   — Pydantic API contracts
  app/services/  — in-memory stores + business helpers (mock data, JWT,
                   Pharmapi client, PDF rendering, etc.)
  app/deps.py    — shared FastAPI dependencies (get_current_user, oauth2_scheme)
  app/routers/   — one APIRouter per domain
  main.py        — FastAPI app + middleware + router registration (this file)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .app.routers import (
    alerts,
    auth,
    documentation,
    health,
    instructions,
    messages,
    notifications,
    patients,
    pharmapi,
    prescriptions,
    safety_checks,
    side_effects,
    spc,
)


app = FastAPI(
    title="PharmAssist POC",
    description="FastAPI backend bridging pharmacist login → Pharmapi (ΗΔΥΚΑ)",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Order doesn't affect routing (each router has its own prefix), but the
# include order is what /docs and /openapi.json render in. Group public →
# auth → core domains.
for module in (
    health,
    auth,
    pharmapi,
    prescriptions,
    safety_checks,
    spc,
    alerts,
    messages,
    documentation,
    instructions,
    side_effects,
    patients,
    notifications,
):
    app.include_router(module.router)
