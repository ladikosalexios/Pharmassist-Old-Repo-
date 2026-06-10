"""Export a v1-only OpenAPI artifact + a static Redoc page (FT-12).

`/openapi.json` mixes the whole B2C surface with /v1; an integrator needs the
B2B surface alone. This script takes `app.openapi()`, keeps only the B2B paths
(`/v1*` plus the unauthenticated `/health/v1` liveness probe), prunes the
component schemas down to what those paths transitively reference, adds the
`X-API-Key` security scheme, and writes:

    docs/b2b-core/openapi-v1.json   — the filtered spec
    docs/b2b-core/api-reference.html — standalone Redoc (spec inlined, opens offline)

Run inside the backend container (or backend/ with the venv):

    python -m scripts.export_openapi_v1

Re-run whenever the /v1 surface changes; commit both outputs. It imports the
app, so it sets mock-mode env defaults at the top — no real secrets needed.
"""

import json
import os
import re
import sys

# Import-time env: create_app() → get_settings() fails fast without these.
# Mock mode keeps the import side-effect-free (no upstream calls).
os.environ.setdefault("ENV", "test")
os.environ.setdefault("PHARMAPI_MOCK", "true")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("SECRET_KEY", "export-openapi-dummy")
os.environ.setdefault("PHARMAPI_USERNAME", "x")
os.environ.setdefault("PHARMAPI_PASSWORD", "x")
os.environ.setdefault("PHARMAPI_API_KEY", "x")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://pharmassist:pharmassist_dev@localhost:5432/pharmassist"
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import create_app  # noqa: E402

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
# Defaults to docs/b2b-core on a full checkout. Override with OPENAPI_OUT_DIR
# when running in the backend container (which mounts only backend/, so the
# repo's docs/ tree isn't present) — write into the mount, then move the two
# files into docs/b2b-core.
_OUT_DIR = os.getenv("OPENAPI_OUT_DIR") or os.path.join(_REPO_ROOT, "docs", "b2b-core")
os.makedirs(_OUT_DIR, exist_ok=True)
_JSON_OUT = os.path.join(_OUT_DIR, "openapi-v1.json")
_HTML_OUT = os.path.join(_OUT_DIR, "api-reference.html")


def _is_b2b_path(path: str) -> bool:
    # The integrator-facing surface: the /v1 tree + the keyless liveness probe.
    return path.startswith("/v1") or path == "/health/v1"


def _collect_refs(node: object, found: set[str]) -> None:
    """Walk an arbitrary JSON node, collecting every $ref'd schema name."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                m = re.match(r"#/components/schemas/(.+)", value)
                if m:
                    found.add(m.group(1))
            else:
                _collect_refs(value, found)
    elif isinstance(node, list):
        for item in node:
            _collect_refs(item, found)


def _transitive_schemas(paths: dict, all_schemas: dict) -> dict:
    """Closure of schemas reachable from the kept paths."""
    seen: set[str] = set()
    frontier: set[str] = set()
    _collect_refs(paths, frontier)
    while frontier:
        name = frontier.pop()
        if name in seen or name not in all_schemas:
            continue
        seen.add(name)
        nested: set[str] = set()
        _collect_refs(all_schemas[name], nested)
        frontier |= nested - seen
    return {name: all_schemas[name] for name in sorted(seen)}


def build_spec() -> dict:
    app = create_app()
    full = app.openapi()

    paths = {p: item for p, item in full.get("paths", {}).items() if _is_b2b_path(p)}
    if not paths:
        sys.exit("[export-openapi-v1] no /v1 paths found — did the surface move?")

    all_schemas = full.get("components", {}).get("schemas", {})
    kept_schemas = _transitive_schemas(paths, all_schemas)

    # X-API-Key scheme; applied globally, with the keyless probe opting out.
    security_schemes = {
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": (
                "Per-location bearer key (`pa_live_…` / `pa_test_…`). TLS only. "
                "All failure modes return one indistinguishable 401."
            ),
        }
    }
    for path, item in paths.items():
        if path == "/health/v1":
            for method in ("get", "post", "patch", "delete", "put"):
                if method in item:
                    item[method]["security"] = []  # unauthenticated liveness probe

    return {
        "openapi": full.get("openapi", "3.1.0"),
        "info": {
            "title": "PharmAssist B2B Core API (/v1)",
            "version": full.get("info", {}).get("version", "0.1.0"),
            "description": (
                "Tier-1 Core surface for integrators. Authenticate with the "
                "`X-API-Key` header over TLS. Errors render in the stable "
                '`{"error": {code, message, request_id}}` envelope. See '
                "docs/b2b-core/API.md for the narrative (auth, error codes, "
                "consent attestation, the 609/ΕΟΠΥΥ rule, rate limits, "
                "tri-state coverage, pagination, sandbox identifiers)."
            ),
        },
        "servers": [{"url": "https://api.<your-domain>", "description": "Live (FT-10, TBD)"}],
        "security": [{"ApiKeyAuth": []}],
        "paths": paths,
        "components": {"schemas": kept_schemas, "securitySchemes": security_schemes},
    }


_REDOC_HTML = """<!doctype html>
<html>
  <head>
    <title>PharmAssist B2B Core API (/v1)</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>body {{ margin: 0; padding: 0; }}</style>
  </head>
  <body>
    <div id="redoc"></div>
    <script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>
    <script>
      // Spec inlined so this file opens offline (double-click) with no CORS
      // fetch. Regenerate with: python -m scripts.export_openapi_v1
      var spec = {spec_json};
      Redoc.init(spec, {{ hideDownloadButton: false }}, document.getElementById('redoc'));
    </script>
  </body>
</html>
"""


def main() -> None:
    spec = build_spec()
    with open(_JSON_OUT, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    html = _REDOC_HTML.format(spec_json=json.dumps(spec, ensure_ascii=False))
    with open(_HTML_OUT, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(
        f"[export-openapi-v1] wrote {os.path.relpath(_JSON_OUT, _REPO_ROOT)} "
        f"({len(spec['paths'])} paths, {len(spec['components']['schemas'])} schemas)"
    )
    print(f"[export-openapi-v1] wrote {os.path.relpath(_HTML_OUT, _REPO_ROOT)}")


if __name__ == "__main__":
    main()
