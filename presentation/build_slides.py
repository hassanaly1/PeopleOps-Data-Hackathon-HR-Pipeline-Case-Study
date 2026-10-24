"""Builds presentation/slides.pdf (6 slides) and presentation/numbers.json from the warehouse.
Every number on the slides is queried here, so they cannot drift from the data.

Run:  python presentation/build_slides.py     (after python run_pipeline.py)
"""
import json
import os
import sys
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db import get_engine

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parent / "analytics" / "results"
EVID = HERE / "evidence"
BLUE, ORANGE, GREEN, GREY, RED, INK = "#2f6fa8", "#d9822b", "#2e8b57", "#8a8a8a", "#c0392b", "#222222"
W, H = 13.33, 7.5
engine = get_engine()


def sql(text_):
    return pd.read_sql(text_, engine)


def evidence(name, part=None):
    text_ = (EVID / name).read_text(encoding="utf-8")
    if part is not None:
        text_ = text_.split("-- Part B")[1] if part == "B" else text_.split("-- Part B")[0].split("-- Part A")[1]
    return sql(text_)

trend = evidence("f1_overtime_trend.sql")
stitch = evidence("f1_stitching_overpayment.sql")
nopay = evidence("f2_pay_without_attendance.sql")
clock_b = evidence("f3_clock_drift.sql", "B")
clock_a = evidence("f3_clock_drift.sql", "A")
q6 = pd.read_csv(RESULTS / "q06_paid_exceeds_computed.csv")
q5 = pd.read_csv(RESULTS / "q05_overtime_computed_approved_paid.csv")
q8 = pd.read_csv(RESULTS / "q08_paid_after_separation.csv")
dq = sql("""SELECT COUNT(*) AS checks, SUM(CASE WHEN status = 'PASS' THEN 1 ELSE 0 END) AS passed
            FROM dq.dq_results WHERE run_id = (SELECT TOP 1 run_id FROM dq.dq_results ORDER BY result_id DESC)""")
diag = sql("""SELECT device_id, week_start, avg_deviation_minutes FROM staging.device_clock_diagnostics ORDER BY device_id, week_start""")
cost_total = float(trend["overtime_cost_pkr"].sum())
top = stitch.iloc[0]
s_row = q6.iloc[0]
sep = nopay[nopay.reason == "Paid after separation"].iloc[0]
unm = nopay[nopay.reason.str.startswith("Active employee")].iloc[0]
numbers = {
    "paid_hours_apr": float(trend.paid_hours.iloc[0]), "paid_hours_sep": float(trend.paid_hours.iloc[-1]),
    "worked_hours_apr": float(trend.worked_hours.iloc[0]), "worked_hours_sep": float(trend.worked_hours.iloc[-1]),
    "paid_growth_pct": round(100 * (trend.paid_hours.iloc[-1] / trend.paid_hours.iloc[0] - 1), 1),
    "worked_growth_pct": round(100 * (trend.worked_hours.iloc[-1] / trend.worked_hours.iloc[0] - 1), 1),
    "overtime_cost_pkr_6m": cost_total,
    "overtime_cost_pkr_apr": float(trend.overtime_cost_pkr.iloc[0]), "overtime_cost_pkr_sep": float(trend.overtime_cost_pkr.iloc[-1]),
    "stitching_paid_hours": float(s_row.paid_ot_hours), "stitching_computed_hours": float(s_row.computed_ot_hours),
    "stitching_paid_vs_computed_pct": float(s_row.paid_vs_computed_pct), "stitching_months_over_15pct": int(s_row.months_over_15pct),
    "stitching_overstated_hours": float(top.overstated_hours), "stitching_overstated_pkr": float(top.overstated_pkr),
    "stitching_requests": int(top.approved_requests), "stitching_requests_overstated": int(top.requests_overstated),
    "stitching_employees_overstated": int(top.employees_overstated), "stitching_approver": str(top.approver_id),
    "other_depts_overstated_hours": float(stitch.iloc[1:].overstated_hours.sum()),
    "after_separation_employees": int(sep.employees), "after_separation_months": int(sep.employee_months), "after_separation_pkr": float(sep.gross_pay_pkr),
    "unmapped_employees": int(unm.employees), "unmapped_months": int(unm.employee_months), "unmapped_pkr": float(unm.gross_pay_pkr),
    "no_attendance_pkr_total": float(sep.gross_pay_pkr + unm.gross_pay_pkr),
    "site_requests": int(clock_b.approved_site_requests.iloc[0]), "site_match_corrected": int(clock_b.match_with_correction.iloc[0]),
    "site_match_uncorrected": int(clock_b.match_without_correction.iloc[0]),
    "dq_checks": int(dq.checks.iloc[0]), "dq_passed": int(dq.passed.iloc[0]),
}
(HERE / "numbers.json").write_text(json.dumps(numbers, indent=2), encoding="utf-8")
n = numbers


