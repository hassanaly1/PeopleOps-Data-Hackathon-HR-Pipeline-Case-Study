"""Stage 6: data quality checks. Results are appended to dq.dq_results.

A check is (layer, category, table, name, actual_sql, expected). It passes when the SQL result equals the expectation,
which is 0 violations by default.

Run alone: python -m quality.dq_checks [raw|staging|warehouse]
"""
import logging
import sys
import uuid
from dataclasses import dataclass

from sqlalchemy import text

from db import get_engine

log = logging.getLogger("pipeline")


@dataclass
class Check:
    layer: str
    category: str
    table: str
    name: str
    actual_sql: str
    expected: object = 0

RAW_TABLES = ["employees", "employment_history", "departments", "shifts", "shift_roster", "device_mapping",
              "biometric_punches", "holidays", "leave_requests", "overtime_requests", "payroll_lines", "applications"]

STAGING_PK = {
    "employees": ["emp_id"], "employee_merge_log": ["dropped_row_id"], "employment_history": ["emp_id", "valid_from"],
    "history_rejected": ["source_row_id"], "departments": ["dept_id"], "shifts": ["shift_code"],
    "shift_roster": ["emp_id", "week_start"], "employee_shift_week": ["emp_id", "week_start"],
    "holiday_plant": ["holiday_date", "plant"], "device_mapping": ["device_id", "device_user_id"],
    "device_clock_correction": ["device_id", "valid_from"],
    "punches": ["punch_id"], "rejected_punches": ["punch_id"], "duplicate_punches": ["punch_id"],
    "punch_shift_date": ["punch_id"], "leave_requests": ["request_id"], "leave_approval_steps": ["request_id", "step"],
    "leave_days": ["emp_id", "leave_date"], "overtime_requests": ["request_id"], "payroll_lines": ["line_id"],
    "attendance_daily": ["emp_id", "att_date"],
}
WAREHOUSE_PK = {
    "dim_date": ["date_key"], "dim_department": ["department_key"], "dim_shift": ["shift_key"],
    "dim_employee": ["employee_key"], "fact_attendance_daily": ["attendance_key"], "fact_leave_day": ["leave_day_key"],
    "fact_overtime_approved": ["request_id"], "fact_payroll_line": ["line_id"],
}
WAREHOUSE_NATURAL_KEYS = {
    "dim_employee": ["emp_id", "valid_from"], "dim_department": ["dept_id"], "dim_shift": ["shift_code"],
    "fact_attendance_daily": ["employee_key", "date_key"], "fact_leave_day": ["employee_key", "date_key"],
}
FOREIGN_KEYS = [
    ("dim_employee", "department_key", "dim_department", "department_key"),
    ("fact_attendance_daily", "employee_key", "dim_employee", "employee_key"),
    ("fact_attendance_daily", "department_key", "dim_department", "department_key"),
    ("fact_attendance_daily", "shift_key", "dim_shift", "shift_key"),
    ("fact_attendance_daily", "date_key", "dim_date", "date_key"),
    ("fact_leave_day", "employee_key", "dim_employee", "employee_key"),
    ("fact_leave_day", "department_key", "dim_department", "department_key"),
    ("fact_leave_day", "date_key", "dim_date", "date_key"),
    ("fact_overtime_approved", "employee_key", "dim_employee", "employee_key"),
    ("fact_overtime_approved", "department_key", "dim_department", "department_key"),
    ("fact_overtime_approved", "date_key", "dim_date", "date_key"),
    ("fact_payroll_line", "employee_key", "dim_employee", "employee_key"),
    ("fact_payroll_line", "department_key", "dim_department", "department_key"),
    ("fact_payroll_line", "date_key", "dim_date", "date_key"),
]


