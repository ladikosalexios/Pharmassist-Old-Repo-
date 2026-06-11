"""Guard: no Tier-1 / deterministic module imports the LLM seam (T2-2 AC).

The whole point of the seam is that AI is additive — the deterministic surfaces
(safety check, formulary, ADR CRUD, the whole B2C app) must keep working when the
LLM is down or unconfigured, which is only true if they never pull it in. This
scans every module under app/ and asserts that the only importers of
``services/llm.py`` / ``services/ai_cache.py`` are the seam itself and the small,
documented allowlist below.

A safety net, not a parser: it greps source text for the seam's import shapes,
so a marker inside a comment or string trips it too. Deliberate — a false
positive fails toward a human look (add the file to the allowlist or reword the
comment), which is the safe direction for an architectural guard. When an AI
feature lands (T2-5/6/7/9/10) its endpoint module adds itself to
``ALLOWED_IMPORTERS`` — that edit is the visible record that a new caller of the
seam was reviewed.
"""

import os
from pathlib import Path

os.environ.setdefault("ENV", "test")

APP_ROOT = Path(__file__).resolve().parent.parent / "app"

# The seam's own files — excluded from the scan (ai_cache is imported by llm).
SEAM_FILES = {"services/llm.py", "services/ai_cache.py"}

# Modules permitted to reference the seam. errors.py only enveloping-translates
# AiUnavailableError → the ai_unavailable code; it does not call the seam. AI
# endpoint modules append themselves here as they ship.
ALLOWED_IMPORTERS = {"routers/v1/errors.py"}

# Import shapes that mean "this module pulls in the seam".
_SEAM_IMPORT_MARKERS = (
    "services.llm",
    "services.ai_cache",
    "from .llm import",
    "from .ai_cache import",
    "import llm",
    "import ai_cache",
)


def _rel(path: Path) -> str:
    return path.relative_to(APP_ROOT).as_posix()


def test_no_deterministic_module_imports_the_seam():
    offenders = []
    for path in APP_ROOT.rglob("*.py"):
        rel = _rel(path)
        if rel in SEAM_FILES or rel in ALLOWED_IMPORTERS:
            continue
        source = path.read_text(encoding="utf-8")
        if any(marker in source for marker in _SEAM_IMPORT_MARKERS):
            offenders.append(rel)
    assert offenders == [], (
        "These deterministic modules import the LLM seam — AI must stay additive. "
        f"If a new AI endpoint legitimately uses it, add it to ALLOWED_IMPORTERS: {offenders}"
    )


def test_allowlist_entries_actually_reference_the_seam():
    # Keep the allowlist honest: an entry that no longer touches the seam should
    # be removed, so the list always reflects real, reviewed callers.
    for rel in ALLOWED_IMPORTERS:
        source = (APP_ROOT / rel).read_text(encoding="utf-8")
        assert any(marker in source for marker in _SEAM_IMPORT_MARKERS), (
            f"{rel} is allowlisted but no longer references the seam — drop it"
        )
