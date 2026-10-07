"""Backend subprocess bootstrap: suppress dotenv before importing application code."""

import asyncio
import sys
from pathlib import Path


async def test_fixtures():
    # Reuse only the catalog/rule data required by existing DB assertions.
    # seed_data is a constants-only module; never import or invoke scripts.seed.
    from sqlalchemy import insert

    from app.db.models.drug_catalog import DrugCatalog
    from app.db.models.safety_rule import SafetyRule
    from app.db.session import engine
    from scripts.seed_data import DRUG_CATALOG_DATA, SAFETY_RULES_DATA

    drug = next(row for row in DRUG_CATALOG_DATA if row["gns_code"] == "3661001")
    rule = next(
        row
        for row in SAFETY_RULES_DATA
        if row["rule_code"] == "WARFARIN_PREGNANCY_CONTRAINDICATION"
    )
    try:
        async with engine.begin() as connection:
            await connection.execute(insert(DrugCatalog), [drug])
            await connection.execute(insert(SafetyRule), [rule])
    finally:
        await engine.dispose()


def main():
    # Environment is supplied by verify.py. Do not let app.config or a CLI pull
    # credentials/URLs from a developer's .env, even with older python-dotenv.
    import dotenv
    import dotenv.main

    dotenv.load_dotenv = lambda *args, **kwargs: False
    dotenv.main.load_dotenv = dotenv.load_dotenv
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    action, *arguments = sys.argv[1:]
    if action == "fixtures":
        asyncio.run(test_fixtures())
        return 0
    if action == "pytest":
        import pytest

        return pytest.main(arguments)
    if action == "alembic":
        from alembic.config import main as alembic_main

        alembic_main(argv=arguments)
        return 0
    raise ValueError(f"Unsupported verification action: {action}")


if __name__ == "__main__":
    sys.exit(main())
