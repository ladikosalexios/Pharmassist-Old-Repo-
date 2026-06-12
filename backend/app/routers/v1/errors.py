"""B2B /v1 error envelope + request-id plumbing (BC-5).

Every /v1 error renders as::

    {"error": {"code": "...", "message": "...", "request_id": "..."}}

with optional ``upstream_code`` when a ΗΔΥΚΑ G-code was identified. Stable
``code`` strings are the partner-facing contract; HTTP statuses match them.
AI (Tier-2) endpoints add one more stable code: ``ai_unavailable`` (503), raised
by the LLM seam (T2-2) on a timeout / upstream failure so a degraded AI feature
is distinguishable from a real error; deterministic endpoints never emit it.

B2C is untouched: the app-level handlers delegate to FastAPI's defaults for
any path outside /v1, so existing ``{"detail": ...}`` bodies are byte-
identical. Service-layer HTTPExceptions (which carry B2C-shaped operator
hints like "call POST /pharmapi/connect first") are translated — and 5xx
details suppressed — before reaching an API customer. PHI rule: envelope
messages never carry AMKA or patient names; upstream bodies are already
truncated to 200 chars in services/pharmapi.py.
"""

import re

from fastapi import FastAPI, Request
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.services.llm import AiUnavailableError, PiiBoundaryError

_G_CODE_RE = re.compile(r"\bG\d{2}\b")

_CODE_BY_STATUS = {
    400: "validation_failed",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    410: "gone",
    422: "validation_failed",
    429: "rate_limited",
}


class V1Error(Exception):
    """Raise inside /v1 handlers for envelope errors with an explicit code.

    ``headers`` rides into the envelope response unchanged — used by the
    rate limiter for ``Retry-After`` (FT-1).
    """

    def __init__(
        self,
        code: str,
        status_code: int,
        message: str,
        headers: dict[str, str] | None = None,
    ):
        self.code = code
        self.status_code = status_code
        self.message = message
        self.headers = headers
        super().__init__(message)


def request_id_of(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _envelope_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    upstream_code: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    error: dict = {"code": code, "message": message, "request_id": request_id_of(request)}
    if upstream_code:
        error["upstream_code"] = upstream_code
    return JSONResponse(status_code=status_code, content={"error": error}, headers=headers)


def _translate_http_exception(exc: StarletteHTTPException) -> tuple[str, str, str | None]:
    """Map an app/service HTTPException to (code, message, upstream_code).

    4xx details are caller-actionable and pass through (after the session-
    expiry special case). 5xx details are operator-facing (env-var names,
    B2C flow hints) and are replaced with a generic message.
    """
    detail = str(exc.detail)
    match = _G_CODE_RE.search(detail)
    upstream_code = match.group(0) if match else None

    if upstream_code in ("G12", "G14") or "session expired" in detail.lower():
        return (
            "upstream_session_expired",
            "ΗΔΥΚΑ session expired — retry (a new session is established automatically)",
            upstream_code,
        )
    if exc.status_code >= 500:
        if upstream_code or "Pharmapi" in detail or exc.status_code == 502:
            return ("upstream_error", "Upstream ΗΔΥΚΑ error", upstream_code)
        return ("internal", "Internal server error", None)
    code = _CODE_BY_STATUS.get(exc.status_code, "error")
    return (code, detail, upstream_code)


def install_v1_exception_handlers(app: FastAPI) -> None:
    """Register app-level handlers that envelope /v1 errors and delegate
    everything else to FastAPI's defaults (B2C bodies unchanged)."""

    @app.exception_handler(V1Error)
    async def _v1_error(request: Request, exc: V1Error):
        return _envelope_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            headers=exc.headers,
        )

    @app.exception_handler(AiUnavailableError)
    async def _ai_unavailable(request: Request, exc: AiUnavailableError):
        # The T2-2 LLM seam failed (timeout / transport / non-200). Stable
        # ``ai_unavailable`` code so a partner can distinguish a degraded AI
        # feature from a real error and retry — never the provider's body (PHI /
        # internals). Only AI endpoints raise this; deterministic surfaces never
        # touch the seam (tests/test_no_tier1_llm_import.py).
        return _envelope_response(
            request,
            status_code=503,
            code="ai_unavailable",
            message="AI feature temporarily unavailable — please retry shortly",
        )

    @app.exception_handler(PiiBoundaryError)
    async def _pii_boundary(request: Request, exc: PiiBoundaryError):
        # The T2-2 PII scrub refused a prompt because caller-supplied content
        # carried a PII-shaped token (e.g. an AMKA in a condition code). That is a
        # caller-data error, not a server fault — surface it as a 422 rather than a
        # raw 500, for every AI endpoint at once. The message is fixed and never
        # echoes the offending token (PHI rule); the exception's own message
        # already withholds it.
        return _envelope_response(
            request,
            status_code=422,
            code="validation_failed",
            message=(
                "Request contains a PII-shaped token (e.g. an AMKA) in a clinical "
                "field — patient identity must not be sent to AI endpoints."
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(request: Request, exc: StarletteHTTPException):
        if not request.url.path.startswith("/v1"):
            return await http_exception_handler(request, exc)
        code, message, upstream_code = _translate_http_exception(exc)
        return _envelope_response(
            request,
            status_code=exc.status_code,
            code=code,
            message=message,
            upstream_code=upstream_code,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(request: Request, exc: RequestValidationError):
        if not request.url.path.startswith("/v1"):
            return await request_validation_exception_handler(request, exc)
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(part) for part in first.get("loc", []) if part != "body")
        msg = first.get("msg", "invalid request")
        return _envelope_response(
            request,
            status_code=422,
            code="validation_failed",
            message=f"{loc}: {msg}" if loc else msg,
        )
