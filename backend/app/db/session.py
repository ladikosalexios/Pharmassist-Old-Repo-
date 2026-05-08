from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from ..config import get_settings

settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True, pool_size=10, max_overflow=20)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
