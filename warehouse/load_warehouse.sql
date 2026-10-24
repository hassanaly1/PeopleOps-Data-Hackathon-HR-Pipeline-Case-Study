-- load_warehouse.sql - Stage 4: fill the star schema from the staging layer.

INSERT warehouse.dim_date (date_key, full_date, [year], [quarter], [month], month_name, year_month, day_of_month, day_of_week,
                           day_name, is_sunday, week_start, month_start, month_end, is_month_end)
SELECT CONVERT(INT, FORMAT(d, 'yyyyMMdd')), d, YEAR(d), DATEPART(QUARTER, d), MONTH(d), DATENAME(MONTH, d), ym, DAY(d),
       dow + 1, CHOOSE(dow + 1, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'),
       is_sunday, week_start, month_start, month_end, CASE WHEN d = month_end THEN 1 ELSE 0 END
FROM staging.calendar;
GO


INSERT warehouse.dim_department (dept_id, dept_name, plant, cost_center, previous_name, renamed_on)
SELECT dept_id, dept_name, plant, cost_center, previous_name, renamed_on FROM staging.departments ORDER BY dept_id;

INSERT warehouse.dim_shift (shift_code, shift_name, start_time, end_time, crosses_midnight, grace_minutes, applies_to)
SELECT shift_code, name, start_time, end_time, crosses_midnight, grace_minutes, applies_to FROM staging.shifts ORDER BY shift_code;
GO


INSERT warehouse.dim_employee (emp_id, full_name, gender, plant, employment_type, hire_date, separation_date, status,
                               annual_leave_entitlement, has_device_mapping, department_key, designation, grade, basic_salary,
                               change_reason, valid_from, valid_to, is_current)
SELECT h.emp_id, e.full_name, e.gender, e.plant, e.employment_type, e.hire_date, e.separation_date, e.status,
       e.annual_leave_entitlement,
       CASE WHEN EXISTS (SELECT 1 FROM staging.device_mapping m WHERE m.emp_id = h.emp_id) THEN 1 ELSE 0 END,
       d.department_key, h.designation, h.grade, h.basic_salary, h.change_reason,
       h.valid_from, ISNULL(h.valid_to, '9999-12-31'), CASE WHEN h.valid_to IS NULL THEN 1 ELSE 0 END
FROM staging.employment_history h
JOIN staging.employees e ON e.emp_id = h.emp_id
JOIN warehouse.dim_department d ON d.dept_id = h.dept_id
ORDER BY h.emp_id, h.valid_from;
GO


INSERT warehouse.fact_attendance_daily (employee_key, department_key, shift_key, date_key, status, is_working_day, n_punches,
       check_in, check_out, worked_hours, late_minutes, early_departure_minutes, is_late, is_early_departure,
       overtime_hours, overtime_type, holiday_name, leave_type)
SELECT de.employee_key, de.department_key, s.shift_key, dd.date_key, a.status, a.is_working_day, a.n_punches,
       a.check_in, a.check_out, a.worked_hours, a.late_minutes, a.early_departure_minutes, a.is_late, a.is_early_departure,
       a.overtime_hours, a.overtime_type, a.holiday_name, a.leave_type
FROM staging.attendance_daily a
JOIN warehouse.dim_employee de ON de.emp_id = a.emp_id AND a.att_date BETWEEN de.valid_from AND de.valid_to
JOIN warehouse.dim_shift s     ON s.shift_code = a.shift_code
JOIN warehouse.dim_date dd     ON dd.full_date = a.att_date;
GO


INSERT warehouse.fact_leave_day (employee_key, department_key, date_key, leave_type, request_id)
SELECT de.employee_key, de.department_key, dd.date_key, l.leave_type, l.request_id
FROM staging.leave_days l
JOIN warehouse.dim_employee de ON de.emp_id = l.emp_id AND l.leave_date BETWEEN de.valid_from AND de.valid_to
JOIN warehouse.dim_date dd     ON dd.full_date = l.leave_date;
GO


INSERT warehouse.fact_overtime_approved (request_id, employee_key, department_key, date_key, requested_hours, approved_hours,
                                         approver_id, requested_at)
SELECT o.request_id, de.employee_key, de.department_key, dd.date_key, o.requested_hours, o.approved_hours, o.approver_id, o.requested_at
FROM staging.overtime_requests o
JOIN warehouse.dim_employee de ON de.emp_id = o.emp_id AND o.ot_date BETWEEN de.valid_from AND de.valid_to
JOIN warehouse.dim_date dd     ON dd.full_date = o.ot_date
WHERE o.status = 'Approved';
GO


INSERT warehouse.fact_payroll_line (line_id, employee_key, department_key, date_key, payroll_month, component, component_type, units, amount)
SELECT p.line_id, de.employee_key, de.department_key, dd.date_key, p.payroll_month, p.component, p.component_type, p.units, p.amount
FROM staging.payroll_lines p
JOIN staging.employees e ON e.emp_id = p.emp_id
JOIN staging.calendar c  ON c.ym = p.payroll_month AND c.d = c.month_end
JOIN warehouse.dim_employee de ON de.emp_id = p.emp_id
     AND (CASE WHEN e.separation_date IS NOT NULL AND e.separation_date <= c.month_end THEN e.separation_date ELSE c.month_end END)
         BETWEEN de.valid_from AND de.valid_to
JOIN warehouse.dim_date dd ON dd.full_date = c.month_end;
GO
