-- Q5. Overtime hours computed from punches vs approved vs paid, by department and month.

WITH months AS (
    SELECT DISTINCT year_month FROM warehouse.dim_date WHERE year_month BETWEEN '2026-04' AND '2026-09'
),
emp_month AS (
    SELECT emp_id, year_month, department_key FROM warehouse.vw_employee_month
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
by_dept AS (
    SELECT em.year_month, em.department_key,
           SUM(ISNULL(c.hours, 0)) AS computed_ot_hours,
           SUM(ISNULL(a.hours, 0)) AS approved_ot_hours,
           SUM(ISNULL(p.hours, 0)) AS paid_ot_hours
    FROM emp_month em
    LEFT JOIN computed c ON c.emp_id = em.emp_id AND c.year_month = em.year_month
    LEFT JOIN approved a ON a.emp_id = em.emp_id AND a.year_month = em.year_month
    LEFT JOIN paid p     ON p.emp_id = em.emp_id AND p.year_month = em.year_month
    GROUP BY em.year_month, em.department_key
)
SELECT m.year_month, d.plant, d.dept_id, d.dept_name,
       CAST(ISNULL(b.computed_ot_hours, 0) AS DECIMAL(10,1)) AS computed_ot_hours,
       CAST(ISNULL(b.approved_ot_hours, 0) AS DECIMAL(10,1)) AS approved_ot_hours,
       CAST(ISNULL(b.paid_ot_hours, 0)     AS DECIMAL(10,1)) AS paid_ot_hours,
       CAST(ISNULL(b.paid_ot_hours, 0) - ISNULL(b.computed_ot_hours, 0) AS DECIMAL(10,1)) AS paid_minus_computed,
       CAST(100.0 * (ISNULL(b.paid_ot_hours, 0) - ISNULL(b.computed_ot_hours, 0)) / NULLIF(b.computed_ot_hours, 0) AS DECIMAL(8,2)) AS paid_vs_computed_pct
FROM months m
CROSS JOIN warehouse.dim_department d
LEFT JOIN by_dept b ON b.year_month = m.year_month AND b.department_key = d.department_key
ORDER BY m.year_month, d.plant, d.dept_id;
