-- Q9. Payroll cost per employee by department, with month-over-month change.

WITH cost AS (
    SELECT e.emp_id, p.payroll_month, p.department_key,
           SUM(CASE WHEN p.component_type = 'EARNING' THEN p.amount ELSE 0 END) AS payroll_cost
    FROM warehouse.fact_payroll_line p
    JOIN warehouse.dim_employee e ON e.employee_key = p.employee_key
    GROUP BY e.emp_id, p.payroll_month, p.department_key
),
with_prev AS (
    SELECT *, LAG(payroll_cost) OVER (PARTITION BY emp_id ORDER BY payroll_month) AS prev_month_cost,
              LAG(payroll_month) OVER (PARTITION BY emp_id ORDER BY payroll_month) AS prev_month
    FROM cost
)
SELECT w.payroll_month, d.plant, d.dept_id, d.dept_name, w.emp_id, cur.full_name,
       w.payroll_cost,
       w.prev_month_cost,
       w.payroll_cost - w.prev_month_cost AS mom_change,
       CAST(100.0 * (w.payroll_cost - w.prev_month_cost) / NULLIF(w.prev_month_cost, 0) AS DECIMAL(8,2)) AS mom_change_pct
FROM with_prev w
JOIN warehouse.dim_department d ON d.department_key = w.department_key
JOIN warehouse.dim_employee cur ON cur.emp_id = w.emp_id AND cur.is_current = 1
ORDER BY d.plant, d.dept_id, w.emp_id, w.payroll_month;
