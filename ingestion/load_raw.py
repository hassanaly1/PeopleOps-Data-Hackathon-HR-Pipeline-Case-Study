"""Stage 1: load the raw exports into the raw schema as delivered.

All columns are text, plus _source_file, _loaded_at and _row_hash. Rows already loaded are skipped, so a re-run adds
nothing. Row counts per file and per table are logged and compared.

Run alone: python -m ingestion.load_raw
"""
import csv
import hashlib
import json
import logging
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.types import NVARCHAR

import config
from db import ensure_database, get_engine

log = logging.getLogger("pipeline")

SCHEMAS = ["raw", "staging", "warehouse", "dq"]
TEXT_LEN = 400


def ensure_schemas(engine) -> None:
    with engine.begin() as conn:
        for s in SCHEMAS:
            conn.execute(text(f"IF SCHEMA_ID(N'{s}') IS NULL EXEC('CREATE SCHEMA [{s}]')"))
        conn.execute(text("""
            IF OBJECT_ID(N'raw.load_log') IS NULL
            CREATE TABLE raw.load_log (
                log_id INT IDENTITY(1,1) PRIMARY KEY,
                logged_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
                source_file NVARCHAR(100) NOT NULL,
                table_name NVARCHAR(100) NOT NULL,
                rows_in_file INT NOT NULL,
                rows_inserted INT NOT NULL,
                rows_in_table INT NOT NULL,
                status NVARCHAR(10) NOT NULL)"""))


def row_hashes(df: pd.DataFrame) -> pd.Series:
    """SHA-256 of the row's text values (unit-separator joined)."""
    joined = df.astype(str).agg("\x1f".join, axis=1)
    return joined.map(lambda s: hashlib.sha256(s.encode("utf-8")).hexdigest())


def _prepare(df: pd.DataFrame, source_file: str) -> pd.DataFrame:
    df = df.copy()
    df["_row_hash"] = row_hashes(df)
    df["_dup_seq"] = df.groupby("_row_hash").cumcount() + 1
    df["_source_file"] = source_file
    return df


def _count_csv_records(path: Path) -> int:
    """Independent record count (does not use pandas) for the file-vs-table check."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        return sum(1 for _ in csv.reader(f)) - 1


def _load_dataframe(engine, df: pd.DataFrame, table: str, source_file: str, data_cols: list[str],
                    col_types: dict[str, str]) -> int:
    """Create raw.<table> if needed and insert the rows that are not already present. Returns rows inserted."""
    col_ddl = ",\n  ".join(f"[{c}] {col_types[c]} NULL" for c in data_cols)
    with engine.begin() as conn:
        conn.execute(text(f"""
            IF OBJECT_ID(N'raw.{table}') IS NULL
            CREATE TABLE raw.[{table}] (
              _row_id INT IDENTITY(1,1) NOT NULL,
              {col_ddl},
              _source_file NVARCHAR(100) NOT NULL,
              _loaded_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
              _row_hash CHAR(64) NOT NULL,
              _dup_seq INT NOT NULL,
              CONSTRAINT [pk_raw_{table}] PRIMARY KEY (_row_id),
              CONSTRAINT [uq_raw_{table}_row] UNIQUE (_source_file, _row_hash, _dup_seq))"""))

    scratch = f"_incoming_{table}"
    sa_types = {c: NVARCHAR(None if col_types[c] == "NVARCHAR(MAX)" else TEXT_LEN) for c in data_cols}
    sa_types.update({"_source_file": NVARCHAR(100), "_row_hash": NVARCHAR(64)})
    df.to_sql(scratch, engine, schema="raw", if_exists="replace", index=False, dtype=sa_types, chunksize=5000)

    cols = ", ".join(f"[{c}]" for c in data_cols)
    scols = ", ".join(f"s.[{c}]" for c in data_cols)
    with engine.begin() as conn:
        res = conn.execute(text(f"""
            INSERT INTO raw.[{table}] ({cols}, _source_file, _row_hash, _dup_seq)
            SELECT {scols}, s._source_file, s._row_hash, s._dup_seq
            FROM raw.[{scratch}] s
            WHERE NOT EXISTS (SELECT 1 FROM raw.[{table}] t
                              WHERE t._source_file = s._source_file AND t._row_hash = s._row_hash AND t._dup_seq = s._dup_seq)"""))
        inserted = res.rowcount
        conn.execute(text(f"DROP TABLE raw.[{scratch}]"))
    return inserted


def _log(engine, source_file: str, table: str, rows_in_file: int, inserted: int) -> bool:
    with engine.begin() as conn:
        in_table = conn.execute(text(f"SELECT COUNT(*) FROM raw.[{table}] WHERE _source_file = :f"),
                                {"f": source_file}).scalar()
        ok = in_table == rows_in_file
        conn.execute(text("""INSERT INTO raw.load_log (source_file, table_name, rows_in_file, rows_inserted, rows_in_table, status)
                             VALUES (:f, :t, :a, :b, :c, :s)"""),
                     {"f": source_file, "t": table, "a": rows_in_file, "b": inserted, "c": in_table, "s": "MATCH" if ok else "MISMATCH"})
    log.info("raw.%-18s file=%-24s rows_in_file=%7d inserted=%7d rows_in_table=%7d  %s",
             table, source_file, rows_in_file, inserted, in_table, "OK" if ok else "MISMATCH")
    return ok


def load_csv(engine, filename: str, table: str) -> bool:
    path = config.DATA_DIR / filename
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False, encoding="utf-8-sig")
    rows_in_file = _count_csv_records(path)
    if len(df) != rows_in_file:
        raise RuntimeError(f"{filename}: pandas read {len(df)} rows but the file has {rows_in_file}")
    data_cols = list(df.columns)
    df = _prepare(df, filename)
    inserted = _load_dataframe(engine, df, table, filename, data_cols, {c: f"NVARCHAR({TEXT_LEN})" for c in data_cols})
    return _log(engine, filename, table, rows_in_file, inserted)


def load_json(engine, filename: str, table: str, array_path: str | None) -> bool:
    path = config.DATA_DIR / filename
    doc = json.loads(path.read_text(encoding="utf-8-sig"))
    records = doc[array_path.split(".")[1]] if array_path else doc
    df = pd.DataFrame({"record_json": [json.dumps(r, ensure_ascii=False) for r in records]})
    rows_in_file = len(records)
    df = _prepare(df, filename)
    inserted = _load_dataframe(engine, df, table, filename, ["record_json"], {"record_json": "NVARCHAR(MAX)"})
    return _log(engine, filename, table, rows_in_file, inserted)


def run() -> bool:
    ensure_database()
    engine = get_engine()
    ensure_schemas(engine)
    ok = True
    for filename, table in config.CSV_FILES.items():
        ok &= load_csv(engine, filename, table)
    for filename, (table, array_path) in config.JSON_FILES.items():
        ok &= load_json(engine, filename, table, array_path)
    log.info("raw load %s", "complete - every file matches its table" if ok else "FINISHED WITH MISMATCHES")
    return ok


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stdout)
    sys.exit(0 if run() else 1)
