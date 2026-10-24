/* Finding 1 - evidence: approved overtime that punches do not support, by department and approver.
   For each approved request: hours approved minus overtime actually worked that day (when positive) = overstated hours.
   Valued at the employee's own overtime rate that month (OVERTIME payroll amount / units).                          */
WITH rate AS (
    SELECT e.emp_id, p.payroll_month, p.amount / NULLIF(p.units, 0) AS pkr_per_hour
    FROM warehouse.fact_payroll_line p
    JOIN warehouse.dim_employee e ON e.employee_key = p.employee_key
    WHERE p.component = 'OVERTIME'
),
req AS (
    SELECT e.emp_id, dd.year_month, d.dept_id, d.dept_name, d.plant, o.approver_id, o.approved_hours, f.overtime_hours AS worked_hours,
           CASE WHEN o.approved_hours > f.overtime_hours THEN o.approved_hours - f.overtime_hours ELSE 0 END AS overstated_hours
    FROM warehouse.fact_overtime_approved o
    JOIN warehouse.fact_attendance_daily f ON f.employee_key = o.employee_key AND f.date_key = o.date_key
    JOIN warehouse.dim_employee e   ON e.employee_key = o.employee_key
    JOIN warehouse.dim_department d ON d.department_key = o.department_key
    JOIN warehouse.dim_date dd      ON dd.date_key = o.date_key
)
SELECT r.dept_id, r.dept_name, r.plant, r.approver_id,
       COUNT(*)                                             AS approved_requests,
       SUM(CASE WHEN r.overstated_hours > 0 THEN 1 ELSE 0 END) AS requests_overstated,
       COUNT(DISTINCT CASE WHEN r.overstated_hours > 0 THEN r.emp_id END) AS employees_overstated,
       SUM(r.overstated_hours)                              AS overstated_hours,
       CAST(SUM(r.overstated_hours * ISNULL(x.pkr_per_hour, 0)) AS DECIMAL(14,0)) AS overstated_pkr
FROM req r
LEFT JOIN rate x ON x.emp_id = r.emp_id AND x.payroll_month = r.year_month
GROUP BY r.dept_id, r.dept_name, r.plant, r.approver_id
HAVING SUM(r.overstated_hours) > 0
ORDER BY overstated_pkr DESC;
