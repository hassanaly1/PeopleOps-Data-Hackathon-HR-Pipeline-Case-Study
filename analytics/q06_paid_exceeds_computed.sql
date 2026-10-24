-- Q6. Departments where paid overtime exceeds computed overtime by more than 15%.

WITH emp_month AS (
    SELECT emp_id, year_month, department_key FROM warehouse.vw_employee_month WHERE year_month BETWEEN '2026-04' AND '2026-09'
),
computed AS (
    SELECT e.emp_id, dd.year_month, SUM(f.overtime_hours) AS hours
    FROM warehouse.fact_attendance_daily f
    JOIN warehouse.dim_employee e ON e.employee_key = f.employee_key
    JOIN warehouse.dim_date dd    ON dd.date_key = f.date_key
    GROUP BY e.emp_id, dd.year_month
),
approved AS (
    SELECT e.emp_id, dd.year_month, SUM(o.approved_hours) AS hours
    FROM warehouse.fact_overtime_approved o
    JOIN warehouse.dim_employee e ON e.employee_key = o.employee_key
    JOIN warehouse.dim_date dd    ON dd.date_key = o.date_key
    GROUP BY e.emp_id, dd.year_month
),
paid AS (
    SELECT e.emp_id, p.payroll_month AS year_month, SUM(p.units) AS hours
    FROM warehouse.fact_payroll_line p
    JOIN warehouse.dim_employee e ON e.employee_key = p.employee_key
    WHERE p.component = 'OVERTIME'
    GROUP BY e.emp_id, p.payroll_month
),
dept_month AS (
    SELECT em.department_key, em.year_month,
           SUM(ISNULL(c.hours, 0)) AS computed_hours,
           SUM(ISNULL(a.hours, 0)) AS approved_hours,
           SUM(ISNULL(p.hours, 0)) AS paid_hours
    FROM emp_month em
    LEFT JOIN computed c ON c.emp_id = em.emp_id AND c.year_month = em.year_month
    LEFT JOIN approved a ON a.emp_id = em.emp_id AND a.year_month = em.year_month
    LEFT JOIN paid p     ON p.emp_id = em.emp_id AND p.year_month = em.year_month
    GROUP BY em.department_key, em.year_month
),
dept_total AS (
    SELECT department_key,
           SUM(computed_hours) AS computed_ot_hours,
           SUM(approved_hours) AS approved_ot_hours,
           SUM(paid_hours)     AS paid_ot_hours,
           SUM(CASE WHEN computed_hours > 0 AND paid_hours > computed_hours * 1.15 THEN 1 ELSE 0 END) AS months_over_15pct
    FROM dept_month
    GROUP BY department_key
)
SELECT d.plant, d.dept_id, d.dept_name,
       CAST(t.computed_ot_hours AS DECIMAL(10,1)) AS computed_ot_hours,
       CAST(t.approved_ot_hours AS DECIMAL(10,1)) AS approved_ot_hours,
       CAST(t.paid_ot_hours     AS DECIMAL(10,1)) AS paid_ot_hours,
       CAST(t.paid_ot_hours - t.computed_ot_hours AS DECIMAL(10,1)) AS excess_paid_hours,
       CAST(100.0 * (t.paid_ot_hours - t.computed_ot_hours) / t.computed_ot_hours AS DECIMAL(8,2)) AS paid_vs_computed_pct,
       t.months_over_15pct
FROM dept_total t
JOIN warehouse.dim_department d ON d.department_key = t.department_key
WHERE t.computed_ot_hours > 0
  AND t.paid_ot_hours > t.computed_ot_hours * 1.15
ORDER BY paid_vs_computed_pct DESC;
