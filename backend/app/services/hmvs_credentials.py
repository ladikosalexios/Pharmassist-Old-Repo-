"""Resolve the HMVS OAuth2 client-credentials pair for a pharmacy.

Two layers, in priority order — mirrors how ``auth.login`` handles the Pharmapi
creds (decrypt the per-link row), with an env fallback the Pharmapi flow does not
need:

1. **Per-pharmacy** — the encrypted ``hmvs_client_id`` / ``hmvs_client_secret``
   columns on the pharmacist's default ``pharmacist_pharmacies`` link (the IQE
   equipment creds, used at certification / in prod).
2. **Env fallback** — ``settings.hmvs_client_id`` / ``hmvs_client_secret`` (the
   ITE *shared* published credentials used for development against the sandbox).

SECURITY: the decrypted secret is returned in-memory to the HMVS client only —
never logged, never persisted plaintext.
"""

from __future__ import annotations

from ..config import get_settings
from ..crypto import decrypt_credential
from ..db.models.pharmacist_pharmacy import PharmacistPharmacy


def resolve_hmvs_credentials(link: PharmacistPharmacy | None) -> tuple[str, str]:
    """Return ``(client_id, client_secret)`` for HMVS calls on this pharmacy.

    Prefers the link's encrypted per-pharmacy columns; falls back to the
    env-sourced ITE shared creds. Raises ``RuntimeError`` if neither layer
    yields a usable pair — the caller (router) translates that to a 503 so the
    failure is explicit rather than a silent empty-string token request.
    """
    if link is not None and link.hmvs_client_id and link.hmvs_client_secret:
        return (
            decrypt_credential(link.hmvs_client_id),
            decrypt_credential(link.hmvs_client_secret),
        )

    settings = get_settings()
    if settings.hmvs_client_id and settings.hmvs_client_secret:
        return settings.hmvs_client_id, settings.hmvs_client_secret

    raise RuntimeError(
        "No HMVS client credentials available — set HMVS_CLIENT_ID / "
        "HMVS_CLIENT_SECRET (ITE shared creds) or store encrypted per-pharmacy "
        "creds on the pharmacist_pharmacies link."
    )
