"""Database helpers: engine creation, database bootstrap and a runner for .sql scripts."""
import logging
import re
import urllib.parse
from pathlib import Path

import pyodbc
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

import config

log = logging.getLogger("pipeline")


def _odbc_string(database: str) -> str:
    parts = [
        f"DRIVER={{{config.ODBC_DRIVER}}}",
        f"SERVER={config.SQL_SERVER}",
        f"DATABASE={database}",
        "TrustServerCertificate=yes",
    ]
    if config.SQL_USER:
        parts += [f"UID={config.SQL_USER}", f"PWD={config.SQL_PASSWORD}"]
    else:
        parts.append("Trusted_Connection=yes")
    return ";".join(parts)


def get_engine(database: str | None = None) -> Engine:
    odbc = urllib.parse.quote_plus(_odbc_string(database or config.DATABASE))
    return create_engine(f"mssql+pyodbc:///?odbc_connect={odbc}", fast_executemany=True)


def ensure_database() -> None:
    """Create the pipeline database if it does not exist."""
    conn = pyodbc.connect(_odbc_string("master"), autocommit=True)
    try:
        conn.execute(f"IF DB_ID(N'{config.DATABASE}') IS NULL CREATE DATABASE [{config.DATABASE}]")
    finally:
        conn.close()


def split_batches(sql: str) -> list[str]:
    """Split a T-SQL script on lines that contain only GO."""
    batches = re.split(r"^\s*GO\s*$", sql, flags=re.IGNORECASE | re.MULTILINE)
    return [b.strip() for b in batches if b.strip()]


def run_sql_file(path: Path) -> None:
    """Execute a .sql script batch by batch and autocommit each batch."""
    sql = Path(path).read_text(encoding="utf-8")
    conn = pyodbc.connect(_odbc_string(config.DATABASE), autocommit=True)
    try:
        for i, batch in enumerate(split_batches(sql), start=1):
            try:
                cur = conn.cursor()
                cur.execute(batch)
                while cur.nextset():
                    pass
            except pyodbc.Error as exc:
                raise RuntimeError(f"{Path(path).name}: batch {i} failed: {exc}") from exc
        log.info("ran %s (%d batches)", Path(path).name, i)
    finally:
        conn.close()


def query_df(sql: str, **kwargs):
    import pandas as pd

    with get_engine().connect() as conn:
        return pd.read_sql(sql, conn, **kwargs)