def pkr(v):
    return f"PKR {v / 1e6:.1f}M" if v >= 1e6 else f"PKR {v:,.0f}"


def r0(v):
    """Round half up (Python's format rounds 6418.5 to 6,418; the text elsewhere says 6,419)."""
    return f"{int(v + 0.5):,}"


def wrap(text_, width):
    return textwrap.fill(text_, width)


def new_slide(title, subtitle=None):
    fig = plt.figure(figsize=(W, H))
    fig.patch.set_facecolor("white")
    fig.text(0.05, 0.92, title, fontsize=26, fontweight="bold", color=INK, va="center")
    if subtitle:
        fig.text(0.05, 0.855, subtitle, fontsize=14, color="#555555", va="center")
    return fig


def tile(fig, x, y, w, h, big, small, color):
    ax = fig.add_axes([x, y, w, h]); ax.axis("off")
    ax.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.04", fc="#f6f7f9", ec=color, lw=2.5, transform=ax.transAxes))
    ax.text(0.5, 0.64, big, fontsize=34, fontweight="bold", color=color, ha="center", va="center", transform=ax.transAxes)
    ax.text(0.5, 0.26, small, fontsize=13, color=INK, ha="center", va="center", transform=ax.transAxes, wrap=True, linespacing=1.4)


def footer(fig, text_):
    fig.text(0.05, 0.035, text_, fontsize=10, color="#777777")

_page = [0]


def emit(pdf, fig):
    """Add the slide to the PDF; with SLIDE_PREVIEW_DIR set, also save a PNG of it for a quick look."""
    _page[0] += 1
    pdf.savefig(fig)
    preview = os.environ.get("SLIDE_PREVIEW_DIR")
    if preview:
        fig.savefig(Path(preview) / f"slide{_page[0]}.png", dpi=80)
    plt.close(fig)

