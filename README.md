# Indus Weave Textiles - HR data pipeline

Turns six months (1 Apr - 30 Sep 2026) of messy HCM exports into a trusted SQL Server warehouse, answers the ten business
questions with SQL, proves the numbers with 174 automated data quality checks, and explains why overtime cost keeps rising.

**Team:** Hassan Ali

> **Database note.** The case study names PostgreSQL (SQLite as the fallback). This team works in **SQL Server**, so the
> whole pipeline is written in T-SQL + Python. If the organizers require PostgreSQL, tell us before judging; every stage
> is a plain SQL file plus a thin Python runner, so only the dialect-specific parts (`OPENJSON`, `DATEDIFF`, `FORMAT`,
> `IDENTITY`) would need porting.

## Headline findings (details in `presentation/cfo_findings.md`)

1. **Paid overtime is rising, worked overtime is not.** Paid overtime hours grew from 5,526 (Apr) to 6,419 (Sep), +16%, while the
   hours actually worked from biometric punches were flat (6,167 -> 6,066). The gap is one department: **Faisalabad Stitching** is
   paid 56% more overtime than punches support, all approved by a single approver.
2. **PKR 4.8 million was paid to people with no attendance:** 5 employees were paid in full for months after they left, and 6 active
   employees have no biometric device and no punches in six months.
3. **Numbers cannot be trusted until the data is fixed:** the SITE plant punch clock ran exactly one hour fast from 1 July
   (45,803 punches). With the correction, 95.4% of SITE working-day overtime requests reconcile to punches (95.9% before July);
   on the raw punch file, none do.

## What you need

| | |
|---|---|
| SQL Server 2019 or newer (Developer / Express is fine) and a Windows login that may create a database | |
| Microsoft ODBC Driver 17 or 18 for SQL Server | |
| Python 3.10+ | `pip install -r requirements.txt` |
| The dataset pack (`indus_weave_hcm_data.zip`) | unzip the 12 files + `data_dictionary.md` into `data/` |

## Rebuild from the raw files (one command)

```bash
pip install -r requirements.txt
# put the 12 raw files in data/   (or set HR_DATA_DIR to where they are)
python run_pipeline.py
```

This creates the database `IndusWeaveHR` if needed and runs, in order: raw load -> staging -> warehouse -> the ten questions ->
bonus funnel, with the data quality checks after each load. It takes about 2 minutes (89 seconds on the development machine)
and exits non-zero if any check fails.
Re-running is safe: the raw load is idempotent and every later table is rebuilt.

Settings (environment variables, all optional):

| Variable | Default | Meaning |
|---|---|---|
| `HR_SQL_SERVER` | `localhost` | server or `host\instance` |
| `HR_DB` | `IndusWeaveHR` | database to create / use |
| `HR_DATA_DIR` | `./data` | folder with the raw files |
| `HR_SQL_USER`, `HR_SQL_PASSWORD` | unset | SQL login; leave unset for Windows authentication |
| `HR_ODBC_DRIVER` | `ODBC Driver 18 for SQL Server` | use `ODBC Driver 17 for SQL Server` if 18 is not installed |

Partial runs: `python run_pipeline.py --from staging`, or `--only raw|staging|warehouse|analytics|bonus`.
Data quality alone: `python -m quality.dq_checks`. Redraw the ER diagram: `python warehouse/make_erd.py`.

## Layout

```
run_pipeline.py            one-command rebuild            config.py, db.py   settings and database helpers
ingestion/load_raw.py      Stage 1  raw schema, all text, _source_file/_loaded_at/_row_hash, idempotent, row-count log
transform/                 Stage 2-3
    clock_drift.py         finds the device whose clock is off and writes the correction
    10_staging_masters.sql employees (dedupe + merge log), departments, history periods, shifts, holidays, roster
    20_staging_punches.sql device mapping, rejected punches, 2-minute de-duplication
    30_staging_leave_ot_pay.sql  leave JSON flattened (requests, approval steps, leave days), overtime, payroll
    40_attendance_daily.sql staging.attendance_daily
warehouse/                 Stage 4
    ddl/01_dimensions.sql, 02_facts.sql, 03_views.sql    load_warehouse.sql    erd.png, erd.dbml
analytics/q01 ... q10 .sql Stage 5  one file per question, results/*.csv    bonus_recruitment_funnel.py
quality/dq_checks.py       Stage 6  174 checks -> dq.dq_results
presentation/              cfo_findings.md, slides.pdf
```

Schemas in the database: `raw` (as delivered), `staging` (typed, cleaned, logs of everything removed), `warehouse` (star schema),
`dq` (`dq_results`, one row per check per run).

## How the stages work

**Stage 1 - raw.** Every file is loaded as text, nothing trimmed or converted. Each table gets `_source_file`, `_loaded_at`,
`_row_hash`. A row is inserted only if the same (`_source_file`, `_row_hash`, `_dup_seq`) is not already there (`_dup_seq` numbers
identical rows inside one file), so running the loader twice adds nothing, while a new file or new rows appended to a file
(e.g. a seventh month of punches) load incrementally. JSON files are stored one record per row. Row counts per file and per
table are logged to `raw.load_log` and compared; a mismatch stops the pipeline.

**Stage 2 - staging.** Typed tables, ISO dates (`YYYY-MM-DD`, `DD/MM/YYYY`, `DD-Mon-YYYY` all parsed), trimmed text, canonical
department names. Nothing is silently dropped: every removed row is in a log table, so
`raw rows = staging rows + rejected / merged rows` holds for every table.

