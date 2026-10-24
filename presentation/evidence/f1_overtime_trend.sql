/* Finding 1 - evidence: paid overtime rises, worked overtime does not.
   Monthly hours worked (from punches), approved, and paid, plus what the overtime cost in PKR.                      */
WITH worked AS (
    SELECT dd.year_month, SUM(f.overtime_hours) AS worked_hours
    FROM warehouse.fact_attendance_daily f JOIN warehouse.dim_date dd ON dd.date_key = f.date_key
    GROUP BY dd.year_month
),
approved AS (
    SELECT dd.year_month, SUM(o.approved_hours) AS approved_hours
    FROM warehouse.fact_overtime_approved o JOIN warehouse.dim_date dd ON dd.date_key = o.date_key
    GROUP BY dd.year_month
),
paid AS (
    SELECT payroll_month AS year_month, SUM(units) AS paid_hours, SUM(amount) AS overtime_cost_pkr
    FROM warehouse.fact_payroll_line WHERE component = 'OVERTIME' GROUP BY payroll_month
)
SELECT p.year_month, w.worked_hours, a.approved_hours, p.paid_hours, p.overtime_cost_pkr,
       CAST(100.0 * (p.paid_hours - w.worked_hours) / w.worked_hours AS DECIMAL(6,1)) AS paid_vs_worked_pct
FROM paid p JOIN worked w ON w.year_month = p.year_month JOIN approved a ON a.year_month = p.year_month
WHERE p.year_month BETWEEN '2026-04' AND '2026-09'
ORDER BY p.year_month;
