"""Rebuild the whole pipeline from the raw files with one command.

    python run_pipeline.py
    python run_pipeline.py --from staging
    python run_pipeline.py --only analytics
"""
import argparse
import logging
import sys
import time
import uuid
from pathlib import Path

import config
from db import ensure_database, run_sql_file

log = logging.getLogger("pipeline")
ROOT = Path(__file__).resolve().parent
STAGES = ["raw", "staging", "warehouse", "analytics", "bonus"]


def stage_raw(run_id):
    from ingestion import load_raw
    from quality import dq_checks
    if not load_raw.run():
        raise RuntimeError("raw load: a file's row count does not match its table")
    return dq_checks.run(["raw"], run_id)


def stage_staging(run_id):
    from quality import dq_checks
    from transform import clock_drift
    run_sql_file(ROOT / "transform" / "10_staging_masters.sql")
    clock_drift.run()
    for name in ["20_staging_punches.sql", "30_staging_leave_ot_pay.sql", "40_attendance_daily.sql"]:
        run_sql_file(ROOT / "transform" / name)
    return dq_checks.run(["staging"], run_id)


def stage_warehouse(run_id):
    from quality import dq_checks
    for f in ["ddl/01_dimensions.sql", "ddl/02_facts.sql", "load_warehouse.sql", "ddl/03_views.sql"]:
        run_sql_file(ROOT / "warehouse" / f)
    return dq_checks.run(["warehouse"], run_id)


def stage_analytics(run_id):
    from analytics import run_analytics
    run_analytics.run()


def stage_bonus(run_id):
    from analytics import bonus_recruitment_funnel
    bonus_recruitment_funnel.run()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="start", choices=STAGES, default="raw", help="first stage to run")
    ap.add_argument("--only", choices=STAGES, help="run just one stage")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stdout)
    stages = [args.only] if args.only else STAGES[STAGES.index(args.start):]
    run_id = uuid.uuid4().hex[:12]
    log.info("pipeline run %s on %s / %s, data from %s", run_id, config.SQL_SERVER, config.DATABASE, config.DATA_DIR)
    ensure_database()

    failed_checks = 0
    t_all = time.time()
    for name in stages:
        t0 = time.time()
        result = globals()[f"stage_{name}"](run_id)
        if isinstance(result, tuple):
            failed_checks += result[1]
        log.info("== %s done in %.0fs", name, time.time() - t0)
    log.info("pipeline finished in %.0fs - %s", time.time() - t_all,
             "all data quality checks passed" if not failed_checks else f"{failed_checks} DATA QUALITY CHECK(S) FAILED")
    return 1 if failed_checks else 0


if __name__ == "__main__":
    sys.exit(main())