| Planted issue | What we found | Where it is handled |
|---|---|---|
| Duplicate employees | 1,316 rows for 1,266 people; 50 older rows dropped | `staging.employee_merge_log` (kept / dropped row, what differed) |
| Mixed dates, department text | 3 date formats; case, spaces, old names (Processing -> Finishing, Procurement -> Supply Chain) | `staging.fn_parse_date`, join to `staging.departments` on name or previous name |
| Unreliable `effective_to` | disagrees with the rule for 37 employees; also one same-date Hire + Salary Revision tie (E11259, resolved to the non-Hire record, confirmed by payroll BASIC) | `staging.employment_history` (valid_to rebuilt), `staging.history_rejected` |
| Missing roster weeks | 2,075 employee-weeks filled from the previous week | `staging.employee_shift_week.inferred_from_previous_week` |
| Unmapped punches | 6,962 punches from 40 device users (contractors / visitors) | `staging.rejected_punches` with a reason |
| Duplicate punches | 16,175 within 2 minutes (no chains, none at exactly 120 s) | `staging.duplicate_punches` (points at the kept punch) |
| Device clock off | `DEV-SITE-01` is +60 minutes from 2026-07-01; 45,803 punches corrected | `staging.device_clock_correction`, `staging.device_clock_diagnostics` |
| Leave JSON | 5,372 requests, 10,125 approval steps; 4,282 requests count (both steps Approved, never cancelled); 8,604 leave days after removing Sundays and plant holidays | `staging.leave_requests`, `leave_approval_steps`, `leave_days` |
| Night shifts | morning punches belong to the day the shift started | `staging.punch_shift_date` |

**How the faulty clock was found** (`transform/clock_drift.py`). Each morning every device sees the same early-arrival cluster.
For each device and day we take the 5th percentile of punch times between 03:00 and 12:00, compare it with that device's own
first-four-weeks baseline, smooth it, and flag a device whose level sits away from zero for 7+ valid days. Only `DEV-SITE-01`
moves: +60 minutes from 1 July, the other three stay within about 6 minutes. Validation on working-day overtime requests: with
the correction SITE matches the approved hours on 95.4% of requests after 1 July (95.9% before July, Korangi 95.7%); on the raw
file, 0 of 2,801. Sunday / holiday overtime is unaffected by a constant offset, so it is excluded from this test.

**Stage 3 - attendance.** `staging.attendance_daily` has one row per employee per day of employment (217,584 rows). Status
priority, late / early (> 10 min, Present working days only) and overtime (after shift end on working days, all hours on Sundays
and holidays, rounded down to half-hours from exact seconds) follow rules 12-15. Worked hours, late minutes and early-departure
minutes are included. Every one of the 322,143 clean punches lands on exactly one attendance row.

**Stage 4 - warehouse.** Star schema with enforced primary and foreign keys (`warehouse/erd.png`):
`dim_employee` (SCD Type 2 from employment history; `valid_to = 9999-12-31` is the open version, join with
`fact_date BETWEEN valid_from AND valid_to`), `dim_department`, `dim_shift`, `dim_date`, and the facts `fact_attendance_daily`,
`fact_leave_day`, `fact_overtime_approved` (Approved requests only), `fact_payroll_line`. Attendance, leave and overtime belong
to the Workforce module and payroll consumes them, so every fact carries `employee_key` (the version that applied on its
reference date) and `department_key`; payroll lines use the last day of the pay month, or the last working day for leavers.
`warehouse.vw_employee_month` gives the month-end department and headcount flag used by the analytics.

**Stage 5 - the ten questions** (`analytics/q01..q10 .sql`, results in `analytics/results/`). Definitions where the case leaves
room, all stated in each file's header:

| Q | Definition used |
|---|---|
| 1 | headcount by rule 4 at each month end, department on that day; 25 departments x 6 months |
| 2 | separations in the month / ((headcount at previous month end + at this month end) / 2); April opens from 31 March |
| 3 | Absent days / scheduled working days (not Sunday, not plant holiday, not approved leave) |
| 4 | most Present working days with a late arrival; ties (ranks 9-12 all have 45) broken by total late minutes, then emp_id; `late_rank` shows the tie |
| 5 | computed (punches) vs approved (requests) vs paid (OVERTIME payroll units), month-end department |
| 6 | six-month totals per department; listed when paid > computed x 1.15; `months_over_15pct` shows the monthly view |
| 7 | employees with EARNING pay in a month and no Present / Missing Punch day in it; `reason` splits never-mapped, paid after separation, other |
| 8 | payroll month starts after `separation_date`; the separation month itself is pro-rated and legitimate |
| 9 | EARNING lines per employee-month, `LAG` for the month-over-month change |
| 10 | counted Annual leave days in the six months > full-year entitlement |

**Stage 6 - data quality.** `quality/dq_checks.py` runs after each load and appends to `dq.dq_results`: uniqueness and not-null on
every primary key, referential integrity (including that the SCD2 version covers each fact date), raw = staging + rejected /
merged for every table and staging = warehouse, accepted values (attendance status, leave type, pay component, ...), and
business sanity (no negative worked hours, no shift over 16 hours, no overlapping or gapped SCD2 ranges, one attendance row per
employee-day, payroll overtime = approved overtime per employee-month, ...). The latest run: 174 checks, 174 passed.

**Bonus.** `run_pipeline.py` (one command); the raw load is incremental-ready (see Stage 1); recruitment funnel
(`analytics/bonus_recruitment_funnel.py` -> conversion and median days in each stage, plus Applied -> Hired by department).

## Known limits

* SQL Server instead of PostgreSQL (see the note at the top).
* Q3, Q6 and Q7 involve a definition choice (documented above); the CSVs include the numerator and denominator so another
  definition can be derived from them.
* Six employees have no device mapping. By rule 8 and rule 12 they are Absent every day; payroll made no absence deduction for them.
  We report them as a finding rather than guess a mapping.
