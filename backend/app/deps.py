"""Shared FastAPI dependencies.

Routers import ``get_current_user`` from here instead of from main.py — that
way main.py can include routers without each router pulling main back in
(circular-import bait).
"""

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from .services.security import USERS, decode_jwt


# tokenUrl is what the FastAPI Swagger UI uses for its "Authorize" button —
# it must match the actual login route, registered in routers/auth.py.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    payload = decode_jwt(token)
    user = USERS.get(payload.get("sub", ""))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return {"email": payload["sub"], **user}
