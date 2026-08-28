from urllib.parse import urlparse, urlencode, parse_qsl, urlunparse

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from config import DATABASE_URL, DB_SSL

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

def _strip_non_asyncpg_params(url: str) -> str:
    parts = urlparse(url)
    keep = [q for q in parse_qsl(parts.query) if q[0] not in ("sslmode", "channel_binding")]
    query = urlencode(keep)
    return urlunparse((parts.scheme, parts.netloc, parts.path, parts.params, query, parts.fragment))

DATABASE_URL = _strip_non_asyncpg_params(DATABASE_URL)

_ssl_arg = "require" if DB_SSL == "require" else None

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    connect_args={"ssl": _ssl_arg} if _ssl_arg else {},
)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with SessionLocal() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)