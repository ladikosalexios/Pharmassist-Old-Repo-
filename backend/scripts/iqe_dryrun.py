"""IQE dry-run harness — drive test packs through the real HMVS client and log
each request/response as JSONL evidence for the qualification testbook.

Live-only by design: forces HMVS_MOCK=false before importing config, and refuses
to run if mock is still somehow on. Never hits the mock path.

Default is VERIFY-ONLY (read-only). Supply/reactivate MUTATE pack state in IQE
(reversible within the 10-day window / via test-data reset) and are opt-in:

    # safe, read-only:
    docker compose exec backend python -m scripts.iqe_dryrun --manifest scripts/iqe_packs.json
    # state-changing (explicit):
    docker compose exec backend python -m scripts.iqe_dryrun --manifest … --supply --reactivate

Credentials + IQE URLs come from env (inject the same way the probe does — never
hardcode). Output: scripts/iqe_dryrun_<stamp>.jsonl, one line per operation,
Authorization/secret never logged.
"""

from __future__ import annotations

import os

# Force live BEFORE importing app.config (get_settings snapshots hmvs_mock).
os.environ["HMVS_MOCK"] = "false"

import argparse  # noqa: E402
import asyncio  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
from datetime import UTC, datetime  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import get_settings  # noqa: E402
from app.services import hmvs  # noqa: E402
from app.utils.environment import is_mock_hmvs  # noqa: E402

# Default manifest — the IDIKA scanner-check packs (verify is read-only, so safe
# to run as-is). Replace/point --manifest at the testbook #146 packs for the real run.
DEFAULT_PACKS = [
    {"gtin": "05060917518062", "serial": "SN_IDIKA/1_0001", "batch": "IDIKA/1", "expiry": "301231"},
    {"gtin": "05060917518062", "serial": "SN_IDIKA/1_0002", "batch": "IDIKA/1", "expiry": "301231"},
    {"gtin": "05060917518062", "serial": "SN_IDIKA/1_0003", "batch": "IDIKA/1", "expiry": "301231"},
]


def _result_dict(r: object) -> dict:
    """Pull the fields we care about off HmvsResult, defensively."""
    keys = [
        "http_status",
        "ok",
        "state",
        "current_state",
        "operation_code",
        "nhrn",
        "is_intermarket",
        "information",
        "warning",
        "product_name",
        "batch_state",
        "alert_id",
        "queued",
        "retry_after_seconds",
    ]
    return {k: getattr(r, k, None) for k in keys}


async def _op(name: str, coro) -> dict:
    started = datetime.now(UTC).isoformat()
    try:
        r = await coro
        return {"op": name, "ts": started, "result": _result_dict(r)}
    except Exception as exc:  # noqa: BLE001 — log and continue the run
        return {"op": name, "ts": started, "error": f"{type(exc).__name__}: {exc}"}


async def main() -> int:
    p = argparse.ArgumentParser(description="IQE dry-run harness (verify by default)")
    p.add_argument("--manifest", help="JSON file: list of {gtin,serial,batch,expiry}")
    p.add_argument("--supply", action="store_true", help="STATE-CHANGING: supply each pack")
    p.add_argument(
        "--reactivate", action="store_true", help="STATE-CHANGING: reactivate after supply"
    )
    p.add_argument("--out", help="JSONL output path (default scripts/iqe_dryrun_<stamp>.jsonl)")
    args = p.parse_args()

    if is_mock_hmvs():
        print("[dryrun] ERROR: mock still on — refusing. Must hit live IQE.", file=sys.stderr)
        return 2
    s = get_settings()
    if not (s.hmvs_client_id and s.hmvs_client_secret):
        print("[dryrun] ERROR: HMVS_CLIENT_ID/SECRET unset.", file=sys.stderr)
        return 2

    packs = DEFAULT_PACKS
    if args.manifest:
        with open(args.manifest) as fh:
            packs = json.load(fh)

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = args.out or os.path.join(os.path.dirname(__file__), f"iqe_dryrun_{stamp}.jsonl")
    creds = {"client_id": s.hmvs_client_id, "client_secret": s.hmvs_client_secret}

    print(f"[dryrun] live={not is_mock_hmvs()}  verify_url={s.hmvs_verification_url}")
    print(f"[dryrun] packs={len(packs)}  supply={args.supply}  reactivate={args.reactivate}")
    print(f"[dryrun] log → {out_path}")

    lines: list[dict] = []
    for pk in packs:
        key = (pk["gtin"], pk["serial"], pk["batch"], pk["expiry"])
        label = f"{pk['gtin']}/{pk['serial']}"

        rec = await _op("verify", hmvs.verify(*key, **creds))
        rec["pack"] = label
        lines.append(rec)
        res = rec.get("result", {})
        print(
            f"  verify {label} → http={res.get('http_status')} ok={res.get('ok')} "
            f"state={res.get('state')} op={res.get('operation_code')} nhrn={res.get('nhrn')}"
        )

        if args.supply:
            rec = await _op("supply", hmvs.change_state(*key, target_state="Supplied", **creds))
            rec["pack"] = label
            lines.append(rec)
            print(f"  supply {label} → {rec.get('result', rec.get('error'))}")

        if args.reactivate:
            rec = await _op("reactivate", hmvs.change_state(*key, target_state="Active", **creds))
            rec["pack"] = label
            lines.append(rec)
            print(f"  reactivate {label} → {rec.get('result', rec.get('error'))}")

    with open(out_path, "w") as fh:
        for ln in lines:
            fh.write(json.dumps(ln, default=str) + "\n")
    print(f"[dryrun] wrote {len(lines)} records to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
