"""Pharmacist login + session info (ADR-003: JSON body, JWT in httpOnly cookie).

The JWT lives ONLY in a SameSite=Strict, httpOnly cookie — it is never
returned in the response body. The response carries display fields
(pharmacist_name, pharmacy, ids) the SPA needs to render its shell.
"""

from datetime import UTC, datetime

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import get_settings
from ..crypto import decrypt_credential, encrypt_credential
from ..db.models.invitation import Invitation
from ..db.models.pharmacist import Pharmacist
from ..db.models.pharmacist_pharmacy import PharmacistPharmacy
from ..db.session import get_session
from ..deps import get_current_user
from ..schemas.auth import (
    AcceptInviteRequest,
    InviteInfo,
    LoginRequest,
    LoginResponse,
    PharmacistMe,
)
from ..services.pharmapi import (
    _start_pharmapi_session,
    verify_pharmapi_credentials_with_decrypted,
)
from ..services.security import TOKEN_EXPIRE_MIN, create_jwt

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_NAME = "pharmassist_session"
# Keep the cookie's Max-Age aligned with the JWT's exp claim so the browser
# drops the cookie at the same moment the server would reject the token.
# Drift here means dead cookies sticking around, or live cookies whose tokens
# already 401 — both confusing.
COOKIE_MAX_AGE_SECONDS = TOKEN_EXPIRE_MIN * 60

# Pinned to the same cost factor (rounds=12) as real password hashes (see
# scripts/seed.py). Used to neutralise the timing side-channel when an email
# isn't on file — we always pay one bcrypt verify regardless. Keep in sync if
# the production cost factor ever changes.
_DUMMY_PASSWORD_HASH: str = bcrypt.hashpw(
    b"unused-dummy-for-constant-time-login", bcrypt.gensalt(rounds=12)
).decode()


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> LoginResponse:
    """Authenticate against the pharmacists table + ΗΔΥΚΑ, issue a session cookie."""
    pharmacist = await db.scalar(
        select(Pharmacist).where(
            Pharmacist.email == body.email,
            Pharmacist.active.is_(True),
        )
    )
    # Always run bcrypt — against the real hash if the account exists, against
    # the dummy hash otherwise — so unknown-email and wrong-password requests
    # take the same wall-clock time. Do NOT short-circuit on `pharmacist is None`
    # before checkpw, or you leak account existence via response latency.
    password_hash = pharmacist.password_hash if pharmacist is not None else _DUMMY_PASSWORD_HASH
    password_ok = bcrypt.checkpw(body.password.encode(), password_hash.encode())
    if pharmacist is None or not password_ok:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    link = await pharmacist.get_default_pharmacy_link(db)
    if link is None:
        raise HTTPException(status_code=500, detail="Pharmacist has no default pharmacy linked")
    # link.pharmacy is eager-loaded via selectinload + FK-guaranteed non-null.
    pharmacy = link.pharmacy

    # Refuse to log in if the link row exists but its ΗΔΥΚΑ creds are NULL/blank —
    # the previous `or ""` fallback would have fed empty ciphertext into
    # decrypt_credential and either thrown an opaque InvalidTag or, worse,
    # silently decoded to empty plaintext that we'd then send upstream.
    if not link.pharmapi_username or not link.pharmapi_password:
        raise HTTPException(
            status_code=500,
            detail="Pharmacist's pharmacy link is missing ΗΔΥΚΑ credentials",
        )
    # Decrypt ΗΔΥΚΑ credentials in-memory; never log or persist plaintext.
    pharmapi_username = decrypt_credential(link.pharmapi_username)
    pharmapi_password = decrypt_credential(link.pharmapi_password)
    profile = await verify_pharmapi_credentials_with_decrypted(pharmapi_username, pharmapi_password)
    _start_pharmapi_session(profile)

    # Audit-grade timestamp; only updated once everything upstream has accepted
    # the login, so a 502 from Pharmapi doesn't masquerade as a successful auth
    # in the column.
    pharmacist.last_login_at = datetime.now(UTC)
    await db.commit()

    # JWT payload deliberately holds ids + email only — no creds, no profile.
    token = create_jwt(
        {
            "sub": str(pharmacist.id),
            "pharmacy_id": str(pharmacy.id),
            "email": pharmacist.email,
        }
    )
    settings = get_settings()
    # path="/" is the Starlette default today, but pin it on both set_cookie
    # and delete_cookie so a future default change can't leave a deletion
    # request scoped to a different path than the original set.
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=settings.cookie_httponly,
        samesite=settings.cookie_samesite,
        secure=settings.cookie_secure,
        max_age=COOKIE_MAX_AGE_SECONDS,
        path="/",
    )

    return LoginResponse(
        pharmacist_name=pharmacist.full_name,
        pharmacy=pharmacy.name,
        pharmacist_id=str(pharmacist.id),
        pharmacy_id=str(pharmacy.id),
    )


