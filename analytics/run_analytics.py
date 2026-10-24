"""Stage 5 - run every analytics/q*.sql against the warehouse and save each result as analytics/results/<query>.csv.

Run alone:  python -m analytics.run_analytics
"""
import logging
import sys
from pathlib import Path

import pandas as pd

from db import get_engine

log = logging.getLogger("pipeline")

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"


def run() -> dict[str, int]:
    RESULTS.mkdir(exist_ok=True)
    engine = get_engine()
    counts = {}
    with engine.connect() as conn:
        for sql_file in sorted(HERE.glob("q*.sql")):
            df = pd.read_sql(sql_file.read_text(encoding="utf-8"), conn)
            out = RESULTS / f"{sql_file.stem}.csv"
            df.to_csv(out, index=False, encoding="utf-8")
            counts[sql_file.stem] = len(df)
            log.info("%-42s %6d rows -> %s", sql_file.name, len(df), out.relative_to(HERE.parent))
    return counts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stdout)
    run()
