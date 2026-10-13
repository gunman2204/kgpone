from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from src.config.settings import Settings

import os
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOCAL_DB_PATH = os.path.join(BACKEND_DIR, "kgpone_offline.db")
LOCAL_DATABASE_URL = f"sqlite:///{LOCAL_DB_PATH}"

DATABASE_URL = Settings.DATABASE_URL

# Cloud Postgres Engine with fast connection timeout (prevents 300s offline hangs)
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {"connect_timeout": 4}
engine = create_engine(
    DATABASE_URL, 
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=3600
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Local SQLite Engine (Always Active for Dropzone and Offline Fallback)
local_engine = create_engine(
    LOCAL_DATABASE_URL,
    connect_args={"check_same_thread": False}
)
LocalSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=local_engine)

class Base(DeclarativeBase):
    pass

def init_local_db():
    """Ensure local offline tables exist in SQLite without circular import at module load."""
    import src.models
    Base.metadata.create_all(bind=local_engine)

def is_postgres_healthy() -> bool:
    """Fast non-blocking check to verify if Cloud Postgres is reachable."""
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_local_db():
    db = LocalSessionLocal()
    try:
        yield db
    finally:
        db.close()

