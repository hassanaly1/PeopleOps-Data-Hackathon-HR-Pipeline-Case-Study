-- Q7. Employees paid in a month with zero attendance in that month.

WITH paid AS (
    SELECT e.emp_id, p.payroll_month AS year_month, SUM(p.amount) AS gross_pay
    FROM warehouse.fact_payroll_line p
    JOIN warehouse.dim_employee e ON e.employee_key = p.employee_key
    WHERE p.component_type = 'EARNING'
    GROUP BY e.emp_id, p.payroll_month
),
attendance AS (
    SELECT e.emp_id, dd.year_month,
           SUM(CASE WHEN f.status IN ('Present', 'Missing Punch') THEN 1 ELSE 0 END) AS attended_days,
           COUNT(*) AS attendance_rows
    FROM warehouse.fact_attendance_daily f
    JOIN warehouse.dim_employee e ON e.employee_key = f.employee_key
    JOIN warehouse.dim_date dd    ON dd.date_key = f.date_key
    GROUP BY e.emp_id, dd.year_month
)
SELECT p.year_month AS payroll_month, p.emp_id, cur.full_name, d.dept_id, d.dept_name, d.plant,
       cur.separation_date,
       p.gross_pay,
       ISNULL(a.attendance_rows, 0) AS attendance_rows,
       CASE WHEN cur.has_device_mapping = 0 THEN 'No biometric device mapping (never punched)'
            WHEN cur.separation_date < DATEFROMPARTS(CAST(LEFT(p.year_month, 4) AS INT), CAST(RIGHT(p.year_month, 2) AS INT), 1)
                 THEN 'Paid after separation'
            ELSE 'Employed but no attended day in the month' END AS reason
FROM paid p
LEFT JOIN attendance a ON a.emp_id = p.emp_id AND a.year_month = p.year_month
JOIN warehouse.dim_employee cur ON cur.emp_id = p.emp_id AND cur.is_current = 1
JOIN warehouse.vw_employee_month em ON em.emp_id = p.emp_id AND em.year_month = p.year_month
JOIN warehouse.dim_department d ON d.department_key = em.department_key
WHERE p.gross_pay > 0
  AND ISNULL(a.attended_days, 0) = 0
ORDER BY p.emp_id, p.year_month;