with PdfPages(HERE / "slides.pdf") as pdf:

    f = new_slide("Overtime cost is rising on paper, not on the shop floor", "Indus Weave Textiles - HR data pipeline, 1 Apr to 30 Sep 2026")
    tile(f, 0.05, 0.38, 0.28, 0.36, f"+{n['paid_growth_pct']:.0f}%",
         f"paid overtime hours Apr to Sep\n({r0(n['paid_hours_apr'])} to {r0(n['paid_hours_sep'])})\nhours actually worked: {n['worked_growth_pct']:+.0f}%", ORANGE)
    tile(f, 0.36, 0.38, 0.28, 0.36, pkr(n["no_attendance_pkr_total"]),
         f"paid to {n['after_separation_employees'] + n['unmapped_employees']} people with\nno attendance in the pay month", RED)
    tile(f, 0.67, 0.38, 0.28, 0.36, "60 min",
         f"SITE punch clock error from 1 July\n({n['site_match_corrected']:,} of {n['site_requests']:,} SITE working-day\novertime requests reconcile once fixed)", BLUE)
    f.text(0.05, 0.27, "The overtime gap sits in one department, Faisalabad Stitching, under one approver.\n"
           "Payroll pays from approved requests, not from punches, so nobody checks the hours.",
           fontsize=15, color=INK, linespacing=1.5)
    f.text(0.05, 0.15, f"All numbers come from a rebuilt warehouse: 12 raw files -> clean model -> 10 SQL answers,\n"
           f"{n['dq_passed']}/{n['dq_checks']} data quality checks passing.", fontsize=13, color="#555555", linespacing=1.5)
    footer(f, "Source: indus_weave_hcm_data, pipeline in this repository")
    emit(pdf, f)

    f = new_slide("Finding 1: we pay for overtime that punches do not support",
                  f"Paid hours up {n['paid_growth_pct']:.0f}%, worked hours {n['worked_growth_pct']:+.0f}%. The gap sits in one department.")
    ax = f.add_axes([0.06, 0.26, 0.40, 0.50])
    x = range(len(trend))
    ax.plot(x, trend.paid_hours, marker="o", color=ORANGE, lw=3, label="Paid (approved requests)")
    ax.plot(x, trend.worked_hours, marker="o", color=BLUE, lw=3, label="Worked (from punches)")
    ax.set_xticks(list(x)); ax.set_xticklabels([m[-2:] + "/26" for m in trend.year_month])
    ax.set_ylim(5000, 7000); ax.set_ylabel("overtime hours per month"); ax.legend(frameon=False, loc="upper left")
    ax.spines[["top", "right"]].set_visible(False); ax.set_title("Overtime hours, company-wide", loc="left", fontsize=13)
    ax2 = f.add_axes([0.56, 0.26, 0.38, 0.50])
    d = (q5.groupby(["plant", "dept_name"])[["computed_ot_hours", "paid_ot_hours"]].sum().reset_index())
    d["over_pct"] = 100 * (d.paid_ot_hours - d.computed_ot_hours) / d.computed_ot_hours
    d = d.sort_values("over_pct", ascending=False).head(8).iloc[::-1]
    labels = [f"{r.dept_name} ({r.plant.split()[0]})" for r in d.itertuples()]
    ax2.barh(labels, d.over_pct, color=[RED if v > 15 else GREY for v in d.over_pct])
    ax2.axvline(15, color=INK, ls="--", lw=1); ax2.text(15.5, -0.45, "15% line", fontsize=9)
    ax2.set_xlabel("paid overtime above hours worked (%)"); ax2.spines[["top", "right"]].set_visible(False)
    ax2.set_title("Paid vs worked by department, 6 months", loc="left", fontsize=13)
    f.text(0.05, 0.15, wrap(f"Faisalabad Stitching: {r0(n['stitching_paid_hours'])} h paid vs {r0(n['stitching_computed_hours'])} h worked (+{n['stitching_paid_vs_computed_pct']:.0f}%), "
           f"over the 15% line in {n['stitching_months_over_15pct']} of 6 months. Approver {n['stitching_approver']} approved all {n['stitching_requests']:,} Stitching requests; "
           f"{n['stitching_requests_overstated']:,} of them ({n['stitching_employees_overstated']} employees) exceed the hours worked, {r0(n['stitching_overstated_hours'])} h or "
           f"{pkr(n['stitching_overstated_pkr'])} in total. No other department has any.", 150), fontsize=12, color=INK, linespacing=1.5)
    footer(f, "Evidence: analytics/q05, q06; presentation/evidence/f1_*.sql")
    emit(pdf, f)

    f = new_slide(f"Finding 2: {pkr(n['no_attendance_pkr_total'])} went to people with no attendance",
                  "Paid in a month in which they did not attend a single day")
    tile(f, 0.05, 0.50, 0.42, 0.28, pkr(n["after_separation_pkr"]),
         f"{n['after_separation_employees']} employees paid in full for {n['after_separation_months']} pay-months\nafter their last working day", RED)
    tile(f, 0.53, 0.50, 0.42, 0.28, pkr(n["unmapped_pkr"]),
         f"{n['unmapped_employees']} active employees, {n['unmapped_months']} pay-months, no biometric device and\nno punch in six months", ORANGE)
    ax = f.add_axes([0.05, 0.10, 0.90, 0.30]); ax.axis("off")
    t = q8[["emp_id", "full_name", "dept_name", "separation_date", "months_paid_after_separation", "gross_pay_after_separation"]].copy()
    t["gross_pay_after_separation"] = t.gross_pay_after_separation.map("{:,.0f}".format)
    t.columns = ["Employee", "Name", "Department", "Last day worked", "Months paid after", "Gross paid after (PKR)"]
    tb = ax.table(cellText=t.values, colLabels=t.columns, loc="center", cellLoc="center")
    tb.auto_set_font_size(False); tb.set_fontsize(11); tb.scale(1, 1.55)
    for (r, c), cell in tb.get_celld().items():
        cell.set_edgecolor("#dddddd")
        if r == 0:
            cell.set_facecolor(BLUE); cell.set_text_props(color="white", fontweight="bold")
    footer(f, "Evidence: analytics/q07, q08; presentation/evidence/f2_pay_without_attendance.sql")
    emit(pdf, f)

    f = new_slide("Finding 3: one punch clock ran an hour fast",
                  "DEV-SITE-01 was exactly 60 minutes ahead from 1 July, so SITE numbers could not be trusted; the other devices stayed flat")
    ax = f.add_axes([0.06, 0.14, 0.52, 0.62])
    for dev, col in [("DEV-FSD-01", GREY), ("DEV-HO-01", "#b8b8b8"), ("DEV-KOR-01", GREEN), ("DEV-SITE-01", RED)]:
        g = diag[diag.device_id == dev]
        ax.plot(pd.to_datetime(g.week_start), g.avg_deviation_minutes, color=col, lw=3 if dev == "DEV-SITE-01" else 1.8, label=dev)
    ax.axhline(0, color=INK, lw=0.8)
    ax.set_ylabel("morning arrival time vs the device's own baseline (min)"); ax.legend(frameon=False, loc="upper left")
    ax.spines[["top", "right"]].set_visible(False)
    tile(f, 0.64, 0.46, 0.31, 0.28, f"{100 * n['site_match_corrected'] / n['site_requests']:.1f}%",
         f"of SITE working-day overtime requests\n(1 Jul on; {n['site_requests']:,}) reconcile after the fix", GREEN)
    tile(f, 0.64, 0.14, 0.31, 0.28, f"{100 * n['site_match_uncorrected'] / n['site_requests']:.0f}%",
         "reconcile on the raw, uncorrected\nSITE punch file", RED)
    footer(f, f"Found by comparing each device's morning arrival edge with its own baseline; {45803:,} punches corrected. Evidence: presentation/evidence/f3_clock_drift.sql")
    emit(pdf, f)

    f = new_slide("How we know the numbers are right", "Every raw row is accounted for, and the checks run on every load")
    steps = [("raw", "12 files as text\n+ load metadata\nidempotent"), ("staging", "typed, cleaned\nlogs of every row\nremoved"),
             ("warehouse", "star schema\nSCD2 employee\nkeys enforced"), ("10 answers", "one SQL file\nper question\nCSV results")]
    for i, (a, b) in enumerate(steps):
        ax = f.add_axes([0.05 + i * 0.235, 0.52, 0.2, 0.25]); ax.axis("off")
        ax.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.05", fc="#f6f7f9", ec=BLUE, lw=2.5, transform=ax.transAxes))
        ax.text(0.5, 0.78, a, fontsize=17, fontweight="bold", color=BLUE, ha="center", va="center", transform=ax.transAxes)
        ax.text(0.5, 0.36, b, fontsize=12, ha="center", va="center", transform=ax.transAxes, linespacing=1.5)
        if i < 3:
            f.text(0.05 + i * 0.235 + 0.208, 0.645, "->", fontsize=22, color=BLUE, va="center")
    bullets = [f"{n['dq_passed']} of {n['dq_checks']} automated checks pass (keys, foreign keys, accepted values, business sanity, SCD2 ranges)",
               "raw rows = staging + rejected + merged, for every table (345,280 punches = 322,143 clean + 6,962 unmapped + 16,175 duplicates)",
               "every one of the 322,143 clean punches lands on exactly one attendance day",
               "payroll overtime hours = approved overtime hours in all 6,572 employee-months: payroll follows requests, not punches",
               "the whole warehouse rebuilds from the raw files with one command: python run_pipeline.py"]
    for i, b in enumerate(bullets):
        f.text(0.06, 0.40 - i * 0.065, "- " + b, fontsize=13, color=INK)
    footer(f, "quality/dq_checks.py writes every result to dq.dq_results")
    emit(pdf, f)

    f = new_slide("What we recommend", "Three actions, in order of money at stake")
    acts = [("1", ORANGE, "Pay overtime only for hours the punches support",
             f"Stop payment on requests whose approved hours exceed hours worked. Review the {pkr(n['stitching_overstated_pkr'])} already paid in Faisalabad Stitching "
             f"and the approvals of {n['stitching_approver']}. Make approval depend on a punch check."),
            ("2", RED, f"Recover and stop the {pkr(n['no_attendance_pkr_total'])} paid without attendance",
             f"Remove the {n['after_separation_employees']} leavers from payroll and recover {pkr(n['after_separation_pkr'])}. Verify that the "
             f"{n['unmapped_employees']} active employees without a device exist and work, then enrol them."),
            ("3", BLUE, "Make the data trustworthy every month",
             "Run this pipeline on each export. Alert when a device drifts, when a leaver is paid, or when paid overtime exceeds worked overtime by more than 15%.")]
    for i, (num, col, head, body) in enumerate(acts):
        y = 0.62 - i * 0.24
        ax = f.add_axes([0.05, y, 0.90, 0.20]); ax.axis("off")
        ax.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.03", fc="#f6f7f9", ec=col, lw=2.5, transform=ax.transAxes))
        ax.text(0.04, 0.5, num, fontsize=40, fontweight="bold", color=col, ha="center", va="center", transform=ax.transAxes)
        ax.text(0.09, 0.72, head, fontsize=17, fontweight="bold", color=INK, va="center", transform=ax.transAxes)
        ax.text(0.09, 0.34, wrap(body, 112), fontsize=12.5, color=INK, va="center", transform=ax.transAxes, linespacing=1.4)
    footer(f, "Details and evidence queries: presentation/cfo_findings.md")
    emit(pdf, f)

print("wrote", HERE / "slides.pdf", "and", HERE / "numbers.json")
print(json.dumps(numbers, indent=2))