def build_checks() -> list[Check]:
    c: list[Check] = []

    for t in RAW_TABLES:
        c += [
            Check("raw", "uniqueness", f"raw.{t}", "_row_id is unique",
                  f"SELECT COUNT(*) FROM (SELECT _row_id FROM raw.{t} GROUP BY _row_id HAVING COUNT(*) > 1) q"),
            Check("raw", "not_null", f"raw.{t}", "load metadata is never NULL",
                  f"SELECT COUNT(*) FROM raw.{t} WHERE _row_id IS NULL OR _source_file IS NULL OR _loaded_at IS NULL OR _row_hash IS NULL"),
            Check("raw", "uniqueness", f"raw.{t}", "(_source_file, _row_hash, _dup_seq) is unique (idempotent load)",
                  f"SELECT COUNT(*) FROM (SELECT 1 x FROM raw.{t} GROUP BY _source_file, _row_hash, _dup_seq HAVING COUNT(*) > 1) q"),
        ]
    c.append(Check("raw", "reconciliation", "raw.load_log", "every file's row count matches its raw table (latest load)",
                   "SELECT COUNT(*) FROM raw.load_log l WHERE l.log_id IN (SELECT MAX(log_id) FROM raw.load_log GROUP BY source_file) "
                   "AND l.status <> 'MATCH'"))
    c.append(Check("staging", "reconciliation", "raw.leave_requests", "approval steps in the JSON = rows in staging.leave_approval_steps",
                   "SELECT COUNT(*) FROM staging.leave_approval_steps",
                   "SELECT SUM(c) FROM raw.leave_requests CROSS APPLY (SELECT COUNT(*) AS c FROM OPENJSON(record_json, '$.approvals')) x"))

    for t, pk in STAGING_PK.items():
        cols = ", ".join(pk)
        c += [
            Check("staging", "uniqueness", f"staging.{t}", f"primary key ({cols}) is unique",
                  f"SELECT COUNT(*) FROM (SELECT 1 x FROM staging.{t} GROUP BY {cols} HAVING COUNT(*) > 1) q"),
            Check("staging", "not_null", f"staging.{t}", f"primary key ({cols}) has no NULL",
                  f"SELECT COUNT(*) FROM staging.{t} WHERE " + " OR ".join(f"{k} IS NULL" for k in pk)),
        ]

    recon = [
        ("employees", ["employees", "employee_merge_log"]),
        ("employment_history", ["employment_history", "history_rejected"]),
        ("departments", ["departments"]), ("shifts", ["shifts"]), ("shift_roster", ["shift_roster"]),
        ("device_mapping", ["device_mapping"]),
        ("biometric_punches", ["punches", "rejected_punches", "duplicate_punches"]),
        ("holidays", ["holidays"]), ("leave_requests", ["leave_requests"]), ("overtime_requests", ["overtime_requests"]),
        ("payroll_lines", ["payroll_lines"]), ("applications", ["applications"]),
    ]
    for raw_t, stg in recon:
        c.append(Check("staging", "reconciliation", f"raw.{raw_t}",
                       f"raw rows = {' + '.join(stg)}",
                       "SELECT " + " + ".join(f"(SELECT COUNT(*) FROM staging.{s})" for s in stg),
                       f"SELECT COUNT(*) FROM raw.{raw_t}"))

    c += [
        Check("staging", "accepted_values", "staging.attendance_daily", "status is one of the six allowed values",
              "SELECT COUNT(*) FROM staging.attendance_daily WHERE status NOT IN ('Present','Absent','On Leave','Holiday','Weekly Off','Missing Punch')"),
        Check("staging", "accepted_values", "staging.leave_requests", "leave type is Annual / Casual / Sick",
              "SELECT COUNT(*) FROM staging.leave_requests WHERE leave_type NOT IN ('Annual','Casual','Sick')"),
        Check("staging", "accepted_values", "staging.leave_approval_steps", "approval action is Approved / Rejected / Pending",
              "SELECT COUNT(*) FROM staging.leave_approval_steps WHERE action NOT IN ('Approved','Rejected','Pending')"),
        Check("staging", "accepted_values", "staging.payroll_lines", "component is one of the nine pay components",
              "SELECT COUNT(*) FROM staging.payroll_lines WHERE component NOT IN ('BASIC','HOUSE_RENT','MEDICAL','CONVEYANCE','OVERTIME','INCOME_TAX','EOBI','ABSENCE_DEDUCTION','LOAN_INSTALLMENT')"),
        Check("staging", "accepted_values", "staging.payroll_lines", "component_type is EARNING / DEDUCTION",
              "SELECT COUNT(*) FROM staging.payroll_lines WHERE component_type NOT IN ('EARNING','DEDUCTION')"),
        Check("staging", "accepted_values", "staging.overtime_requests", "status is Approved / Rejected / Pending",
              "SELECT COUNT(*) FROM staging.overtime_requests WHERE status NOT IN ('Approved','Rejected','Pending')"),
        Check("staging", "accepted_values", "staging.shift_roster", "shift_code exists in shifts.json",
              "SELECT COUNT(*) FROM staging.shift_roster r WHERE NOT EXISTS (SELECT 1 FROM staging.shifts s WHERE s.shift_code = r.shift_code)"),
        Check("staging", "accepted_values", "staging.employees", "employment_type is Permanent / Contract and status is Active / Separated",
              "SELECT COUNT(*) FROM staging.employees WHERE employment_type NOT IN ('Permanent','Contract') OR status NOT IN ('Active','Separated')"),
        Check("staging", "accepted_values", "staging.employees", "every date column was parsed (hire_date, date_of_birth, non-blank separation_date)",
              "SELECT COUNT(*) FROM staging.employees e JOIN raw.employees r ON r._row_id = e.source_row_id "
              "WHERE e.hire_date IS NULL OR e.date_of_birth IS NULL OR (NULLIF(LTRIM(RTRIM(r.separation_date)), '') IS NOT NULL AND e.separation_date IS NULL)"),
        Check("staging", "accepted_values", "staging.employees", "every employee's department text maps to a department",
              "SELECT COUNT(*) FROM staging.employees WHERE dept_id_on_profile IS NULL"),
        Check("staging", "referential_integrity", "staging.punches", "every clean punch maps to an employee",
              "SELECT COUNT(*) FROM staging.punches p WHERE NOT EXISTS (SELECT 1 FROM staging.employees e WHERE e.emp_id = p.emp_id)"),
        Check("staging", "referential_integrity", "staging.employment_history", "every history row belongs to an employee and a department",
              "SELECT COUNT(*) FROM staging.employment_history h WHERE NOT EXISTS (SELECT 1 FROM staging.employees e WHERE e.emp_id = h.emp_id) "
              "OR NOT EXISTS (SELECT 1 FROM staging.departments d WHERE d.dept_id = h.dept_id)"),
        Check("staging", "referential_integrity", "staging.payroll_lines", "every payroll line belongs to an employee",
              "SELECT COUNT(*) FROM staging.payroll_lines p WHERE NOT EXISTS (SELECT 1 FROM staging.employees e WHERE e.emp_id = p.emp_id)"),
        Check("staging", "business_sanity", "staging.attendance_daily", "no negative worked hours",
              "SELECT COUNT(*) FROM staging.attendance_daily WHERE worked_hours < 0 OR late_minutes < 0 OR early_departure_minutes < 0 OR overtime_hours < 0"),
        Check("staging", "business_sanity", "staging.attendance_daily", "no shift longer than 16 hours",
              "SELECT COUNT(*) FROM staging.attendance_daily WHERE worked_hours > 16"),
        Check("staging", "business_sanity", "staging.attendance_daily", "exactly one row per employee per day of employment (1 Apr - 30 Sep)",
              "SELECT COUNT(*) FROM staging.attendance_daily",
              "SELECT SUM(DATEDIFF(DAY, CASE WHEN hire_date > '2026-04-01' THEN hire_date ELSE CAST('2026-04-01' AS DATE) END, "
              "CASE WHEN separation_date IS NULL OR separation_date > '2026-09-30' THEN CAST('2026-09-30' AS DATE) ELSE separation_date END) + 1) "
              "FROM staging.employees WHERE hire_date <= '2026-09-30' AND (separation_date IS NULL OR separation_date >= '2026-04-01')"),
        Check("staging", "business_sanity", "staging.attendance_daily", "every clean punch is placed on an attendance row",
              "SELECT SUM(n_punches) FROM staging.attendance_daily", "SELECT COUNT(*) FROM staging.punches"),
        Check("staging", "business_sanity", "staging.attendance_daily", "late / early / overtime only on Present days",
              "SELECT COUNT(*) FROM staging.attendance_daily WHERE status <> 'Present' AND (is_late = 1 OR is_early_departure = 1 OR overtime_hours > 0)"),
        Check("staging", "business_sanity", "staging.attendance_daily", "status follows the rule-12 priority (Sunday/holiday with no punch is never Absent)",
              "SELECT COUNT(*) FROM staging.attendance_daily a JOIN staging.calendar c ON c.d = a.att_date "
              "WHERE a.status = 'Absent' AND (c.is_sunday = 1 OR a.holiday_name IS NOT NULL)"),
        Check("staging", "business_sanity", "staging.employment_history", "no overlapping validity ranges for one employee",
              "SELECT COUNT(*) FROM (SELECT valid_to, LEAD(valid_from) OVER (PARTITION BY emp_id ORDER BY valid_from) AS next_from "
              "FROM staging.employment_history) q WHERE valid_to IS NOT NULL AND next_from <= valid_to"),
        Check("staging", "business_sanity", "staging.employment_history", "no gaps between consecutive ranges",
              "SELECT COUNT(*) FROM (SELECT valid_to, LEAD(valid_from) OVER (PARTITION BY emp_id ORDER BY valid_from) AS next_from "
              "FROM staging.employment_history) q WHERE valid_to IS NOT NULL AND next_from <> DATEADD(DAY, 1, valid_to)"),
        Check("staging", "business_sanity", "staging.employment_history", "first history record starts on the hire date",
              "SELECT COUNT(*) FROM staging.employees e JOIN (SELECT emp_id, MIN(valid_from) AS first_from FROM staging.employment_history GROUP BY emp_id) h "
              "ON h.emp_id = e.emp_id WHERE h.first_from <> e.hire_date"),
        Check("staging", "business_sanity", "staging.punches", "no punch before hire or after the day after separation",
              "SELECT COUNT(*) FROM staging.punches p JOIN staging.employees e ON e.emp_id = p.emp_id "
              "WHERE CAST(p.punch_time AS DATE) < e.hire_date OR CAST(p.punch_time AS DATE) > DATEADD(DAY, 1, ISNULL(e.separation_date, '2999-01-01'))"),
        Check("staging", "business_sanity", "staging.punches", "no two punches of one employee within 2 minutes after de-duplication",
              "SELECT COUNT(*) FROM (SELECT DATEDIFF(SECOND, LAG(punch_time) OVER (PARTITION BY emp_id ORDER BY punch_time), punch_time) AS gap "
              "FROM staging.punches) q WHERE gap <= 120"),
        Check("staging", "business_sanity", "staging.device_clock_correction", "after correction no device is more than 20 minutes from the others",
              "SELECT COUNT(*) FROM (SELECT d.device_id, d.week_start, d.avg_deviation_minutes FROM staging.device_clock_diagnostics d) q "
              "WHERE ABS(q.avg_deviation_minutes) > 20 AND NOT EXISTS (SELECT 1 FROM staging.device_clock_correction c "
              "WHERE c.device_id = q.device_id AND q.week_start >= DATEADD(DAY, -6, c.valid_from))"),
        Check("staging", "business_sanity", "staging.leave_days", "no leave day on a Sunday or plant holiday",
              "SELECT COUNT(*) FROM staging.leave_days l JOIN staging.calendar c ON c.d = l.leave_date JOIN staging.employees e ON e.emp_id = l.emp_id "
              "WHERE c.is_sunday = 1 OR EXISTS (SELECT 1 FROM staging.holiday_plant h WHERE h.holiday_date = l.leave_date AND h.plant = e.plant)"),
        Check("staging", "business_sanity", "staging.leave_days", "every leave day comes from a request approved by both steps and not cancelled",
              "SELECT COUNT(*) FROM staging.leave_days l JOIN staging.leave_requests r ON r.request_id = l.request_id WHERE r.is_counted = 0"),
        Check("staging", "business_sanity", "staging.overtime_requests", "approved overtime has approved_hours; others do not",
              "SELECT COUNT(*) FROM staging.overtime_requests WHERE (status = 'Approved' AND (approved_hours IS NULL OR approved_hours <= 0)) "
              "OR (status <> 'Approved' AND approved_hours IS NOT NULL)"),
        Check("staging", "business_sanity", "staging.payroll_lines", "payroll overtime hours = approved overtime hours for every employee-month (rule 20)",
              "SELECT COUNT(*) FROM (SELECT COALESCE(p.emp_id, a.emp_id) AS emp_id FROM "
              "(SELECT emp_id, payroll_month, SUM(units) AS paid FROM staging.payroll_lines WHERE component = 'OVERTIME' GROUP BY emp_id, payroll_month) p "
              "FULL JOIN (SELECT emp_id, FORMAT(ot_date, 'yyyy-MM') AS ym, SUM(approved_hours) AS appr FROM staging.overtime_requests WHERE status = 'Approved' GROUP BY emp_id, FORMAT(ot_date, 'yyyy-MM')) a "
              "ON a.emp_id = p.emp_id AND a.ym = p.payroll_month WHERE ISNULL(p.paid, 0) <> ISNULL(a.appr, 0)) q"),
    ]

    for t, pk in WAREHOUSE_PK.items():
        cols = ", ".join(pk)
        c += [
            Check("warehouse", "uniqueness", f"warehouse.{t}", f"primary key ({cols}) is unique",
                  f"SELECT COUNT(*) FROM (SELECT 1 x FROM warehouse.{t} GROUP BY {cols} HAVING COUNT(*) > 1) q"),
            Check("warehouse", "not_null", f"warehouse.{t}", f"primary key ({cols}) has no NULL",
                  f"SELECT COUNT(*) FROM warehouse.{t} WHERE " + " OR ".join(f"{k} IS NULL" for k in pk)),
        ]
    for t, nk in WAREHOUSE_NATURAL_KEYS.items():
        cols = ", ".join(nk)
        c.append(Check("warehouse", "uniqueness", f"warehouse.{t}", f"natural key ({cols}) is unique",
                       f"SELECT COUNT(*) FROM (SELECT 1 x FROM warehouse.{t} GROUP BY {cols} HAVING COUNT(*) > 1) q"))
    for t, col, ref_t, ref_col in FOREIGN_KEYS:
        c.append(Check("warehouse", "referential_integrity", f"warehouse.{t}", f"{col} -> {ref_t}.{ref_col}: no orphan rows",
                       f"SELECT COUNT(*) FROM warehouse.{t} f WHERE NOT EXISTS (SELECT 1 FROM warehouse.{ref_t} d WHERE d.{ref_col} = f.{col})"))
    c += [
        Check("warehouse", "referential_integrity", "warehouse.fact_attendance_daily", "employee version covers the attendance date (SCD2)",
              "SELECT COUNT(*) FROM warehouse.fact_attendance_daily f JOIN warehouse.dim_employee e ON e.employee_key = f.employee_key "
              "JOIN warehouse.dim_date d ON d.date_key = f.date_key WHERE d.full_date NOT BETWEEN e.valid_from AND e.valid_to"),
        Check("warehouse", "referential_integrity", "warehouse.fact_leave_day", "employee version covers the leave date (SCD2)",
              "SELECT COUNT(*) FROM warehouse.fact_leave_day f JOIN warehouse.dim_employee e ON e.employee_key = f.employee_key "
              "JOIN warehouse.dim_date d ON d.date_key = f.date_key WHERE d.full_date NOT BETWEEN e.valid_from AND e.valid_to"),
        Check("warehouse", "referential_integrity", "warehouse.fact_attendance_daily", "department_key of the fact = department of its employee version",
              "SELECT COUNT(*) FROM warehouse.fact_attendance_daily f JOIN warehouse.dim_employee e ON e.employee_key = f.employee_key "
              "WHERE e.department_key <> f.department_key"),
        Check("warehouse", "reconciliation", "warehouse.dim_employee", "SCD2 rows = staging.employment_history rows",
              "SELECT COUNT(*) FROM warehouse.dim_employee", "SELECT COUNT(*) FROM staging.employment_history"),
        Check("warehouse", "reconciliation", "warehouse.fact_attendance_daily", "fact rows = staging.attendance_daily rows",
              "SELECT COUNT(*) FROM warehouse.fact_attendance_daily", "SELECT COUNT(*) FROM staging.attendance_daily"),
        Check("warehouse", "reconciliation", "warehouse.fact_leave_day", "fact rows = staging.leave_days rows",
              "SELECT COUNT(*) FROM warehouse.fact_leave_day", "SELECT COUNT(*) FROM staging.leave_days"),
        Check("warehouse", "reconciliation", "warehouse.fact_overtime_approved", "fact rows = Approved rows of staging.overtime_requests",
              "SELECT COUNT(*) FROM warehouse.fact_overtime_approved", "SELECT COUNT(*) FROM staging.overtime_requests WHERE status = 'Approved'"),
        Check("warehouse", "reconciliation", "warehouse.fact_payroll_line", "fact rows = staging.payroll_lines rows",
              "SELECT COUNT(*) FROM warehouse.fact_payroll_line", "SELECT COUNT(*) FROM staging.payroll_lines"),
        Check("warehouse", "reconciliation", "warehouse.fact_payroll_line", "payroll amount total unchanged from staging",
              "SELECT CAST(SUM(amount) AS DECIMAL(18,2)) FROM warehouse.fact_payroll_line", "SELECT CAST(SUM(amount) AS DECIMAL(18,2)) FROM staging.payroll_lines"),
        Check("warehouse", "reconciliation", "warehouse.fact_attendance_daily", "overtime hours total unchanged from staging",
              "SELECT CAST(SUM(overtime_hours) AS DECIMAL(18,1)) FROM warehouse.fact_attendance_daily", "SELECT CAST(SUM(overtime_hours) AS DECIMAL(18,1)) FROM staging.attendance_daily"),
        Check("warehouse", "accepted_values", "warehouse.fact_attendance_daily", "status is one of the six allowed values",
              "SELECT COUNT(*) FROM warehouse.fact_attendance_daily WHERE status NOT IN ('Present','Absent','On Leave','Holiday','Weekly Off','Missing Punch')"),
        Check("warehouse", "accepted_values", "warehouse.fact_leave_day", "leave_type is Annual / Casual / Sick",
              "SELECT COUNT(*) FROM warehouse.fact_leave_day WHERE leave_type NOT IN ('Annual','Casual','Sick')"),
        Check("warehouse", "accepted_values", "warehouse.fact_payroll_line", "component and component_type are allowed values",
              "SELECT COUNT(*) FROM warehouse.fact_payroll_line WHERE component NOT IN ('BASIC','HOUSE_RENT','MEDICAL','CONVEYANCE','OVERTIME','INCOME_TAX','EOBI','ABSENCE_DEDUCTION','LOAN_INSTALLMENT') "
              "OR component_type NOT IN ('EARNING','DEDUCTION')"),
        Check("warehouse", "business_sanity", "warehouse.fact_attendance_daily", "no negative worked hours and no shift longer than 16 hours",
              "SELECT COUNT(*) FROM warehouse.fact_attendance_daily WHERE worked_hours < 0 OR worked_hours > 16"),
        Check("warehouse", "business_sanity", "warehouse.dim_employee", "no overlapping SCD2 ranges for one employee",
              "SELECT COUNT(*) FROM (SELECT valid_to, LEAD(valid_from) OVER (PARTITION BY emp_id ORDER BY valid_from) AS next_from FROM warehouse.dim_employee) q "
              "WHERE next_from <= valid_to"),
        Check("warehouse", "business_sanity", "warehouse.dim_employee", "exactly one current (open) version per employee",
              "SELECT COUNT(*) FROM (SELECT emp_id FROM warehouse.dim_employee GROUP BY emp_id HAVING SUM(CAST(is_current AS INT)) <> 1) q"),
        Check("warehouse", "business_sanity", "warehouse.dim_employee", "is_current agrees with an open valid_to",
              "SELECT COUNT(*) FROM warehouse.dim_employee WHERE (is_current = 1 AND valid_to <> '9999-12-31') OR (is_current = 0 AND valid_to = '9999-12-31')"),
        Check("warehouse", "business_sanity", "warehouse.fact_payroll_line", "payroll amounts are not negative (deductions are positive)",
              "SELECT COUNT(*) FROM warehouse.fact_payroll_line WHERE amount < 0"),
    ]
    return c

