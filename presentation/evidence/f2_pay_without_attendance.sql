/* Finding 2 - evidence: money paid to people with no attendance.
   Built from the Q7 logic (paid in a month with no attended day); summarised by reason.
   Row-level detail: analytics/results/q07_paid_zero_attendance.csv and q08_paid_after_separation.csv.               */
WITH paid AS (
    SELECT e.emp_id, p.payroll_month AS year_month, SUM(p.amount) AS gross_pay
    FROM warehouse.fact_payroll_line p JOIN warehouse.dim_employee e ON e.employee_key = p.employee_key
    WHERE p.component_type = 'EARNING' GROUP BY e.emp_id, p.payroll_month
),
attended AS (
    SELECT e.emp_id, dd.year_month, SUM(CASE WHEN f.status IN ('Present', 'Missing Punch') THEN 1 ELSE 0 END) AS days
    FROM warehouse.fact_attendance_daily f
    JOIN warehouse.dim_employee e ON e.employee_key = f.employee_key
    JOIN warehouse.dim_date dd ON dd.date_key = f.date_key
    GROUP BY e.emp_id, dd.year_month
)
SELECT CASE WHEN cur.has_device_mapping = 0 THEN 'Active employee with no biometric device and no punches'
            WHEN cur.separation_date < DATEFROMPARTS(CAST(LEFT(p.year_month, 4) AS INT), CAST(RIGHT(p.year_month, 2) AS INT), 1) THEN 'Paid after separation'
            ELSE 'Other' END AS reason,
       COUNT(DISTINCT p.emp_id) AS employees,
       COUNT(*)                 AS employee_months,
       SUM(p.gross_pay)         AS gross_pay_pkr
FROM paid p
LEFT JOIN attended a ON a.emp_id = p.emp_id AND a.year_month = p.year_month
JOIN warehouse.dim_employee cur ON cur.emp_id = p.emp_id AND cur.is_current = 1
WHERE p.gross_pay > 0 AND ISNULL(a.days, 0) = 0
GROUP BY CASE WHEN cur.has_device_mapping = 0 THEN 'Active employee with no biometric device and no punches'
              WHEN cur.separation_date < DATEFROMPARTS(CAST(LEFT(p.year_month, 4) AS INT), CAST(RIGHT(p.year_month, 2) AS INT), 1) THEN 'Paid after separation'
              ELSE 'Other' END
ORDER BY gross_pay_pkr DESC;
