-- Q4. The 10 employees with the most late arrivals, and their department.

WITH late AS (
    SELECT e.emp_id,
           SUM(CAST(f.is_late AS INT)) AS late_arrivals,
           SUM(f.late_minutes)         AS total_late_minutes
    FROM warehouse.fact_attendance_daily f
    JOIN warehouse.dim_employee e ON e.employee_key = f.employee_key
    GROUP BY e.emp_id
),
ranked AS (
    SELECT emp_id, late_arrivals, total_late_minutes,
           RANK() OVER (ORDER BY late_arrivals DESC) AS late_rank,
           ROW_NUMBER() OVER (ORDER BY late_arrivals DESC, total_late_minutes DESC, emp_id) AS pick
    FROM late
)
SELECT r.pick AS position, r.late_rank, r.emp_id, cur.full_name, d.dept_id, d.dept_name, d.plant,
       r.late_arrivals, r.total_late_minutes
FROM ranked r
JOIN warehouse.dim_employee cur ON cur.emp_id = r.emp_id AND cur.is_current = 1
JOIN warehouse.dim_department d ON d.department_key = cur.department_key
WHERE r.pick <= 10
ORDER BY r.pick;
