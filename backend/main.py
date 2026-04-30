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
  PHARMAPI_API_KEY    static key from your ΗΔΥΚΑ registration email (per-app, shared across all pharmacists using your software)

Known Pharmapi error codes:
  G12  You must create first connection        → call /api/v1user/me
  G14  Connection time limit exceeded (24h)   → call /api/v1user/me again
  G15  No api key provided                    → add Api-Key header
  G11  Api key invalid                        → wrong key

Endpoints:
  POST /auth/login                 → pharmacist login, returns JWT
  GET  /auth/me                    → session info
  POST /pharmapi/connect           → call /api/v1user/me, establish 24h session
  GET  /pharmapi/status            → show session state (connected? when?)
  GET  /pharmapi/pharmacy          → GET /pharmacies/myPharmacy
  GET  /pharmapi/prescriptions/{b} → GET prescription by barcode
"""

import os
import hashlib
import hmac
import time
import json
import base64
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

# ── Config ──────────────────────────────────────────────────────────────────
SECRET_KEY       = os.getenv("SECRET_KEY", "pharmassist-dev-secret-CHANGE-IN-PROD")
TOKEN_EXPIRE_MIN = int(os.getenv("TOKEN_EXPIRE_MINUTES", "480"))  # 8h pharmacist session

PHARMAPI_BASE    = os.getenv("PHARMAPI_BASE", "https://testeps.e-prescription.gr/pharmapiv2")
PHARMAPI_USER    = os.getenv("PHARMAPI_USERNAME", "medcare1pharmapi")
PHARMAPI_PASS    = os.getenv("PHARMAPI_PASSWORD", "Aa900919081908!!")
PHARMAPI_API_KEY = os.getenv("PHARMAPI_API_KEY", "pi2jwygkd07yho3a4dw6jc55tg5ra3uc")

# ── In-memory 24h session tracker ───────────────────────────────────────────
# In production this goes in Redis/DB — here it's per-process
_pharmapi_session: dict = {
    "connected": False,
    "connected_at": None,    # ISO timestamp
    "connected_at_ts": 0.0,  # unix timestamp
    "user_data": None,       # response from /api/v1user/me
}

SESSION_WINDOW_SECONDS = 23 * 3600  # 23h (refresh before 24h hard limit)

def session_is_valid() -> bool:
    if not _pharmapi_session["connected"]:
        return False
    elapsed = time.time() - _pharmapi_session["connected_at_ts"]
    return elapsed < SESSION_WINDOW_SECONDS

# ── Minimal JWT (stdlib only — no python-jose needed) ───────────────────────
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * padding)

def create_jwt(payload: dict) -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = {**payload, "exp": int(time.time()) + TOKEN_EXPIRE_MIN * 60}
    body = _b64url(json.dumps(payload).encode())
    sig_input = f"{header}.{body}".encode()
    sig = hmac.new(SECRET_KEY.encode(), sig_input, hashlib.sha256).digest()
    return f"{header}.{body}.{_b64url(sig)}"

def decode_jwt(token: str) -> dict:
    try:
        header, body, sig = token.split(".")
        sig_input = f"{header}.{body}".encode()
        expected = _b64url(hmac.new(SECRET_KEY.encode(), sig_input, hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            raise ValueError("bad signature")
        payload = json.loads(_b64url_decode(body))
        if payload.get("exp", 0) < time.time():
            raise ValueError("token expired")
        return payload
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

# ── Demo user store (replace with DB in production) ─────────────────────────
# SHA-256 of password — run: python3 -c "import hashlib; print(hashlib.sha256(b'demo123').hexdigest())"
USERS = {
    "pharmacist@demo.gr": {
        "name": "Demo Pharmacist",
        "pharmacy": "MedCare Pharmacy",
        # SHA-256("demo123")
        "pw_hash": "d3ad9315b7be5dd53b31a273b3b3aba5defe700808305aa16a3062b76658a791",
    }
}

def verify_password(plain: str, hashed: str) -> bool:
    return hashlib.sha256(plain.encode()).hexdigest() == hashed

# ── Pharmapi HTTP helpers ────────────────────────────────────────────────────
def pharmapi_headers() -> dict:
    """Headers required on every Pharmapi call."""
    if not PHARMAPI_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="PHARMAPI_API_KEY not set. Add it to your environment — it was in your ΗΔΥΚΑ registration email."
        )
    return {
        "Accept": "application/json",
        "Api-Key": PHARMAPI_API_KEY,
    }

def _parse_pharmapi_error(r: httpx.Response) -> str:
    """Extract ΗΔΥΚΑ error code from response body."""
    try:
        data = r.json()
        return data.get("errorCode") or data.get("message") or r.text[:200]
    except Exception:
        return r.text[:200]

async def pharmapi_get(path: str, accept_xml: bool = False) -> dict:
    """Authenticated GET to Pharmapi. Raises HTTPException on failure."""
    url = f"{PHARMAPI_BASE}{path}"
    headers = pharmapi_headers()
    if accept_xml:
        headers["Accept"] = "application/xml"
    print(f"[Pharmapi] GET {url}")
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(
            url,
            auth=(PHARMAPI_USER, PHARMAPI_PASS),
            headers=headers,
        )
    print(f"[Pharmapi] {r.status_code} — {r.text[:500]}")

    if r.status_code == 200:
        # API returns XML for some endpoints, JSON for others
        content_type = r.headers.get("content-type", "")
        if "xml" in content_type:
            # Return raw XML as a dict with one key for now
            return {"raw_xml": r.text}
        try:
            return r.json()
        except Exception:
            return {"raw": r.text}

    # Full raw error for debugging
    try:
        err_body = r.json()
        err = str(err_body)
    except Exception:
        err_body = {}
        err = r.text

    if "G12" in err:
        raise HTTPException(502, "Pharmapi: no active connection — call POST /pharmapi/connect first")
    if "G14" in err or "914" in err or "Connection time limit" in err:
        raise HTTPException(502, "Pharmapi: 24h session expired — log into https://test.e-prescription.gr/epregen2/ first, then retry")
    if "G15" in err:
        raise HTTPException(500, "Pharmapi: Api-Key missing — set PHARMAPI_API_KEY env var")
    if "G11" in err:
        raise HTTPException(500, "Pharmapi: Api-Key invalid — check PHARMAPI_API_KEY value")
    if r.status_code == 401:
        raise HTTPException(502, f"Pharmapi: bad credentials — {err}")
    raise HTTPException(502, f"Pharmapi error {r.status_code}: {err}")

# ── FastAPI app ──────────────────────────────────────────────────────────────
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

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    payload = decode_jwt(token)
    user = USERS.get(payload.get("sub", ""))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return {"email": payload["sub"], **user}

# ── Schemas ──────────────────────────────────────────────────────────────────
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    pharmacist_name: str
    pharmacy: str

class PharmacistMe(BaseModel):
    email: str
    name: str
    pharmacy: str

class SessionStatus(BaseModel):
    pharmapi_connected: bool
    connected_at: Optional[str]
    session_age_minutes: Optional[float]
    session_valid_for_minutes: Optional[float]
    pharmapi_user: Optional[dict]

# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "pharmapi_session_valid": session_is_valid(),
        "pharmapi_api_key_set": bool(PHARMAPI_API_KEY),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/auth/login", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends()):
    """
    Step 1: Pharmacist logs into PharmAssist.
    Demo: pharmacist@demo.gr / demo123
    Returns JWT for all subsequent calls.
    """
    user = USERS.get(form.username)
    if not user or not verify_password(form.password, user["pw_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_jwt({"sub": form.username})
    return TokenResponse(
        access_token=token,
        pharmacist_name=user["name"],
        pharmacy=user["pharmacy"],
    )


@app.get("/auth/me", response_model=PharmacistMe)
async def me(current: dict = Depends(get_current_user)):
    return PharmacistMe(email=current["email"], name=current["name"], pharmacy=current["pharmacy"])


@app.post("/pharmapi/connect")
async def pharmapi_connect(current: dict = Depends(get_current_user)):
    """
    Step 2: Establish (or refresh) the 24h Pharmapi session.

    Calls GET /api/v1user/me on Pharmapi with Basic Auth + Api-Key.
    Per ΗΔΥΚΑ docs: every pharmacist must call this at least once before
    using any other API endpoint. Must be refreshed within 24h.

    Error G12 = never connected → call this.
    Error G14 = 24h expired    → call this again.
    """
    # Correct path per docs: /api/v1/user/me (returns XML)
    data = await pharmapi_get("/api/v1/user/me", accept_xml=True)

    now = time.time()
    _pharmapi_session.update({
        "connected": True,
        "connected_at": datetime.now(timezone.utc).isoformat(),
        "connected_at_ts": now,
        "user_data": data,
    })

    return {
        "success": True,
        "message": "Pharmapi session established. Valid for 24h.",
        "session_valid_until": datetime.fromtimestamp(
            now + SESSION_WINDOW_SECONDS, tz=timezone.utc
        ).isoformat(),
        "pharmapi_user": data,
    }


@app.get("/pharmapi/status", response_model=SessionStatus)
async def pharmapi_status(current: dict = Depends(get_current_user)):
    """Show current Pharmapi session state."""
    if not _pharmapi_session["connected"]:
        return SessionStatus(
            pharmapi_connected=False,
            connected_at=None,
            session_age_minutes=None,
            session_valid_for_minutes=None,
            pharmapi_user=None,
        )

    elapsed = time.time() - _pharmapi_session["connected_at_ts"]
    remaining = max(0.0, SESSION_WINDOW_SECONDS - elapsed)

    return SessionStatus(
        pharmapi_connected=session_is_valid(),
        connected_at=_pharmapi_session["connected_at"],
        session_age_minutes=round(elapsed / 60, 1),
        session_valid_for_minutes=round(remaining / 60, 1),
        pharmapi_user=_pharmapi_session["user_data"],
    )


@app.get("/pharmapi/pharmacy")
async def get_my_pharmacy(current: dict = Depends(get_current_user)):
    """
    Fetch pharmacy details from Pharmapi.
    Requires active Pharmapi session (call /pharmapi/connect first).
    """
    return await pharmapi_get("/pharmacies/myPharmacy")


@app.get("/pharmapi/prescriptions/{barcode}")
async def get_prescription(barcode: str, current: dict = Depends(get_current_user)):
    """
    Load a prescription by barcode from Pharmapi.
    Requires active Pharmapi session.
    """
    return await pharmapi_get(f"/prescriptions/{barcode}")


# ── Prescription Verification (mock data for the new React UI) ──────────────
# These endpoints serve mock data so the verification page works end-to-end
# without depending on the live Pharmapi sandbox.

_MOCK_SAFETY_CHECKS: dict = {
    "RX2024-005": [
        {
            "id": "duplicate-therapy",
            "name": "Duplicate Therapy Check",
            "status": "ok",
            "message": "No duplicate therapy detected.",
            "details": "Patient is not currently on any other anticoagulant. Reviewed active prescriptions in the last 90 days.",
            "recommendedAction": None,
        },
        {
            "id": "interactions",
            "name": "Drug-Drug Interactions",
            "status": "review",
            "message": "Patient is on Aspirin 100 mg — review bleeding risk.",
            "details": (
                "Concurrent Warfarin + Aspirin significantly increases bleeding risk "
                "(major GI and intracranial bleeding rates roughly 2–3× background). "
                "Combination is acceptable when indicated (e.g. mechanical valve, recent ACS) "
                "but requires close INR monitoring and a documented clinical justification."
            ),
            "recommendedAction": (
                "Confirm clinical indication with the prescriber. If continued, schedule INR "
                "every 3–5 days for the first 2 weeks and counsel patient on bleeding signs."
            ),
        },
        {
            "id": "contraindications",
            "name": "Contraindications",
            "status": "ok",
            "message": "No contraindications identified.",
            "details": "Patient has no active bleeding, no recent surgery, no severe hepatic impairment, and is not pregnant.",
            "recommendedAction": None,
        },
        {
            "id": "dose-validation",
            "name": "Dose Validation",
            "status": "ok",
            "message": "Dose within SPC recommended range.",
            "details": "5 mg once daily falls within the SPC maintenance range of 2–10 mg daily.",
            "recommendedAction": None,
        },
        {
            "id": "spc-alignment",
            "name": "SPC Alignment",
            "status": "review",
            "message": "Confirm INR monitoring schedule is in place.",
            "details": (
                "SPC v2024.3 mandates INR monitoring at initiation, every 3–5 days during "
                "induction, and at least every 4 weeks during maintenance. No INR appointments "
                "are recorded for this patient in the last 30 days."
            ),
            "recommendedAction": "Book the next INR test before dispensing and add a recurring monthly INR reminder.",
        },
    ],
    "RX2024-001": [
        {
            "id": "duplicate-therapy",
            "name": "Duplicate Therapy Check",
            "status": "ok",
            "message": "No duplicate therapy detected.",
            "details": "No other beta-lactam antibiotic active in the patient's record.",
            "recommendedAction": None,
        },
        {
            "id": "interactions",
            "name": "Drug-Drug Interactions",
            "status": "ok",
            "message": "No major interactions detected.",
            "details": "No methotrexate, allopurinol, or other significant interactions on file.",
            "recommendedAction": None,
        },
        {
            "id": "contraindications",
            "name": "Contraindications",
            "status": "ok",
            "message": "No contraindications identified.",
            "details": "Patient has no documented penicillin or beta-lactam hypersensitivity.",
            "recommendedAction": None,
        },
        {
            "id": "dose-validation",
            "name": "Dose Validation",
            "status": "ok",
            "message": "Dose within SPC recommended range.",
            "details": "500 mg every 8 hours is within the adult SPC range (250–500 mg q8h).",
            "recommendedAction": None,
        },
        {
            "id": "spc-alignment",
            "name": "SPC Alignment",
            "status": "ok",
            "message": "Aligned with current SPC.",
            "details": "Indication, dose, route, and duration match SPC v2024.3.",
            "recommendedAction": None,
        },
    ],
}


_MOCK_PRESCRIPTIONS: dict = {
    "RX2024-005": {
        "rxId": "RX2024-005",
        "code": "RX2024-005",
        "dateIssued": "2026-04-28",
        "status": "PENDING",
        "spcVersion": "SPC v2024.3",
        "patient": {
            "id": "P001",
            "name": "Maria Stavrou",
            "age": 64,
            "dateOfBirth": "1962-03-15",
            "amka": "15031962456",
            "conditions": ["Type II Diabetes", "Hypertension", "Hyperlipidemia"],
            "allergies": "Penicillin (anaphylaxis), sulfa drugs",
        },
        "medication": {
            "drugName": "Warfarin",
            "dose": "5 mg",
            "form": "Tablet",
            "route": "Oral",
            "frequency": "Once daily",
            "treatmentDuration": "90 days",
            "spcRecommendedDosage": (
                "Initial: 5–10 mg daily for 1–2 days, then adjusted based on INR. "
                "Maintenance: 2–10 mg daily. Target INR 2.0–3.0 for most indications."
            ),
        },
        "prescriber": {
            "name": "Dr. Michael Chen",
            "licenceId": "MD-48291",
            "specialty": "Cardiology",
            "contact": "+30 210 123 4567",
            "email": "m.chen@hospital.gr",
        },
        "spcQuickReference": {
            "contraindications": [
                "Active bleeding or bleeding diathesis",
                "Recent or planned surgery (CNS, eye, traumatic)",
                "Severe hepatic impairment",
                "Pregnancy (except for mechanical heart valves)",
            ],
            "majorInteractions": [
                {"drug": "Aspirin", "effect": "High risk of bleeding when combined with anticoagulants."},
                {"drug": "NSAIDs", "effect": "Increased bleeding risk; avoid concurrent use."},
                {"drug": "Amiodarone", "effect": "Potentiates warfarin effect; reduce warfarin dose by 30–50%."},
            ],
        },
        "safetyChecks": _MOCK_SAFETY_CHECKS["RX2024-005"],
    },
    "RX2024-001": {
        "rxId": "RX2024-001",
        "code": "RX2024-001",
        "dateIssued": "2026-03-11",
        "status": "PENDING",
        "spcVersion": "SPC v2024.3",
        "patient": {
            "id": "P010",
            "name": "Sarah Johnson",
            "age": 32,
            "dateOfBirth": "1993-07-22",
            "amka": "22071993789",
            "conditions": ["Bacterial sinusitis"],
            "allergies": "None known",
        },
        "medication": {
            "drugName": "Amoxicillin",
            "dose": "500 mg",
            "form": "Capsule",
            "route": "Oral",
            "frequency": "Three times daily",
            "treatmentDuration": "7 days",
            "spcRecommendedDosage": "Adults: 250–500 mg every 8 hours, depending on severity.",
        },
        "prescriber": {
            "name": "Dr. Michael Chen",
            "licenceId": "MD-48291",
            "specialty": "General Practice",
            "contact": "+30 210 123 4567",
            "email": "m.chen@hospital.gr",
        },
        "spcQuickReference": {
            "contraindications": [
                "Hypersensitivity to penicillins or any beta-lactam antibiotic",
                "History of severe immediate hypersensitivity reaction",
            ],
            "majorInteractions": [
                {"drug": "Methotrexate", "effect": "Reduced excretion; increased toxicity risk."},
                {"drug": "Allopurinol",  "effect": "Increased risk of skin rash."},
            ],
        },
        "safetyChecks": _MOCK_SAFETY_CHECKS["RX2024-001"],
    },
}


@app.get("/safety-checks/{rx_id}")
async def get_safety_checks(rx_id: str, current: dict = Depends(get_current_user)):
    """Return the automated safety checks for a prescription."""
    checks = _MOCK_SAFETY_CHECKS.get(rx_id)
    if checks is None:
        raise HTTPException(status_code=404, detail=f"Prescription {rx_id} not found")
    return {"rxId": rx_id, "checks": checks}


_MOCK_ACTIVE_ALERTS = [
    {
        "id": "AL-1001",
        "type": "INTERACTION",
        "description": "Warfarin + Aspirin: high risk of bleeding. Immediate review required before dispensing.",
        "rxId": "RX2024-005",
        "createdAt": "2026-04-30T08:14:00Z",
    },
    {
        "id": "AL-1002",
        "type": "G6PD",
        "description": "Patient P003 has G6PD deficiency. Verify medication safety against current SPC.",
        "rxId": "RX2024-002",
        "createdAt": "2026-04-30T07:42:00Z",
    },
    {
        "id": "AL-1003",
        "type": "PREGNANCY",
        "description": "Patient P001 is 18 weeks pregnant. Check teratogenicity classification before approval.",
        "rxId": "RX2024-003",
        "createdAt": "2026-04-30T06:20:00Z",
    },
    {
        "id": "AL-1004",
        "type": "CONTRAINDICATION",
        "description": "Metformin contraindicated — patient eGFR < 30 ml/min recorded last week.",
        "rxId": None,
        "createdAt": "2026-04-29T18:05:00Z",
    },
]


@app.get("/alerts/active")
async def get_active_alerts(current: dict = Depends(get_current_user)):
    """Return active safety alerts for the dashboard."""
    return {"alerts": _MOCK_ACTIVE_ALERTS}


@app.get("/prescriptions/{rx_id}")
async def get_prescription_for_verification(rx_id: str, current: dict = Depends(get_current_user)):
    """Return prescription data (patient, medication, prescriber, safety checks) for the verification UI."""
    rx = _MOCK_PRESCRIPTIONS.get(rx_id)
    if not rx:
        raise HTTPException(status_code=404, detail=f"Prescription {rx_id} not found")
    return rx


class PrescriptionPatch(BaseModel):
    status: Optional[str] = None
    discrepancy_type: Optional[str] = None
    notes: Optional[str] = None
    notify_physician: Optional[bool] = None


class PhysicianNotification(BaseModel):
    rxId: str
    message: str


@app.post("/prescriptions/{rx_id}/approve")
async def approve_prescription(rx_id: str, current: dict = Depends(get_current_user)):
    rx = _MOCK_PRESCRIPTIONS.get(rx_id)
    if not rx:
        raise HTTPException(status_code=404, detail=f"Prescription {rx_id} not found")
    rx["status"] = "APPROVED"
    return {"success": True, "rxId": rx_id, "status": rx["status"]}


@app.patch("/prescriptions/{rx_id}")
async def patch_prescription(
    rx_id: str,
    patch: PrescriptionPatch,
    current: dict = Depends(get_current_user),
):
    """Partial update for a prescription — used by the Flag Discrepancy modal."""
    rx = _MOCK_PRESCRIPTIONS.get(rx_id)
    if not rx:
        raise HTTPException(status_code=404, detail=f"Prescription {rx_id} not found")
    if patch.status is not None:
        rx["status"] = patch.status.upper()
    if patch.discrepancy_type is not None:
        rx["discrepancyType"] = patch.discrepancy_type
    if patch.notes is not None:
        rx["flagNotes"] = patch.notes
    if patch.notify_physician is not None:
        rx["notifyPhysician"] = bool(patch.notify_physician)
    return {
        "success": True,
        "rxId": rx_id,
        "status": rx["status"],
        "discrepancyType": rx.get("discrepancyType"),
        "notes": rx.get("flagNotes"),
        "notifyPhysician": rx.get("notifyPhysician"),
    }


# In-memory log of physician notifications (would be email/SMS/queue in prod)
_PHYSICIAN_NOTIFICATIONS: list = []


@app.post("/notifications/physician")
async def notify_physician(
    payload: PhysicianNotification,
    current: dict = Depends(get_current_user),
):
    entry = {
        "rxId": payload.rxId,
        "message": payload.message,
        "sentAt": datetime.now(timezone.utc).isoformat(),
        "by": current["email"],
    }
    _PHYSICIAN_NOTIFICATIONS.append(entry)
    print(f"[Notification] Physician for {payload.rxId}: {payload.message}")
    return {"success": True, "delivered": True, **entry}
