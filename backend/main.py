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
import csv
import io
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Depends, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
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
            "atcCode": "B01AA03",
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
            "atcCode": "J01CA04",
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


# ── Summary of Product Characteristics (mock) ───────────────────────────────
_MOCK_SPC: dict = {
    "B01AA03": {
        "atcCode": "B01AA03",
        "drugName": "Warfarin",
        "version": "v2.9",
        # NB: this date is *after* RX2024-005's issue date (2026-04-28) so the
        # version badge in the UI flips to red and the "review recommended"
        # tooltip fires for that prescription. Adjust if you need a clean run.
        "updatedAt": "2026-04-29T00:00:00Z",
        "fullSpcUrl": "https://www.eof.gr/spc/warfarin",
        "recommendedDosage": (
            "Initial: 5–10 mg daily for 1–2 days, then adjusted based on INR. "
            "Maintenance: 2–10 mg daily. Target INR 2.0–3.0 for most indications. "
            "Elderly and patients with hepatic impairment may require lower starting doses."
        ),
        "fullSpcText": (
            "1. THERAPEUTIC INDICATIONS\n"
            "Warfarin is indicated for the prophylaxis and treatment of venous thromboembolism, "
            "prevention of stroke in non-valvular atrial fibrillation, and as adjunctive therapy "
            "after mechanical heart valve replacement.\n\n"
            "2. POSOLOGY AND METHOD OF ADMINISTRATION\n"
            "Initial dose 5–10 mg once daily for 1–2 days. Maintenance is individualised based "
            "on INR (typical 2–10 mg daily). Take at the same time each day.\n\n"
            "3. CONTRAINDICATIONS\n"
            "See Key Contraindications section.\n\n"
            "4. SPECIAL WARNINGS AND PRECAUTIONS\n"
            "Bleeding risk increases with age, concurrent antiplatelet therapy, recent surgery, "
            "and uncontrolled hypertension. Counsel patients on signs of bleeding.\n\n"
            "5. INTERACTION WITH OTHER MEDICINAL PRODUCTS\n"
            "See Major Interactions section. Many CYP2C9 inhibitors and inducers can shift INR."
        ),
        "contraindications": [
            "Active bleeding or bleeding diathesis",
            "Recent or planned surgery (CNS, eye, traumatic)",
            "Severe hepatic impairment",
            "Pregnancy (except for mechanical heart valves)",
            "Hypersensitivity to warfarin or any excipient",
        ],
        "majorInteractions": [
            {"drug": "Aspirin",     "effect": "Concurrent use significantly increases bleeding risk; use only with documented indication and close INR monitoring."},
            {"drug": "NSAIDs",      "effect": "Increased bleeding risk via platelet inhibition and gastric mucosal damage; avoid concurrent use."},
            {"drug": "Amiodarone",  "effect": "Potentiates warfarin effect via CYP2C9 inhibition; reduce warfarin dose by 30–50% and recheck INR within 5 days."},
            {"drug": "Fluconazole", "effect": "Marked CYP2C9 inhibition; INR can rise sharply within 3–5 days."},
        ],
    },
    "J01CA04": {
        "atcCode": "J01CA04",
        "drugName": "Amoxicillin",
        "version": "v1.4",
        "updatedAt": "2026-01-10T00:00:00Z",
        "fullSpcUrl": "https://www.eof.gr/spc/amoxicillin",
        "recommendedDosage": (
            "Adults: 250–500 mg every 8 hours, depending on severity. "
            "Children >40 kg: as adults. Children ≤40 kg: 20–40 mg/kg/day in three divided doses."
        ),
        "fullSpcText": (
            "1. THERAPEUTIC INDICATIONS\n"
            "Amoxicillin is indicated for bacterial infections including ENT, lower respiratory "
            "tract, urinary tract, skin and soft tissue, and dental infections, where the "
            "causative organism is known or suspected to be susceptible.\n\n"
            "2. POSOLOGY AND METHOD OF ADMINISTRATION\n"
            "Adults: 250–500 mg every 8 hours; severe infections may require higher doses. "
            "Renal impairment: dose interval should be extended.\n\n"
            "3. CONTRAINDICATIONS\n"
            "See Key Contraindications section.\n\n"
            "4. INTERACTIONS\n"
            "See Major Interactions section."
        ),
        "contraindications": [
            "Hypersensitivity to penicillins or any beta-lactam antibiotic",
            "History of severe immediate hypersensitivity reaction (anaphylaxis, Stevens-Johnson syndrome)",
        ],
        "majorInteractions": [
            {"drug": "Methotrexate", "effect": "Reduced renal excretion of methotrexate; increased toxicity risk — monitor closely."},
            {"drug": "Allopurinol",  "effect": "Increased risk of skin rash when used concurrently."},
            {"drug": "Warfarin",     "effect": "May potentiate anticoagulant effect; monitor INR during and after a course."},
        ],
    },
}


