-- Q10. Employees whose approved Annual leave days in these six months already exceed their full-year entitlement.

WITH annual AS (
    SELECT e.emp_id, COUNT(*) AS annual_days_taken
    FROM warehouse.fact_leave_day l
    JOIN warehouse.dim_employee e ON e.employee_key = l.employee_key
    WHERE l.leave_type = 'Annual'
    GROUP BY e.emp_id
)
SELECT cur.emp_id, cur.full_name, d.dept_id, d.dept_name, d.plant,
       cur.annual_leave_entitlement,
       a.annual_days_taken,
       a.annual_days_taken - cur.annual_leave_entitlement AS days_over_entitlement
FROM annual a
JOIN warehouse.dim_employee cur ON cur.emp_id = a.emp_id AND cur.is_current = 1
JOIN warehouse.dim_department d ON d.department_key = cur.department_key
WHERE a.annual_days_taken > cur.annual_leave_entitlement
ORDER BY days_over_entitlement DESC, cur.emp_id;