@router.post("/logout")
async def logout(response: Response) -> dict:
    """Clear the session cookie. Idempotent — safe to call without a cookie."""
    settings = get_settings()
    response.delete_cookie(
        key=COOKIE_NAME,
        httponly=settings.cookie_httponly,
        samesite=settings.cookie_samesite,
        secure=settings.cookie_secure,
        path="/",
    )
    return {"ok": True}


@router.get("/me", response_model=PharmacistMe)
async def me(current: dict = Depends(get_current_user)) -> PharmacistMe:
    return PharmacistMe(
        email=current["email"],
        name=current["name"],
        pharmacy=current["pharmacy"],
        pharmacist_id=current["pharmacist_id"],
        pharmacy_id=current["pharmacy_id"],
    )


# TODO(security): token in the URL path lands in access logs / browser history.
# Move to a POST body or short-lived signed param once the SPA flow is finalized.
@router.get("/invite/{token}", response_model=InviteInfo)
async def get_invite_info(
    token: str,
    db: AsyncSession = Depends(get_session),
) -> InviteInfo:
    """Public: look up a pending invitation so the SPA can render the
    accept-invite form (pharmacy name + address, invited email)."""
    invitation = await db.scalar(
        select(Invitation)
        .where(Invitation.token == token)
        .options(selectinload(Invitation.pharmacy))
    )
    if not invitation:
        raise HTTPException(404, "Invite not found")

    now = datetime.now(UTC)
    if now > invitation.expires_at or invitation.accepted_at is not None:
        raise HTTPException(410, "Invite has expired or already been used")

    p = invitation.pharmacy
    parts = [
        part
        for part in [
            (f"{p.street_name} {p.street_number}".strip() if p.street_name else p.address),
            p.area,
            p.city,
            p.postal_code,
        ]
        if part
    ]
    pharmacy_address = ", ".join(parts) if parts else ""

    return InviteInfo(
        pharmacy_name=p.name,
        pharmacy_address=pharmacy_address,
        email=invitation.email,
        expires_at=invitation.expires_at.isoformat(),
    )


@router.post("/accept-invite")
async def accept_invite(
    body: AcceptInviteRequest,
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Public: redeem an invitation — validate ΗΔΥΚΑ credentials, then create
    the pharmacist account + pharmacy link and burn the token."""
    # 1. Validate token
    invitation = await db.scalar(
        select(Invitation)
        .where(Invitation.token == body.token)
        .options(selectinload(Invitation.pharmacy))
    )
    if not invitation:
        raise HTTPException(404, "Invite not found")

    now = datetime.now(UTC)
    if now > invitation.expires_at or invitation.accepted_at is not None:
        raise HTTPException(410, "Invite has expired or already been used")

    # 2. Duplicate checks — email and ΗΔΥΚΑ licence number each carry a
    # UNIQUE constraint, so catch collisions here for a clean 409 rather
    # than an IntegrityError 500 on commit.
    existing = await db.scalar(select(Pharmacist).where(Pharmacist.email == invitation.email))
    if existing:
        raise HTTPException(409, "Account already exists for this email")
    licence_taken = await db.scalar(
        select(Pharmacist).where(Pharmacist.eof_licence_no == body.eof_licence_no)
    )
    if licence_taken:
        raise HTTPException(409, "A pharmacist with this licence number already exists")

    # 3. Validate ΗΔΥΚΑ credentials BEFORE any DB write — never create the
    # account if Pharmapi rejects them. Only a 401 means "bad credentials";
    # infra failures (missing API key, expired session, upstream down) must
    # surface as-is instead of masquerading as a credential rejection.
    try:
        profile = await verify_pharmapi_credentials_with_decrypted(
            body.pharmapi_username, body.pharmapi_password
        )
    except HTTPException as exc:
        if exc.status_code == 401:
            raise HTTPException(400, "ΗΔΥΚΑ credentials rejected by Pharmapi") from None
        raise
    if not profile:
        raise HTTPException(400, "ΗΔΥΚΑ credentials rejected by Pharmapi")

    # 4. Create pharmacist + link + burn the token in one transaction.
    hashed = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt(rounds=12)).decode()
    pharmacist = Pharmacist(
        email=invitation.email,
        password_hash=hashed,
        full_name=body.full_name,
        eof_licence_no=body.eof_licence_no,
        phone=body.phone,
        role="pharmacist",
        active=True,
    )
    db.add(pharmacist)
    await db.flush()  # assign pharmacist.id without committing

    link = PharmacistPharmacy(
        pharmacist_id=pharmacist.id,
        pharmacy_id=invitation.pharmacy_id,
        pharmapi_username=encrypt_credential(body.pharmapi_username),
        pharmapi_password=encrypt_credential(body.pharmapi_password),
        is_default=True,
    )
    db.add(link)
    invitation.accepted_at = now  # invalidate the token
    await db.commit()

    return {"ok": True}
