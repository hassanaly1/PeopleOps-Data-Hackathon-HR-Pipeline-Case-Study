"""Draws the warehouse star schema to warehouse/erd.png and writes warehouse/erd.dbml (paste into dbdiagram.io).

Run:  python warehouse/make_erd.py
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

HERE = Path(__file__).resolve().parent

CORE, WORK, PAY, SHARED = "#2f6fa8", "#2e8b57", "#d9822b", "#6b6b6b"

TABLES = {
    "dim_department": (CORE, [("department_key", "PK"), ("dept_id (natural key)", ""), ("dept_name", ""), ("plant", ""),
                              ("cost_center", ""), ("previous_name", ""), ("renamed_on", "")]),
    "dim_date": (SHARED, [("date_key  (yyyymmdd)", "PK"), ("full_date", ""), ("year, quarter, month", ""), ("year_month", ""),
                          ("day_of_week, is_sunday", ""), ("week_start", ""), ("month_end, is_month_end", "")]),
    "dim_shift": (WORK, [("shift_key", "PK"), ("shift_code (natural key)", ""), ("shift_name", ""), ("start_time, end_time", ""),
                         ("crosses_midnight", ""), ("grace_minutes", "")]),
    "dim_employee  (SCD Type 2)": (CORE, [("employee_key", "PK"), ("emp_id (natural key)", ""), ("full_name, gender, plant", ""),
                                          ("employment_type, status", ""), ("hire_date, separation_date", ""),
                                          ("annual_leave_entitlement", ""), ("has_device_mapping", ""), ("department_key", "FK"),
                                          ("designation, grade, basic_salary", ""), ("change_reason", ""),
                                          ("valid_from, valid_to (9999-12-31 = open)", ""), ("is_current", "")]),
    "fact_attendance_daily": (WORK, [("attendance_key", "PK"), ("employee_key", "FK"), ("department_key", "FK"), ("shift_key", "FK"),
                                     ("date_key", "FK"), ("status", ""), ("is_working_day, n_punches", ""), ("check_in, check_out", ""),
                                     ("worked_hours", ""), ("late_minutes, early_departure_minutes", ""),
                                     ("overtime_hours, overtime_type", "")]),
    "fact_leave_day": (WORK, [("leave_day_key", "PK"), ("employee_key", "FK"), ("department_key", "FK"), ("date_key", "FK"),
                              ("leave_type", ""), ("request_id", "")]),
    "fact_overtime_approved": (WORK, [("request_id", "PK"), ("employee_key", "FK"), ("department_key", "FK"), ("date_key", "FK"),
                                      ("requested_hours, approved_hours", ""), ("approver_id", "")]),
    "fact_payroll_line": (PAY, [("line_id", "PK"), ("employee_key", "FK"), ("department_key", "FK"), ("date_key", "FK"),
                                ("payroll_month", ""), ("component, component_type", ""), ("units", ""), ("amount", "")]),
}

LAYOUT = {
    "dim_department": (0.6, 14.4, 4.6), "dim_date": (9.6, 14.4, 4.8), "dim_shift": (18.4, 14.4, 4.6),
    "fact_attendance_daily": (0.6, 8.6, 5.6), "fact_leave_day": (7.0, 8.6, 4.4), "fact_overtime_approved": (12.2, 8.6, 5.2),
    "fact_payroll_line": (18.4, 8.6, 4.6),
    "dim_employee  (SCD Type 2)": (8.0, 2.4, 8.0),
}
ROW, HEAD = 0.42, 0.55

FKS = [
    ("fact_attendance_daily", "dim_department"), ("fact_attendance_daily", "dim_date"), ("fact_attendance_daily", "dim_shift"),
    ("fact_attendance_daily", "dim_employee  (SCD Type 2)"),
    ("fact_leave_day", "dim_department"), ("fact_leave_day", "dim_date"), ("fact_leave_day", "dim_employee  (SCD Type 2)"),
    ("fact_overtime_approved", "dim_department"), ("fact_overtime_approved", "dim_date"), ("fact_overtime_approved", "dim_employee  (SCD Type 2)"),
    ("fact_payroll_line", "dim_department"), ("fact_payroll_line", "dim_date"), ("fact_payroll_line", "dim_employee  (SCD Type 2)"),
    ("dim_employee  (SCD Type 2)", "dim_department"),
]


def box(name):
    x, y, w = LAYOUT[name]
    h = HEAD + ROW * len(TABLES[name][1])
    return x, y - h, w, h


def anchor(name, side, k=0, n=1):
    x, y, w, h = box(name)
    f = (k + 1) / (n + 1)
    return {"top": (x + w * f, y + h), "bottom": (x + w * f, y), "left": (x, y + h * f), "right": (x + w, y + h * f)}[side]


def main():
    fig, ax = plt.subplots(figsize=(22, 20))
    ax.set_xlim(0, 24), ax.set_ylim(-6.2, 15.6), ax.axis("off")

    def sides(fact, dim):
        """Which edge each end of a relationship leaves from."""
        if fact.startswith("fact") and dim.startswith("dim_employee"):
            return "bottom", "top"
        return "top", "bottom"

    use = {}
    for fact, dim in FKS:
        sf, sd = sides(fact, dim)
        for key in ((fact, sf), (dim, sd)):
            use[key] = use.get(key, 0) + 1
    seen_f, seen_d = {}, {}
    for fact, dim in FKS:
        sf, sd = sides(fact, dim)
        kf, kd = (fact, sf), (dim, sd)
        i, j = seen_f.get(kf, 0), seen_d.get(kd, 0)
        seen_f[kf], seen_d[kd] = i + 1, j + 1
        x1, y1 = anchor(fact, sf, i, use[kf])
        x2, y2 = anchor(dim, sd, j, use[kd])
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="-|>", color="#555555", lw=1.1, alpha=0.75, shrinkA=0, shrinkB=0))
        ax.text(x1, y1 + (0.12 if sf == "top" else -0.28), "N", fontsize=8, color="#555555", ha="center")
        ax.text(x2, y2 + (0.12 if sd == "top" else -0.28), "1", fontsize=8, color="#555555", ha="center")

    for name, (color, cols) in TABLES.items():
        x, y, w, h = box(name)
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.08", fc="white", ec=color, lw=2, zorder=3))
        ax.add_patch(Rectangle((x, y + h - HEAD), w, HEAD, fc=color, ec=color, zorder=4))
        ax.text(x + 0.15, y + h - HEAD / 2, name, color="white", fontsize=12, fontweight="bold", va="center", zorder=5)
        for i, (col, flag) in enumerate(cols):
            ty = y + h - HEAD - ROW * (i + 0.5)
            ax.text(x + 0.15, ty, flag, fontsize=9, fontweight="bold", color=color, va="center", zorder=5, family="monospace")
            ax.text(x + 0.75, ty, col, fontsize=10, color="#222222", va="center", zorder=5, family="monospace")

    ax.text(0.6, 15.1, "Indus Weave Textiles - HR warehouse (star schema)", fontsize=18, fontweight="bold", color="#222222")
    ax.text(0.6, 14.75, "Every fact carries employee_key (the SCD2 version on the fact's reference date) and department_key. "
            "Join rule:  fact_date BETWEEN dim_employee.valid_from AND dim_employee.valid_to", fontsize=10, color="#444444")
    legend = [(CORE, "Core HR / Foundation (people, organisation)"), (WORK, "Workforce module (shifts, attendance, leave, overtime)"),
              (PAY, "Payroll module - consumes the Workforce results"), (SHARED, "Shared calendar")]
    for i, (c, label) in enumerate(legend):
        ax.add_patch(Rectangle((0.6, -4.2 - i * 0.42), 0.45, 0.26, fc=c, ec=c))
        ax.text(1.2, -4.07 - i * 0.42, label, fontsize=10, va="center")
    ax.text(12.5, -4.07, "PK primary key   FK foreign key (enforced)   N / 1 = many / one", fontsize=10, color="#444444")
    fig.savefig(HERE / "erd.png", dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    lines = []
    for name, (_, cols) in TABLES.items():
        lines.append(f"Table {name.split()[0]} {{")
        for col, flag in cols:
            ident = col.split()[0].rstrip(",")
            if "," in col or "(" in col and flag == "":
                for part in [p.strip() for p in col.split("(")[0].split(",")]:
                    lines.append(f"  {part} varchar")
                continue
            lines.append(f"  {ident} {'int' if flag else 'varchar'}{' [pk]' if flag == 'PK' else ''}")
        lines.append("}\n")
    for fact, dim in FKS:
        f, d = fact.split()[0], dim.split()[0]
        key = {"dim_department": "department_key", "dim_date": "date_key", "dim_shift": "shift_key", "dim_employee": "employee_key"}[d]
        lines.append(f"Ref: {f}.{key} > {d}.{key}")
    (HERE / "erd.dbml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote", HERE / "erd.png", "and", HERE / "erd.dbml")


if __name__ == "__main__":
    main()
