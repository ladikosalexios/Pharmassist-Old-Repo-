import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.config import get_settings
from app.db.base import Base
from app.db.models.adr_event import AdrEvent  # noqa
from app.db.models.adr_report import AdrReport  # noqa
from app.db.models.audit_log import AuditLog  # noqa
from app.db.models.dispense_log import DispenseLog  # noqa
from app.db.models.documentation_log import DocumentationLog  # noqa
from app.db.models.drug_catalog import DrugCatalog  # noqa
from app.db.models.hmvs_operation import HmvsOperation  # noqa
from app.db.models.invitation import Invitation  # noqa
from app.db.models.patient_condition import PatientCondition  # noqa
from app.db.models.pharmacist import Pharmacist  # noqa
from app.db.models.pharmacist_pharmacy import PharmacistPharmacy  # noqa
from app.db.models.pharmacy import Pharmacy  # noqa
from app.db.models.safety_rule import SafetyRule  # noqa

config = context.config
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online():
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
