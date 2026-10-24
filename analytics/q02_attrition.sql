-- Q2. Monthly attrition rate by department = separations / average headcount.

WITH month_end_headcount AS (
    SELECT year_month, department_key, COUNT(*) AS headcount
    FROM warehouse.vw_employee_month
    WHERE in_headcount = 1
    GROUP BY year_month, department_key
),
months AS (
    SELECT DISTINCT year_month FROM warehouse.dim_date WHERE year_month BETWEEN '2026-03' AND '2026-09'
),
grid AS (
    SELECT m.year_month, d.department_key,
           ISNULL(h.headcount, 0) AS headcount_end,
           ISNULL(LAG(h.headcount) OVER (PARTITION BY d.department_key ORDER BY m.year_month), 0) AS headcount_start
    FROM months m
    CROSS JOIN warehouse.dim_department d
    LEFT JOIN month_end_headcount h ON h.year_month = m.year_month AND h.department_key = d.department_key
),
separations AS (
    SELECT dd.year_month, e.department_key, COUNT(*) AS separations
    FROM warehouse.dim_employee e
    JOIN warehouse.dim_date dd ON dd.full_date = e.separation_date
    WHERE e.separation_date BETWEEN e.valid_from AND e.valid_to
    GROUP BY dd.year_month, e.department_key
)
SELECT g.year_month,
       d.plant,
       d.dept_id,
       d.dept_name,
       ISNULL(s.separations, 0)                     AS separations,
       g.headcount_start,
       g.headcount_end,
       (g.headcount_start + g.headcount_end) / 2.0  AS avg_headcount,
       CAST(100.0 * ISNULL(s.separations, 0) / NULLIF((g.headcount_start + g.headcount_end) / 2.0, 0) AS DECIMAL(6,2)) AS attrition_rate_pct
FROM grid g
JOIN warehouse.dim_department d ON d.department_key = g.department_key
LEFT JOIN separations s ON s.year_month = g.year_month AND s.department_key = g.department_key
WHERE g.year_month >= '2026-04'
ORDER BY g.year_month, d.plant, d.dept_id;
