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

Internal layout (work in progress):
  app/schemas/   — Pydantic API contracts (one file per domain)
  app/services/  — in-memory stores + business helpers (mock data, JWT,
                   Pharmapi client, PDF rendering, etc.)
  main.py        — FastAPI app + middleware + route handlers (this file)

The next refactor step splits the route handlers into per-domain APIRouters.
"""

import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

# ── API contracts (Pydantic) ────────────────────────────────────────────────
from .app.schemas import (
    DocumentationCreate,
    InstructionsGenerate,
    InstructionsSend,
    MessagePayload,
    PharmacistMe,
    PhysicianNotification,
    PrescriptionPatch,
    SessionStatus,
    TokenResponse,
)

# ── Services (mock stores + business logic) ─────────────────────────────────
# Aliased here so the existing route handlers below keep their original
# variable names without churn. The next step (routers) drops the aliases
# entirely and references the service modules directly.
from .app.services.security import (
    USERS,
    create_jwt,
    decode_jwt,
    verify_password,
)
from .app.services.pharmapi import (
    PHARMAPI_API_KEY,
    SESSION_WINDOW_SECONDS,
    pharmapi_get,
    pharmapi_session as _pharmapi_session,
    session_is_valid,
)
from .app.services.safety_checks import MOCK_SAFETY_CHECKS as _MOCK_SAFETY_CHECKS
from .app.services.spc import MOCK_SPC as _MOCK_SPC
from .app.services.alerts import MOCK_ACTIVE_ALERTS as _MOCK_ACTIVE_ALERTS
from .app.services.messages import MOCK_MESSAGES as _MOCK_MESSAGES
from .app.services.prescriptions import (
    MOCK_PRESCRIPTIONS as _MOCK_PRESCRIPTIONS,
    MOCK_QUEUE_BASE as _MOCK_QUEUE_BASE,
)
from .app.services.side_effects import (
    MOCK_SIDE_EFFECTS as _MOCK_SIDE_EFFECTS,
    SEVERITY_RANK as _SEVERITY_RANK,
    STATUS_RANK as _STATUS_RANK,
    next_status as _next_status,
    stats as _se_stats,
)
from .app.services.patients import (
    adr_history as _patient_adr_history,
    resolve as _resolve_patient,
    rx_history as _patient_rx_history,
)
from .app.services.documentation import (
    MOCK_DOCUMENTATION as _MOCK_DOCUMENTATION,
    csv_response as _csv_response,
    filter_records as _filter_docs,
    mark_exported as _mark_exported,
    stats as _doc_stats,
)
from .app.services.pdf import (
    REPORTLAB_AVAILABLE,
    full_report as _pdf_full_report,
    pdf_response as _pdf_response,
    safe_filename_part as _safe_filename_part,
    single_record as _pdf_single_record,
)
from .app.services.instructions import (
    INSTRUCTION_DELIVERIES as _INSTRUCTION_DELIVERIES,
    render_instructions as _instructions_template,
)
from .app.services.notifications import PHYSICIAN_NOTIFICATIONS as _PHYSICIAN_NOTIFICATIONS


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


# ── Routes ───────────────────────────────────────────────────────────────────
# Pydantic schemas live in app/schemas/. Mock data + helpers live in
# app/services/. This file only wires HTTP → service.

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


@app.get("/safety-checks/{rx_id}")
async def get_safety_checks(rx_id: str, current: dict = Depends(get_current_user)):
    """Return the automated safety checks for a prescription."""
    checks = _MOCK_SAFETY_CHECKS.get(rx_id)
    if checks is None:
        raise HTTPException(status_code=404, detail=f"Prescription {rx_id} not found")
    return {"rxId": rx_id, "checks": checks}


@app.get("/spc/{atc_code}")
async def get_spc(atc_code: str, current: dict = Depends(get_current_user)):
    """Return the Summary of Product Characteristics for a given ATC code."""
    spc = _MOCK_SPC.get(atc_code)
    if spc is None:
        raise HTTPException(status_code=404, detail=f"SPC not found for ATC {atc_code}")
    return spc


@app.get("/alerts/active")
async def get_active_alerts(current: dict = Depends(get_current_user)):
    """Return active safety alerts for the dashboard."""
    return {"alerts": _MOCK_ACTIVE_ALERTS}


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


# Order matters: fixed paths must be declared *before* the catch-all {id} path.
@app.get("/documentation/export")
async def export_documentation(
    q: Optional[str] = Query(None, description="Free-text search across patient, rxId, drug."),
    method: Optional[str] = Query(None, description="PRINT | DIGITAL | BOTH | ALL"),
    format: str = Query("pdf", description="pdf | csv (default pdf)"),
    current: dict = Depends(get_current_user),
):
    rows = _filter_docs(q, method)
    _mark_exported(rows)
    today = datetime.now(timezone.utc).date().isoformat()
    fmt = (format or "pdf").lower()
    if fmt == "pdf" and REPORTLAB_AVAILABLE:
        return _pdf_response(_pdf_full_report(rows, current), f"PharmAssist_DocumentationLog_{today}.pdf")
    return _csv_response(rows, f"PharmAssist_DocumentationLog_{today}.csv")


@app.get("/documentation/{doc_id}/export")
async def export_documentation_record(
    doc_id: str,
    format: str = Query("pdf", description="pdf | csv (default pdf)"),
    current: dict = Depends(get_current_user),
):
    rec = next((d for d in _MOCK_DOCUMENTATION if d["id"] == doc_id), None)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Documentation record {doc_id} not found")
    _mark_exported([rec])
    fname_base = f"PharmAssist_Record_{_safe_filename_part(rec['rxId'])}_{_safe_filename_part(rec['patientName'])}"
    fmt = (format or "pdf").lower()
    if fmt == "pdf" and REPORTLAB_AVAILABLE:
        return _pdf_response(_pdf_single_record(rec, current), f"{fname_base}.pdf")
    return _csv_response([rec], f"{fname_base}.csv")


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


@app.post("/prescriptions/{rx_id}/approve")
async def approve_prescription(rx_id: str, current: dict = Depends(get_current_user)):
    rx = _MOCK_PRESCRIPTIONS.get(rx_id)
    if not rx:
        raise HTTPException(status_code=404, detail=f"Prescription {rx_id} not found")
    rx["status"] = "COMPLETED"
    rx["completedAt"] = datetime.now(timezone.utc).isoformat()
    return {"success": True, "rxId": rx_id, "status": rx["status"], "completedAt": rx["completedAt"]}


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
