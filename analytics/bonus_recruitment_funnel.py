"""Bonus: recruitment funnel from staging.applications (conversion between stages, median days in each stage).

Run alone: python -m analytics.bonus_recruitment_funnel
"""
import logging
import sys
from pathlib import Path

import pandas as pd

from db import get_engine

log = logging.getLogger("pipeline")
RESULTS = Path(__file__).resolve().parent / "results"
FUNNEL = ["Applied", "Screened", "Interviewed", "Offered", "Hired"]
EXITS = ["Rejected", "Offer Declined"]
ORDER = {s: i for i, s in enumerate(FUNNEL + EXITS)}


def run() -> pd.DataFrame:
    RESULTS.mkdir(exist_ok=True)
    df = pd.read_sql("SELECT application_id, dept_id, stage, stage_date FROM staging.applications", get_engine())
    df["stage_date"] = pd.to_datetime(df["stage_date"])
    df["ord"] = df["stage"].map(ORDER)
    df = df.sort_values(["application_id", "stage_date", "ord"]).reset_index(drop=True)
    df["next_date"] = df.groupby("application_id")["stage_date"].shift(-1)
    df["days_in_stage"] = (df["next_date"] - df["stage_date"]).dt.days

    total = df.loc[df.stage == "Applied", "application_id"].nunique()
    rows, prev = [], None
    for stage in FUNNEL + EXITS:
        s = df[df.stage == stage]
        reached = s["application_id"].nunique()
        rows.append({
            "stage": stage,
            "kind": "funnel" if stage in FUNNEL else "exit",
            "applications_reached": reached,
            "conversion_from_previous_pct": None if prev is None or stage in EXITS else round(100 * reached / prev, 1),
            "conversion_from_applied_pct": round(100 * reached / total, 1),
            "median_days_in_stage": s["days_in_stage"].median(),
            "applications_with_next_event": int(s["days_in_stage"].notna().sum()),
        })
        if stage in FUNNEL:
            prev = reached
    funnel = pd.DataFrame(rows)
    funnel.to_csv(RESULTS / "bonus_recruitment_funnel.csv", index=False)

    dept = (df.groupby("dept_id").apply(lambda g: pd.Series({
        "applications": g.loc[g.stage == "Applied", "application_id"].nunique(),
        "interviewed": g.loc[g.stage == "Interviewed", "application_id"].nunique(),
        "offered": g.loc[g.stage == "Offered", "application_id"].nunique(),
        "hired": g.loc[g.stage == "Hired", "application_id"].nunique()}), include_groups=False).reset_index())
    dept["applied_to_hired_pct"] = (100 * dept["hired"] / dept["applications"]).round(1)
    dept = dept.merge(pd.read_sql("SELECT dept_id, dept_name, plant FROM staging.departments", get_engine()), on="dept_id", how="left")
    dept.to_csv(RESULTS / "bonus_funnel_by_department.csv", index=False)
    log.info("bonus recruitment funnel: %d applications, %d hired -> analytics/results/bonus_*.csv", total, int(funnel.loc[funnel.stage == "Hired", "applications_reached"].iloc[0]))
    return funnel


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stdout)
    print(run().to_string(index=False))
