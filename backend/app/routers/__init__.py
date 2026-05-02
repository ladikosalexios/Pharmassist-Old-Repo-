"""HTTP routers, one per domain.

Each module exports a ``router`` (an ``APIRouter`` instance). main.py imports
each module and calls ``app.include_router(<module>.router)``.
"""
