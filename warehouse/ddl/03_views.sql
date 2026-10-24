-- 03_views.sql - Stage 4: helper view for month-end reporting (run after load_warehouse.sql).

CREATE OR ALTER VIEW warehouse.vw_employee_month
AS
SELECT de.emp_id, de.employee_key, de.department_key, m.year_month, m.full_date AS month_end,
       CASE WHEN de.separation_date IS NOT NULL AND de.separation_date <= m.full_date
            THEN de.separation_date ELSE m.full_date END AS reference_date,
       CASE WHEN de.hire_date <= m.full_date AND (de.separation_date IS NULL OR de.separation_date > m.full_date)
            THEN 1 ELSE 0 END AS in_headcount
FROM warehouse.dim_date m
JOIN warehouse.dim_employee de
  ON de.hire_date <= m.full_date
 AND (CASE WHEN de.separation_date IS NOT NULL AND de.separation_date <= m.full_date
           THEN de.separation_date ELSE m.full_date END) BETWEEN de.valid_from AND de.valid_to
WHERE m.is_month_end = 1;
GO
