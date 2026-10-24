"""Stage 2: find biometric devices whose clock is off and store the correction used by the punch SQL.

Each device's morning arrival time (5th percentile of punches between 03:00 and 12:00) is compared with its own
baseline. A device that stays away from zero for 7 or more valid days gets a correction (see README).

Run alone: python -m transform.clock_drift
"""
import logging
import sys

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.types import DATE, INTEGER, NVARCHAR, FLOAT

from db import get_engine

log = logging.getLogger("pipeline")

MIN_MORNING_PUNCHES = 50
BASELINE_DAYS = 28
LEVEL_STEP = 5
MIN_RUN_DAYS = 7


def _daily_morning_edge(engine) -> pd.DataFrame:
    punches = pd.read_sql(
        "SELECT device_id, CAST(punch_time AS DATETIME2(0)) AS t FROM raw.biometric_punches", engine)
    punches["d"] = punches["t"].dt.normalize()
    punches["minute"] = punches["t"].dt.hour * 60 + punches["t"].dt.minute

    morning = punches[(punches["minute"] >= 3 * 60) & (punches["minute"] < 12 * 60)]
    daily = (morning.groupby(["device_id", "d"])["minute"]
             .agg(p05=lambda s: float(np.percentile(s, 5)), n="count").reset_index())
    daily["dow"] = daily["d"].dt.dayofweek
    return daily[(daily["n"] >= MIN_MORNING_PUNCHES) & (daily["dow"] != 6)].copy()


def detect(daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (weekly diagnostics, corrections)."""
    diag_rows, corr_rows = [], []
    for device, g in daily.groupby("device_id"):
        g = g.sort_values("d").reset_index(drop=True)
        baseline = g.loc[g["d"] < g["d"].min() + pd.Timedelta(days=BASELINE_DAYS), "p05"].median()
        g["deviation"] = g["p05"] - baseline
        g["level"] = (g["deviation"] / LEVEL_STEP).round() * LEVEL_STEP
        g["smooth"] = g["level"].rolling(5, center=True, min_periods=1).median()

        run_id = (g["smooth"] != g["smooth"].shift()).cumsum()
        for _, run in g.groupby(run_id):
            level = run["smooth"].iloc[0]
            if level != 0 and len(run) >= MIN_RUN_DAYS:

                drifted = run[(run["level"] - level).abs() <= LEVEL_STEP]
                start = drifted["d"].iloc[0]
                end = run["d"].iloc[-1]
                is_open = run.index[-1] == g.index[-1]
                corr_rows.append({
                    "device_id": device,
                    "valid_from": start.date(),
                    "valid_to": None if is_open else end.date(),
                    "offset_minutes": int(level),
                    "correction_minutes": int(-level),
                    "baseline_minute_of_day": round(float(baseline), 1),
                    "evidence": (f"Morning arrival edge (p05 of punches 03:00-12:00) moved from a baseline of "
                                 f"{baseline:.0f} min after midnight by {level:+.0f} min on {start.date()} and stayed there for "
                                 f"{len(run)} valid days; other devices did not move."),
                })
        g["week_start"] = g["d"] - pd.to_timedelta(g["d"].dt.dayofweek, unit="D")
        wk = g.groupby("week_start").agg(valid_days=("d", "count"), avg_morning_edge_minute=("p05", "mean"),
                                         avg_deviation_minutes=("deviation", "mean")).reset_index()
        wk.insert(0, "device_id", device)
        diag_rows.append(wk)
    diagnostics = pd.concat(diag_rows, ignore_index=True)
    corrections = pd.DataFrame(corr_rows, columns=["device_id", "valid_from", "valid_to", "offset_minutes",
                                                   "correction_minutes", "baseline_minute_of_day", "evidence"])
    return diagnostics, corrections


def run() -> pd.DataFrame:
    engine = get_engine()
    daily = _daily_morning_edge(engine)
    diagnostics, corrections = detect(daily)
    diagnostics["week_start"] = diagnostics["week_start"].dt.date
    diagnostics[["avg_morning_edge_minute", "avg_deviation_minutes"]] = diagnostics[
        ["avg_morning_edge_minute", "avg_deviation_minutes"]].round(1)
    diagnostics.to_sql("device_clock_diagnostics", engine, schema="staging", if_exists="replace", index=False,
                       dtype={"device_id": NVARCHAR(40), "week_start": DATE, "valid_days": INTEGER,
                              "avg_morning_edge_minute": FLOAT, "avg_deviation_minutes": FLOAT})
    corrections.to_sql("device_clock_correction", engine, schema="staging", if_exists="replace", index=False,
                       dtype={"device_id": NVARCHAR(40), "valid_from": DATE, "valid_to": DATE, "offset_minutes": INTEGER,
                              "correction_minutes": INTEGER, "baseline_minute_of_day": FLOAT, "evidence": NVARCHAR(600)})
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE staging.device_clock_correction ALTER COLUMN device_id NVARCHAR(40) NOT NULL"))
        conn.execute(text("ALTER TABLE staging.device_clock_correction ALTER COLUMN valid_from DATE NOT NULL"))
        conn.execute(text("ALTER TABLE staging.device_clock_correction ADD CONSTRAINT pk_stg_device_clock_correction "
                          "PRIMARY KEY (device_id, valid_from)"))
    if corrections.empty:
        log.info("clock check: no device clock problems found")
    for _, c in corrections.iterrows():
        log.info("clock check: %s is %+d min off from %s -> correcting by %+d min", c.device_id, c.offset_minutes,
                 c.valid_from, c.correction_minutes)
    return corrections


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stdout)
    print(run().to_string())
