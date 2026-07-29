import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Falls back to local SQLite for dev; production sets DATABASE_URL (Postgres).
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./bookshelf.db")

# Providers (Neon, Render, Heroku-style) commonly hand out "postgres://" or
# bare "postgresql://" URLs, but SQLAlchemy needs an explicit driver in the
# scheme to use psycopg (v3) instead of defaulting to psycopg2, which isn't
# installed here. Rewrite defensively rather than trusting the given scheme.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