@app.get("/spc/{atc_code}")
async def get_spc(atc_code: str, current: dict = Depends(get_current_user)):
    """Return the Summary of Product Characteristics for a given ATC code."""
    spc = _MOCK_SPC.get(atc_code)
    if spc is None:
        raise HTTPException(status_code=404, detail=f"SPC not found for ATC {atc_code}")
    return spc


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


# ── Pharmacist ↔ Prescriber messaging (mock thread per prescription) ────────
_MOCK_MESSAGES: dict = {
    "RX2024-005": [
        {
            "id": "m-005-1",
            "rxId": "RX2024-005",
            "from": "pharmacist",
            "fromName": "Demo Pharmacist",
            "body": "Patient is currently on Aspirin 100 mg. Could you confirm the bleeding-risk plan and the INR monitoring schedule before I dispense?",
            "sentAt": "2026-04-29T14:30:00Z",
        },
        {
            "id": "m-005-2",
            "rxId": "RX2024-005",
            "from": "prescriber",
            "fromName": "Dr. Michael Chen",
            "body": "Yes — patient has a recent stent (12/2025). Please continue but stress INR every 3–5 days for the first two weeks. I've already booked the follow-up labs for next Monday.",
            "sentAt": "2026-04-29T16:12:00Z",
        },
    ],
}


class MessagePayload(BaseModel):
    to: str
    rxId: str
    body: str


@app.get("/messages")
async def list_messages(rxId: str, current: dict = Depends(get_current_user)):
    """Return the message thread between this pharmacist and the prescriber for a given rxId."""
    return {"items": _MOCK_MESSAGES.get(rxId, [])}


@app.post("/messages")
async def post_message(payload: MessagePayload, current: dict = Depends(get_current_user)):
    if not payload.body.strip():
        raise HTTPException(status_code=400, detail="Message body cannot be empty.")
    msg = {
        "id": f"m-{int(time.time() * 1000)}",
        "rxId": payload.rxId,
        "to": payload.to,
        "from": "pharmacist",
        "fromName": current["name"],
        "body": payload.body.strip(),
        "sentAt": datetime.now(timezone.utc).isoformat(),
    }
    _MOCK_MESSAGES.setdefault(payload.rxId, []).append(msg)
    return msg


# ── Documentation & Legal Log (mock) ────────────────────────────────────────
_MOCK_DOCUMENTATION: list = [
    {
        "id": "DOC-2026-0007",
        "rxId": "RX2024-005",
        "patientName": "Maria Stavrou",
        "drugName": "Warfarin 5 mg",
        "setting": "Private",
        "deliveryMethod": "BOTH",
        "language": "Greek",
        "informationProvided": (
            "Reviewed bleeding precautions, INR monitoring schedule, dietary "
            "considerations (vitamin K), and signs of over-anticoagulation. Patient "
            "received printed leaflet and digital copy via the patient portal."
        ),
        "pharmacistName": "Demo Pharmacist",
        "pharmacistLicense": "PH-12345",
        "signatureConfirmed": True,
        "dispensedAt": "2026-04-29T10:30:00+00:00",
    },
    {
        "id": "DOC-2026-0006",
        "rxId": "RX2024-001",
        "patientName": "Sarah Johnson",
        "drugName": "Amoxicillin 500 mg",
        "setting": "Private",
        "deliveryMethod": "PRINT",
        "language": "English",
        "informationProvided": (
            "Counselled on full course completion, symptom-watch for hypersensitivity, "
            "and gastrointestinal side effects. Provided printed leaflet."
        ),
        "pharmacistName": "Demo Pharmacist",
        "pharmacistLicense": "PH-12345",
        "signatureConfirmed": True,
        "dispensedAt": "2026-04-15T16:02:00+00:00",
    },
    {
        "id": "DOC-2026-0005",
        "rxId": "RX2024-002",
        "patientName": "James Martinez",
        "drugName": "Warfarin 7.5 mg",
        "setting": "Hospital",
        "deliveryMethod": "DIGITAL",
        "language": "English",
        "informationProvided": (
            "Reviewed inpatient protocol with the ward pharmacist and the patient. "
            "Digital counselling pack pushed to the patient's hospital portal."
        ),
        "pharmacistName": "Demo Pharmacist",
        "pharmacistLicense": "PH-12345",
        "signatureConfirmed": True,
        "dispensedAt": "2026-04-12T09:18:00+00:00",
    },
    {
        "id": "DOC-2026-0004",
        "rxId": "RX2024-003",
        "patientName": "Maria Garcia",
        "drugName": "Lisinopril 10 mg",
        "setting": "Private",
        "deliveryMethod": "PRINT",
        "language": "Greek",
        "informationProvided": (
            "Discussed renal function monitoring, dry-cough as a possible side effect, "
            "and the need to avoid concurrent NSAIDs. Printed leaflet handed over."
        ),
        "pharmacistName": "Demo Pharmacist",
        "pharmacistLicense": "PH-12345",
        "signatureConfirmed": True,
        "dispensedAt": "2026-03-22T11:44:00+00:00",
    },
    {
        "id": "DOC-2026-0003",
        "rxId": "RX2023-118",
        "patientName": "Eleni Nikolaou",
        "drugName": "Atorvastatin 20 mg",
        "setting": "Private",
        "deliveryMethod": "BOTH",
        "language": "Greek",
        "informationProvided": (
            "Reviewed muscle pain warnings and lipid panel follow-up timing. Both "
            "printed leaflet and digital copy delivered."
        ),
        "pharmacistName": "Demo Pharmacist",
        "pharmacistLicense": "PH-12345",
        "signatureConfirmed": True,
        "dispensedAt": "2026-03-10T15:05:00+00:00",
    },
    {
        "id": "DOC-2026-0002",
        "rxId": "RX2023-091",
        "patientName": "Dimitrios Konstantinou",
        "drugName": "Metformin 1000 mg",
        "setting": "Hospital",
        "deliveryMethod": "DIGITAL",
        "language": "Greek",
        "informationProvided": (
            "Discussed lactic-acidosis red-flag symptoms and renal function checks. "
            "Digital counselling sent to the inpatient app."
        ),
        "pharmacistName": "Demo Pharmacist",
        "pharmacistLicense": "PH-12345",
        "signatureConfirmed": True,
        "dispensedAt": "2026-02-27T08:51:00+00:00",
    },
]


