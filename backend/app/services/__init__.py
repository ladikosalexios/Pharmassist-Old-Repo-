"""In-memory stores + business logic.

Each module owns one domain's mock data and the helpers that read or mutate
it. Routes import from these modules; modules don't import anything from
FastAPI's routing layer (they may raise HTTPException, which is fine since
that's part of the FastAPI request/response contract, not the routing layer).

When the mocks are eventually swapped for a real database, only these files
need to change — the routers continue to call the same function signatures.
"""
