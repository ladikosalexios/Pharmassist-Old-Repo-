"""Shared plumbing for SPC source adapters: result types + polite download.

Politeness: one download at a time per source with a minimum interval
between requests (``spc_fetch_min_interval_seconds``), an identifying
User-Agent, and a hard size cap. ``_transport`` is a test seam — tests
inject an ``httpx.MockTransport`` without monkeypatching httpx itself.
"""

import asyncio
import time
from dataclasses import dataclass, field

import httpx

from ...config import get_settings

# Test seam: when set, every client this module builds uses it.
_transport: httpx.AsyncBaseTransport | None = None

_locks: dict[str, asyncio.Lock] = {}
_last_request_at: dict[str, float] = {}


@dataclass(frozen=True)
class FoundDoc:
    url: str
    doc_type: str  # spc | pil | combined
    source: str  # eof | ema


@dataclass
class AdapterResult:
    docs: list[FoundDoc] = field(default_factory=list)
    error: str | None = None


def _client(**kwargs) -> httpx.AsyncClient:
    settings = get_settings()
    kwargs.setdefault("timeout", settings.spc_fetch_timeout_seconds)
    kwargs.setdefault("headers", {})
    kwargs["headers"].setdefault("User-Agent", settings.spc_fetch_user_agent)
    if _transport is not None:
        kwargs["transport"] = _transport
    return httpx.AsyncClient(**kwargs)


async def _throttle(source: str) -> None:
    settings = get_settings()
    lock = _locks.setdefault(source, asyncio.Lock())
    async with lock:
        elapsed = time.monotonic() - _last_request_at.get(source, 0.0)
        wait = settings.spc_fetch_min_interval_seconds - elapsed
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request_at[source] = time.monotonic()


async def download(url: str, *, source: str, cookies=None) -> bytes:
    """Fetch one document, throttled per source and size-capped.

    Raises httpx errors / ValueError — the ADAPTER catches and converts to
    AdapterResult.error; ingestion callers never see exceptions from here.
    """
    settings = get_settings()
    await _throttle(source)
    async with _client(follow_redirects=True, cookies=cookies) as client:
        r = await client.get(url)
        r.raise_for_status()
        if len(r.content) > settings.spc_max_pdf_bytes:
            raise ValueError(f"document exceeds size cap ({len(r.content)} bytes)")
        return r.content
