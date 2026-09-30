import os
import sys
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_engine: Engine | None = None
SessionLocal: sessionmaker[Session] | None = None


def ensure_libpq() -> None:
    """Point the pure-Python psycopg client at a local PostgreSQL libpq on Windows.

    The binary wheel is blocked by Application Control on this machine, and an
    already-open terminal does not see a PATH change made after it started.
    """
    if sys.platform != "win32":
        return
    import ctypes.util

    if ctypes.util.find_library("libpq.dll"):
        return
    roots = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "PostgreSQL",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "PostgreSQL",
    ]
    candidates = [dll for root in roots if root.is_dir() for dll in root.glob("*/bin/libpq.dll")]
    candidates.sort(key=lambda dll: dll.parts[-3], reverse=True)
    if not candidates:
        return
    bin_dir = str(candidates[0].parent)
    os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(bin_dir)


def configure_engine() -> Engine:
    global _engine, SessionLocal
    settings = get_settings()
    if settings.database_url.startswith("postgresql"):
        ensure_libpq()
    connect_args = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    _engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
    SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        return configure_engine()
    return _engine


def get_session() -> Session:
    if SessionLocal is None:
        configure_engine()
    assert SessionLocal is not None
    return SessionLocal()


def get_db() -> Generator[Session, None, None]:
    db = get_session()
    try:
        yield db
    finally:
        db.close()


@event.listens_for(Engine, "connect")
def _sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    if dbapi_connection.__class__.__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
