import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Postgres is required (not just supported) now that embeddings use
# pgvector's Vector column type, which SQLite has no equivalent for. Local
# dev defaults to the docker-compose Postgres service (see docker-compose.yml
# — run `docker compose up -d` before starting the app); production sets
# DATABASE_URL explicitly to the hosted instance.
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://bookshelf:bookshelf@localhost:5432/bookshelf"
)

# Providers (Neon, Render, Heroku-style) commonly hand out "postgres://" or
# bare "postgresql://" URLs, but SQLAlchemy needs an explicit driver in the
# scheme to use psycopg (v3) instead of defaulting to psycopg2, which isn't
# installed here. Rewrite defensively rather than trusting the given scheme.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