DDL = """
IF OBJECT_ID(N'dq.dq_results') IS NULL
CREATE TABLE dq.dq_results (
    result_id      INT IDENTITY(1,1) PRIMARY KEY,
    run_id         VARCHAR(40)   NOT NULL,
    run_at         DATETIME2(0)  NOT NULL DEFAULT SYSUTCDATETIME(),
    layer          VARCHAR(12)   NOT NULL,
    category       VARCHAR(30)   NOT NULL,
    table_name     VARCHAR(80)   NOT NULL,
    check_name     VARCHAR(300)  NOT NULL,
    status         VARCHAR(5)    NOT NULL,      -- PASS / FAIL / ERROR
    expected_value VARCHAR(60)   NULL,
    actual_value   VARCHAR(60)   NULL,
    detail         VARCHAR(500)  NULL)
"""


def _scalar(conn, sql: str):
    v = conn.execute(text(sql)).scalar()
    return 0 if v is None else v


def run(layers: list[str] | None = None, run_id: str | None = None) -> tuple[int, int]:
    """Run the checks of the given layers (default all). Returns (passed, failed)."""
    layers = layers or ["raw", "staging", "warehouse"]
    run_id = run_id or uuid.uuid4().hex[:12]
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("IF SCHEMA_ID(N'dq') IS NULL EXEC('CREATE SCHEMA dq')"))
        conn.execute(text(DDL))

    passed = failed = 0
    rows = []
    with engine.connect() as conn:
        for chk in build_checks():
            if chk.layer not in layers:
                continue
            try:
                actual = _scalar(conn, chk.actual_sql)
                expected = _scalar(conn, chk.expected) if isinstance(chk.expected, str) else chk.expected
                ok = actual == expected
                status, detail = ("PASS" if ok else "FAIL"), None
            except Exception as exc:
                actual, expected, status, detail = None, None, "ERROR", str(exc).splitlines()[0][:480]
                ok = False
            passed += ok
            failed += not ok
            rows.append({"run_id": run_id, "layer": chk.layer, "category": chk.category, "table_name": chk.table,
                         "check_name": chk.name[:300], "status": status,
                         "expected_value": None if expected is None else str(expected),
                         "actual_value": None if actual is None else str(actual), "detail": detail})
            if not ok:
                log.warning("DQ %s FAIL %s | %s | expected=%s actual=%s %s", chk.layer, chk.table, chk.name, expected, actual, detail or "")
    with engine.begin() as conn:
        conn.execute(text("""INSERT INTO dq.dq_results (run_id, layer, category, table_name, check_name, status, expected_value, actual_value, detail)
                             VALUES (:run_id, :layer, :category, :table_name, :check_name, :status, :expected_value, :actual_value, :detail)"""), rows)
    log.info("data quality [%s]: %d checks, %d passed, %d failed (run_id %s)", "+".join(layers), passed + failed, passed, failed, run_id)
    return passed, failed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stdout)
    _, bad = run(sys.argv[1:] or None)
    sys.exit(1 if bad else 0)
