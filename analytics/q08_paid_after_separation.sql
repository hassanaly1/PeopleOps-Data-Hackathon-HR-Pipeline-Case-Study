-- Q8. Employees still receiving pay after their separation date.

WITH after_sep AS (
    SELECT e.emp_id, p.payroll_month,
           SUM(CASE WHEN p.component_type = 'EARNING'   THEN p.amount ELSE 0 END) AS gross_pay,
           SUM(CASE WHEN p.component_type = 'DEDUCTION' THEN p.amount ELSE 0 END) AS deductions
    FROM warehouse.fact_payroll_line p
    JOIN warehouse.dim_employee e ON e.employee_key = p.employee_key
    WHERE e.separation_date IS NOT NULL
      AND DATEFROMPARTS(CAST(LEFT(p.payroll_month, 4) AS INT), CAST(RIGHT(p.payroll_month, 2) AS INT), 1) > e.separation_date
    GROUP BY e.emp_id, p.payroll_month
)
SELECT a.emp_id, cur.full_name, d.dept_id, d.dept_name, d.plant, cur.separation_date,
       COUNT(*)                AS months_paid_after_separation,
       MIN(a.payroll_month)    AS first_month_paid_after,
       MAX(a.payroll_month)    AS last_month_paid_after,
       SUM(a.gross_pay)        AS gross_pay_after_separation,
       SUM(a.gross_pay - a.deductions) AS net_pay_after_separation
FROM after_sep a
JOIN warehouse.dim_employee cur ON cur.emp_id = a.emp_id AND cur.is_current = 1
JOIN warehouse.dim_employee last_ver ON last_ver.emp_id = a.emp_id AND cur.separation_date BETWEEN last_ver.valid_from AND last_ver.valid_to
JOIN warehouse.dim_department d ON d.department_key = last_ver.department_key
GROUP BY a.emp_id, cur.full_name, d.dept_id, d.dept_name, d.plant, cur.separation_date
ORDER BY gross_pay_after_separation DESC, a.emp_id;
