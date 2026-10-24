-- Q1. Month-end headcount by plant and department, for all six months.

WITH months AS (
    SELECT DISTINCT year_month FROM warehouse.dim_date WHERE year_month BETWEEN '2026-04' AND '2026-09'
),
headcount AS (
    SELECT year_month, department_key, COUNT(*) AS headcount
    FROM warehouse.vw_employee_month
    WHERE in_headcount = 1
    GROUP BY year_month, department_key
)
SELECT m.year_month,
       d.plant,
       d.dept_id,
       d.dept_name,
       ISNULL(h.headcount, 0) AS headcount
FROM months m
CROSS JOIN warehouse.dim_department d
LEFT JOIN headcount h ON h.year_month = m.year_month AND h.department_key = d.department_key
ORDER BY m.year_month, d.plant, d.dept_id;
