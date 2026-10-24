-- Q3. Absenteeism rate by plant and month, excluding approved leave.

SELECT dd.year_month,
       e.plant,
       SUM(CASE WHEN f.status = 'Absent' THEN 1 ELSE 0 END)                                AS absent_days,
       SUM(CASE WHEN f.is_working_day = 1 AND f.status <> 'On Leave' THEN 1 ELSE 0 END)    AS scheduled_working_days,
       CAST(100.0 * SUM(CASE WHEN f.status = 'Absent' THEN 1 ELSE 0 END)
            / NULLIF(SUM(CASE WHEN f.is_working_day = 1 AND f.status <> 'On Leave' THEN 1 ELSE 0 END), 0) AS DECIMAL(6,2)) AS absenteeism_rate_pct
FROM warehouse.fact_attendance_daily f
JOIN warehouse.dim_employee e ON e.employee_key = f.employee_key
JOIN warehouse.dim_date dd    ON dd.date_key = f.date_key
GROUP BY dd.year_month, e.plant
ORDER BY dd.year_month, e.plant;