def _doc_stats() -> dict:
    s = {"total": len(_MOCK_DOCUMENTATION), "print": 0, "digital": 0, "both": 0}
    for d in _MOCK_DOCUMENTATION:
        m = d["deliveryMethod"]
        if m == "PRINT":
            s["print"] += 1
        elif m == "DIGITAL":
            s["digital"] += 1
        elif m == "BOTH":
            s["both"] += 1
    return s


def _filter_docs(query: Optional[str], method: Optional[str]) -> list:
    items = list(_MOCK_DOCUMENTATION)
    if query:
        q = query.lower().strip()
        items = [
            d for d in items
            if q in d["patientName"].lower() or q in d["rxId"].lower() or q in d["drugName"].lower()
        ]
    if method and method.upper() != "ALL":
        items = [d for d in items if d["deliveryMethod"] == method.upper()]
    items.sort(key=lambda d: d["dispensedAt"], reverse=True)
    return items


def _csv_response(rows: list, filename: str) -> StreamingResponse:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([
        "ID", "Dispensed At", "Rx Code", "Patient", "Drug", "Setting",
        "Delivery Method", "Language", "Information Provided",
        "Pharmacist", "Licence", "Signature Confirmed",
    ])
    for d in rows:
        writer.writerow([
            d["id"], d["dispensedAt"], d["rxId"], d["patientName"], d["drugName"],
            d["setting"], d["deliveryMethod"], d["language"], d["informationProvided"],
            d["pharmacistName"], d["pharmacistLicense"],
            "yes" if d["signatureConfirmed"] else "no",
        ])
    out.seek(0)
    return StreamingResponse(
        iter([out.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# Order matters: fixed paths must be declared *before* the catch-all {id} path.
@app.get("/documentation/export")
async def export_documentation(
    q: Optional[str] = Query(None, description="Free-text search across patient, rxId, drug."),
    method: Optional[str] = Query(None, description="PRINT | DIGITAL | BOTH | ALL"),
    current: dict = Depends(get_current_user),
):
    rows = _filter_docs(q, method)
    return _csv_response(rows, "documentation_log.csv")


@app.get("/documentation/{doc_id}/export")
async def export_documentation_record(doc_id: str, current: dict = Depends(get_current_user)):
    rec = next((d for d in _MOCK_DOCUMENTATION if d["id"] == doc_id), None)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Documentation record {doc_id} not found")
    return _csv_response([rec], f"{doc_id}.csv")


@app.get("/documentation")
async def list_documentation(
    q: Optional[str] = Query(None, description="Free-text search across patient, rxId, drug."),
    method: Optional[str] = Query(None, description="PRINT | DIGITAL | BOTH | ALL"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current: dict = Depends(get_current_user),
):
    items = _filter_docs(q, method)
    total = len(items)
    page = items[offset : offset + limit]
    return {"items": page, "total": total, "stats": _doc_stats()}


@app.get("/documentation/{doc_id}")
async def get_documentation_record(doc_id: str, current: dict = Depends(get_current_user)):
    rec = next((d for d in _MOCK_DOCUMENTATION if d["id"] == doc_id), None)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Documentation record {doc_id} not found")
    return rec


class DocumentationCreate(BaseModel):
    rxId: str
    instructions: str
    language: str
    method: str
    setting: Optional[str] = "Private"


@app.post("/documentation", status_code=201)
async def create_documentation_record(
    payload: DocumentationCreate,
    current: dict = Depends(get_current_user),
):
    """Create a new documentation log entry, e.g. when patient instructions are saved."""
    rx = _MOCK_PRESCRIPTIONS.get(payload.rxId)
    if rx is None:
        raise HTTPException(status_code=404, detail=f"Prescription {payload.rxId} not found")
    new_id = f"DOC-{int(time.time() * 1000)}"
    record = {
        "id": new_id,
        "rxId": payload.rxId,
        "patientName": rx["patient"]["name"],
        "drugName": f'{rx["medication"]["drugName"]} {rx["medication"]["dose"]}',
        "setting": payload.setting or "Private",
        "deliveryMethod": payload.method.upper(),
        "language": payload.language,
        "informationProvided": payload.instructions,
        "pharmacistName": current.get("name", "Pharmacist"),
        "pharmacistLicense": "PH-12345",
        "signatureConfirmed": True,
        "dispensedAt": datetime.now(timezone.utc).isoformat(),
    }
    _MOCK_DOCUMENTATION.insert(0, record)
    return record


# ── Patient Instructions (mock generation + delivery) ───────────────────────
class InstructionsGenerate(BaseModel):
    rxId: str
    language: str = "en"
    options: Optional[dict] = None


class InstructionsSend(BaseModel):
    patientId: Optional[str] = None
    rxId: str
    content: str
    method: str  # PRINT | DIGITAL | BOTH


_INSTRUCTION_DELIVERIES: list = []


def _instructions_template(rx: dict, language: str, opts: dict) -> str:
    drug = rx["medication"]
    pt = rx["patient"]
    notes = (opts or {}).get("additionalNotes", "").strip()
    include_side = bool((opts or {}).get("includeSideEffects", True))
    include_lifestyle = bool((opts or {}).get("includeLifestyle", True))

    lang = (language or "en").lower()
    if lang.startswith("el"):
        lines = [
            f"ΟΔΗΓΙΕΣ ΑΣΘΕΝΟΥΣ — {drug['drugName']}",
            f"Ασθενής: {pt['name']}",
            "",
            "ΛΗΨΗ:",
            f"  Δόση: {drug['dose']} ({drug['form']}, {drug['route']})",
            f"  Συχνότητα: {drug['frequency']}",
            f"  Διάρκεια θεραπείας: {drug['treatmentDuration']}",
        ]
        if notes:
            lines += ["", "ΣΗΜΑΝΤΙΚΑ ΣΗΜΕΙΑ:", notes]
        if include_side:
            lines += ["", "ΠΙΘΑΝΕΣ ΑΝΕΠΙΘΥΜΗΤΕΣ ΕΝΕΡΓΕΙΕΣ:",
                      "Ενημερώστε αμέσως τον φαρμακοποιό ή ιατρό σας αν παρατηρήσετε ασυνήθιστα συμπτώματα."]
        if include_lifestyle:
            lines += ["", "ΔΙΑΤΡΟΦΙΚΕΣ / ΤΡΟΠΟΥ ΖΩΗΣ ΟΔΗΓΙΕΣ:",
                      "Διατηρήστε σταθερή πρόσληψη βιταμίνης Κ. Αποφύγετε αλκοόλ. Ενυδάτωση."]
        lines += [
            "", "ΑΝ ΞΕΧΑΣΕΤΕ ΜΙΑ ΔΟΣΗ:",
            "Πάρτε την μόλις τη θυμηθείτε, εκτός αν πλησιάζει η ώρα της επόμενης. Μη διπλασιάσετε.",
            "", "ΕΠΙΚΟΙΝΩΝΙΑ ΜΕ ΙΑΤΡΟ ΑΝ:",
            "• Εμφανιστούν σοβαρά συμπτώματα ή αιμορραγία",
            "• Δεν βελτιώνεστε εντός λίγων ημερών",
            "• Ξεκινήσετε νέα φαρμακευτική αγωγή",
        ]
    else:
        lines = [
            f"PATIENT INSTRUCTIONS — {drug['drugName']}",
            f"Patient: {pt['name']}",
            "",
            "HOW TO TAKE:",
            f"  Dose: {drug['dose']} ({drug['form']}, {drug['route']})",
            f"  Frequency: {drug['frequency']}",
            f"  Treatment duration: {drug['treatmentDuration']}",
        ]
        if notes:
            lines += ["", "KEY POINTS:", notes]
        if include_side:
            lines += ["", "POSSIBLE SIDE EFFECTS:",
                      "Tell your pharmacist or doctor immediately if you notice unusual symptoms."]
        if include_lifestyle:
            lines += ["", "DIET / LIFESTYLE:",
                      "Maintain consistent vitamin K intake. Avoid alcohol. Stay hydrated."]
        lines += [
            "", "IF YOU MISS A DOSE:",
            "Take it as soon as you remember, unless it is close to the next dose. Do not double up.",
            "", "CONTACT YOUR DOCTOR IF:",
            "• You develop severe symptoms or bleeding",
            "• You do not improve within a few days",
            "• You start any new medication",
        ]
    return "\n".join(lines)


@app.post("/instructions/generate")
async def generate_instructions(
    payload: InstructionsGenerate,
    current: dict = Depends(get_current_user),
):
    rx = _MOCK_PRESCRIPTIONS.get(payload.rxId)
    if rx is None:
        raise HTTPException(status_code=404, detail=f"Prescription {payload.rxId} not found")
    text = _instructions_template(rx, payload.language, payload.options or {})
    return {"rxId": payload.rxId, "language": payload.language, "content": text}


@app.post("/instructions/send", status_code=201)
async def send_instructions(payload: InstructionsSend, current: dict = Depends(get_current_user)):
    rx = _MOCK_PRESCRIPTIONS.get(payload.rxId)
    if rx is None:
        raise HTTPException(status_code=404, detail=f"Prescription {payload.rxId} not found")
    entry = {
        "rxId": payload.rxId,
        "patientId": payload.patientId or rx["patient"]["id"],
        "method": payload.method.upper(),
        "sentAt": datetime.now(timezone.utc).isoformat(),
        "by": current["email"],
        "size": len(payload.content or ""),
    }
    _INSTRUCTION_DELIVERIES.append(entry)
    print(f"[Instructions] Sent {payload.method} to {entry['patientId']} for {payload.rxId} ({entry['size']} chars)")
    return {"success": True, **entry}


# ── Side Effect Reports / Pharmacovigilance (mock) ──────────────────────────
# Severity: MILD | MODERATE | SEVERE
# Status:   PENDING_REVIEW | ESCALATED | EOF_REPORTED
_MOCK_SIDE_EFFECTS: list = [
    {
        "id": "ADR-2026-0009",
        "patientId": "P001",
        "patientName": "Maria Stavrou",
        "patientPhone": "+30 694 312 3456",
        "rxId": "RX2024-005",
        "drugName": "Warfarin 5 mg",
        "severity": "SEVERE",
        "status": "ESCALATED",
        "reportedAt": "2026-04-29T16:42:00+00:00",
        "symptom": "Dark stools, dizziness on standing, gum bleeding after brushing teeth.",
        "onset": "8 hours after the second dose",
    },
    {
        "id": "ADR-2026-0008",
        "patientId": "P004",
        "patientName": "Eleni Papadopoulos",
        "patientPhone": "+30 697 555 0142",
        "rxId": "RX2024-002",
        "drugName": "Warfarin 7.5 mg",
        "severity": "MODERATE",
        "status": "PENDING_REVIEW",
        "reportedAt": "2026-04-28T11:05:00+00:00",
        "symptom": "Persistent nosebleeds and unusual bruising on forearms.",
        "onset": "Within 48 hours of dose increase",
    },
    {
        "id": "ADR-2026-0007",
        "patientId": "P010",
        "patientName": "Sarah Johnson",
        "patientPhone": "+30 698 011 2233",
        "rxId": "RX2024-001",
        "drugName": "Amoxicillin 500 mg",
        "severity": "MILD",
        "status": "PENDING_REVIEW",
        "reportedAt": "2026-04-26T08:20:00+00:00",
        "symptom": "Diffuse maculopapular rash on torso, no breathing difficulty.",
        "onset": "Day 3 of antibiotic course",
    },
    {
        "id": "ADR-2026-0006",
        "patientId": "P012",
        "patientName": "Dimitrios Konstantinou",
        "patientPhone": "+30 698 555 7012",
        "rxId": None,
        "drugName": "Atorvastatin 20 mg",
        "severity": "SEVERE",
        "status": "EOF_REPORTED",
        "reportedAt": "2026-04-22T19:14:00+00:00",
        "symptom": "Generalised muscle pain, dark urine, ALT 5x upper limit.",
        "onset": "Three weeks after starting therapy",
    },
    {
        "id": "ADR-2026-0005",
        "patientId": "P020",
        "patientName": "Anna Kostas",
        "patientPhone": "+30 697 999 0011",
        "rxId": None,
        "drugName": "Clopidogrel 75 mg",
        "severity": "MODERATE",
        "status": "ESCALATED",
        "reportedAt": "2026-04-15T12:00:00+00:00",
        "symptom": "Two episodes of melena, mild dyspnoea on exertion.",
        "onset": "Two weeks into therapy",
    },
    {
        "id": "ADR-2026-0004",
        "patientId": "P031",
        "patientName": "Nikos Vlachos",
        "patientPhone": "+30 698 222 0099",
        "rxId": None,
        "drugName": "Metformin 1000 mg",
        "severity": "MILD",
        "status": "EOF_REPORTED",
        "reportedAt": "2026-03-30T10:30:00+00:00",
        "symptom": "Mild gastrointestinal upset and metallic taste.",
        "onset": "First week of therapy",
    },
]


_PATIENT_PROFILES: dict = {
    "P001": {
        "id": "P001", "amka": "15031962456",
        "firstName": "Maria", "lastName": "Stavrou", "name": "Maria Stavrou",
        "dateOfBirth": "1962-03-15", "age": 64, "sex": "F",
        "phone": "+30 694 312 3456",
        "conditions": ["Type II Diabetes", "Hypertension", "Hyperlipidemia"],
        "allergies": ["Penicillin (anaphylaxis)", "Sulfa drugs"],
        "intolerances": ["Lactose"],
        "safetyFlags": {
            "g6pd": False,
            "pregnancyWeeks": None,
            "renalFunction": "MILD_IMPAIRMENT",
            "hepaticFunction": "NORMAL",
            "breastfeeding": False,
        },
    },
    "P004": {
        "id": "P004", "amka": "08111974201",
        "firstName": "Eleni", "lastName": "Papadopoulos", "name": "Eleni Papadopoulos",
        "dateOfBirth": "1974-11-08", "age": 51, "sex": "F",
        "phone": "+30 697 555 0142",
        "conditions": ["Atrial fibrillation"],
        "allergies": [],
        "intolerances": [],
        "safetyFlags": {
            "g6pd": False,
            "pregnancyWeeks": None,
            "renalFunction": "NORMAL",
            "hepaticFunction": "NORMAL",
            "breastfeeding": False,
        },
    },
    "P010": {
        "id": "P010", "amka": "22071993789",
        "firstName": "Sarah", "lastName": "Johnson", "name": "Sarah Johnson",
        "dateOfBirth": "1993-07-22", "age": 32, "sex": "F",
        "phone": "+30 698 011 2233",
        "conditions": ["Bacterial sinusitis"],
        "allergies": [],
        "intolerances": [],
        "safetyFlags": {
            "g6pd": False,
            "pregnancyWeeks": 18,
            "renalFunction": "NORMAL",
            "hepaticFunction": "NORMAL",
            "breastfeeding": False,
        },
    },
    "P012": {
        "id": "P012", "amka": "03051961334",
        "firstName": "Dimitrios", "lastName": "Konstantinou", "name": "Dimitrios Konstantinou",
        "dateOfBirth": "1961-05-03", "age": 64, "sex": "M",
        "phone": "+30 698 555 7012",
        "conditions": ["Hyperlipidemia", "Coronary artery disease"],
        "allergies": [],
        "intolerances": [],
        "safetyFlags": {
            "g6pd": False,
            "pregnancyWeeks": None,
            "renalFunction": "NORMAL",
            "hepaticFunction": "MODERATE_IMPAIRMENT",
            "breastfeeding": False,
        },
    },
    "P020": {
        "id": "P020", "amka": "12101948112",
        "firstName": "Anna", "lastName": "Kostas", "name": "Anna Kostas",
        "dateOfBirth": "1948-10-12", "age": 77, "sex": "F",
        "phone": "+30 697 999 0011",
        "conditions": ["Coronary stent (2025)", "Atrial fibrillation"],
        "allergies": [],
        "intolerances": [],
        "safetyFlags": {
            "g6pd": False,
            "pregnancyWeeks": None,
            "renalFunction": "MODERATE_IMPAIRMENT",
            "hepaticFunction": "NORMAL",
            "breastfeeding": False,
        },
    },
    "P031": {
        "id": "P031", "amka": "27021982557",
        "firstName": "Nikos", "lastName": "Vlachos", "name": "Nikos Vlachos",
        "dateOfBirth": "1982-02-27", "age": 43, "sex": "M",
        "phone": "+30 698 222 0099",
        "conditions": ["Type II Diabetes"],
        "allergies": ["Aspirin (urticaria)"],
        "intolerances": [],
        "safetyFlags": {
            "g6pd": True,
            "pregnancyWeeks": None,
            "renalFunction": "NORMAL",
            "hepaticFunction": "NORMAL",
            "breastfeeding": False,
        },
    },
}


# Static prescription history per patient (additional rxs that are not part
# of the verification mock). The current status of any rx that is also seeded
# in _MOCK_PRESCRIPTIONS is overlaid live so flag/approve actions reflect.
_PATIENT_RX_HISTORY_BASE: dict = {
    "P001": [
        {"rxId": "RX2024-005", "date": "2026-04-28", "drugName": "Warfarin 5 mg",      "prescriberName": "Dr. Michael Chen",   "status": "PENDING"},
        {"rxId": "RX2023-118", "date": "2025-11-12", "drugName": "Atorvastatin 20 mg", "prescriberName": "Dr. Michael Chen",   "status": "COMPLETED"},
        {"rxId": "RX2023-077", "date": "2025-09-03", "drugName": "Metformin 1000 mg",  "prescriberName": "Dr. Maria Lampraki", "status": "COMPLETED"},
        {"rxId": "RX2023-022", "date": "2025-04-19", "drugName": "Ramipril 5 mg",      "prescriberName": "Dr. Maria Lampraki", "status": "COMPLETED"},
    ],
    "P004": [
        {"rxId": "RX2024-002", "date": "2026-03-11", "drugName": "Warfarin 7.5 mg",    "prescriberName": "Dr. Emily Roberts",  "status": "FLAGGED"},
        {"rxId": "RX2023-054", "date": "2025-08-20", "drugName": "Bisoprolol 5 mg",    "prescriberName": "Dr. Emily Roberts",  "status": "COMPLETED"},
    ],
    "P010": [
        {"rxId": "RX2024-001", "date": "2026-03-11", "drugName": "Amoxicillin 500 mg", "prescriberName": "Dr. Michael Chen",   "status": "PENDING"},
    ],
    "P012": [
        {"rxId": "RX2023-091", "date": "2025-12-08", "drugName": "Atorvastatin 20 mg", "prescriberName": "Dr. David Lee",      "status": "COMPLETED"},
        {"rxId": "RX2023-044", "date": "2025-06-14", "drugName": "Aspirin 100 mg",     "prescriberName": "Dr. David Lee",      "status": "COMPLETED"},
    ],
    "P020": [
        {"rxId": "RX2023-066", "date": "2025-09-30", "drugName": "Clopidogrel 75 mg",  "prescriberName": "Dr. Sophia Roussou", "status": "COMPLETED"},
    ],
    "P031": [
        {"rxId": "RX2023-032", "date": "2025-05-18", "drugName": "Metformin 1000 mg",  "prescriberName": "Dr. Niko Pateli",    "status": "COMPLETED"},
    ],
}


def _patient_rx_history(patient_id: str) -> list:
    rows = list(_PATIENT_RX_HISTORY_BASE.get(patient_id, []))
    for row in rows:
        live = _MOCK_PRESCRIPTIONS.get(row["rxId"])
        if live and live.get("status"):
            row["status"] = live["status"]
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows


def _patient_adr_history(patient_id: str) -> list:
    rows = [r for r in _MOCK_SIDE_EFFECTS if r["patientId"] == patient_id]
    rows.sort(key=lambda r: r["reportedAt"], reverse=True)
    return rows


def _resolve_patient(patient_key: str) -> Optional[dict]:
    """Look up by patient id (P001) or AMKA (15031962456)."""
    direct = _PATIENT_PROFILES.get(patient_key)
    if direct:
        return direct
    for p in _PATIENT_PROFILES.values():
        if p.get("amka") == patient_key:
            return p
    return None


def _se_stats() -> dict:
    s = {"total": len(_MOCK_SIDE_EFFECTS), "pendingReview": 0, "severe": 0, "escalated": 0}
    for r in _MOCK_SIDE_EFFECTS:
        if r["status"] == "PENDING_REVIEW":
            s["pendingReview"] += 1
        if r["severity"] == "SEVERE":
            s["severe"] += 1
        if r["status"] == "ESCALATED":
            s["escalated"] += 1
    return s


_SEVERITY_RANK = {"MILD": 0, "MODERATE": 1, "SEVERE": 2}
_STATUS_RANK   = {"PENDING_REVIEW": 0, "ESCALATED": 1, "EOF_REPORTED": 2}


@app.get("/side-effects")
async def list_side_effects(
    q: Optional[str] = Query(None, description="Free-text search across patient, drug, symptom."),
    sort: Optional[str] = Query("date", description="date | severity | status"),
    current: dict = Depends(get_current_user),
):
    items = list(_MOCK_SIDE_EFFECTS)
    if q:
        needle = q.lower().strip()
        items = [
            r for r in items
            if needle in r["patientName"].lower()
            or needle in r["drugName"].lower()
            or needle in r["symptom"].lower()
        ]
    sort_key = (sort or "date").lower()
    if sort_key == "severity":
        items.sort(key=lambda r: (_SEVERITY_RANK.get(r["severity"], -1), r["reportedAt"]), reverse=True)
    elif sort_key == "status":
        items.sort(key=lambda r: (_STATUS_RANK.get(r["status"], -1), r["reportedAt"]), reverse=True)
    else:
        items.sort(key=lambda r: r["reportedAt"], reverse=True)
    return {"items": items, "stats": _se_stats()}


def _next_status(current_status: str) -> str:
    if current_status == "PENDING_REVIEW":
        return "ESCALATED"
    if current_status == "ESCALATED":
        return "EOF_REPORTED"
    return current_status


@app.post("/side-effects/{report_id}/flag")
async def flag_side_effect(report_id: str, current: dict = Depends(get_current_user)):
    """Advance the report's pharmacovigilance status one step (PENDING_REVIEW → ESCALATED → EOF_REPORTED)."""
    rec = next((r for r in _MOCK_SIDE_EFFECTS if r["id"] == report_id), None)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Side-effect report {report_id} not found")
    previous = rec["status"]
    rec["status"] = _next_status(previous)
    rec["lastFlaggedAt"] = datetime.now(timezone.utc).isoformat()
    rec["lastFlaggedBy"] = current["email"]
    return {"success": True, "id": report_id, "previousStatus": previous, "status": rec["status"]}


@app.get("/patients/{patient_id}/prescriptions")
async def get_patient_prescriptions(patient_id: str, current: dict = Depends(get_current_user)):
    profile = _resolve_patient(patient_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    return {"items": _patient_rx_history(profile["id"])}


@app.get("/patients/{patient_id}/side-effects")
async def get_patient_side_effects(patient_id: str, current: dict = Depends(get_current_user)):
    profile = _resolve_patient(patient_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    return {"items": _patient_adr_history(profile["id"])}


@app.get("/patients/{patient_id}")
async def get_patient(patient_id: str, current: dict = Depends(get_current_user)):
    profile = _resolve_patient(patient_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    return profile


@app.get("/prescriptions/next")
async def next_pending_prescription(current: dict = Depends(get_current_user)):
    """Return the next PENDING prescription in the queue (for the keyboard shortcut). Declared before the {rx_id} catch-all so FastAPI matches it first."""
    for base in _MOCK_QUEUE_BASE:
        rx = _MOCK_PRESCRIPTIONS.get(base["rxId"])
        status = rx["status"] if rx else base["status"]
        if status == "PENDING":
            return {**base, "status": status}
    raise HTTPException(status_code=404, detail="No pending prescriptions in the queue")


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
    rx["status"] = "COMPLETED"
    rx["completedAt"] = datetime.now(timezone.utc).isoformat()
    return {"success": True, "rxId": rx_id, "status": rx["status"], "completedAt": rx["completedAt"]}


# Static queue rows that may not have full prescription details. The actual
# status comes from _MOCK_PRESCRIPTIONS when the rxId is also seeded there.
_MOCK_QUEUE_BASE = [
    {"rxId": "RX2024-001", "patientName": "Sarah Johnson",  "medication": "Amoxicillin", "physician": "Dr. Michael Chen",  "date": "2026-03-11", "status": "PENDING"},
    {"rxId": "RX2024-002", "patientName": "James Martinez", "medication": "Warfarin",    "physician": "Dr. Emily Roberts", "date": "2026-03-11", "status": "FLAGGED"},
    {"rxId": "RX2024-003", "patientName": "Maria Garcia",   "medication": "Lisinopril",  "physician": "Dr. David Lee",     "date": "2026-03-11", "status": "PENDING"},
    {"rxId": "RX2024-005", "patientName": "Maria Stavrou",  "medication": "Warfarin",    "physician": "Dr. Michael Chen",  "date": "2026-04-28", "status": "PENDING"},
]


@app.get("/prescriptions")
async def list_prescriptions(current: dict = Depends(get_current_user)):
    """Return the prescription queue for the dashboard, with up-to-date statuses."""
    items = []
    for base in _MOCK_QUEUE_BASE:
        rx = _MOCK_PRESCRIPTIONS.get(base["rxId"])
        status = rx["status"] if rx else base["status"]
        items.append({**base, "status": status})
    return {"items": items}


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
