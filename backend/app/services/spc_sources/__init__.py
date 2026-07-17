"""SPC document source adapters (ΕΟΦ portal, EMA).

Contract: adapters NEVER raise — ``resolve`` returns an :class:`AdapterResult`
whose ``error`` string lands in ``spc_fetch_state.last_error`` when empty-
handed. Automated fetching is best-effort by design; the admin upload path
is the guaranteed backbone.
"""

from .base import AdapterResult, FoundDoc, download  # noqa: F401
