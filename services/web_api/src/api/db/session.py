import os
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# Resolve database URL from environment or default to local SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./interview.db")

# SQLite needs check_same_thread=False for multithreaded web servers
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI route dependency yielding a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Python context manager for background workers, tools, and scripts."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Creates all database tables defined in models and applies non-destructive migrations."""
    Base.metadata.create_all(bind=engine)

    # Safe SQLite column migration for credential_vault if upgraded from previous schema
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            # Check existing columns in credential_vault
            result = conn.execute(text("PRAGMA table_info(credential_vault)")).fetchall()
            existing_cols = {row[1] for row in result}
            if existing_cols:
                if "category" not in existing_cols:
                    conn.execute(text("ALTER TABLE credential_vault ADD COLUMN category VARCHAR(50) DEFAULT 'thinking' NOT NULL"))
                if "model_name" not in existing_cols:
                    conn.execute(text("ALTER TABLE credential_vault ADD COLUMN model_name VARCHAR(120)"))
                if "base_url" not in existing_cols:
                    conn.execute(text("ALTER TABLE credential_vault ADD COLUMN base_url VARCHAR(255)"))
                if "voice" not in existing_cols:
                    conn.execute(text("ALTER TABLE credential_vault ADD COLUMN voice VARCHAR(50)"))
                if "updated_at" not in existing_cols:
                    conn.execute(text("ALTER TABLE credential_vault ADD COLUMN updated_at DATETIME"))
                conn.commit()
    except Exception:
        pass
