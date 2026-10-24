-- 40_attendance_daily.sql - Stage 3: staging.attendance_daily

DROP TABLE IF EXISTS staging.punch_shift_date;


SELECT p.emp_id, p.punch_id, p.punch_time,
       CAST(p.punch_time AS DATE) AS d,
       DATEADD(DAY, -1, CAST(p.punch_time AS DATE)) AS d_prev,
       DATEPART(HOUR, p.punch_time) * 60 + DATEPART(MINUTE, p.punch_time) AS mins,
       DATEADD(DAY, -(DATEDIFF(DAY, '1900-01-01', CAST(p.punch_time AS DATE)) % 7), CAST(p.punch_time AS DATE)) AS wk_today,
       DATEADD(DAY, -(DATEDIFF(DAY, '1900-01-01', DATEADD(DAY, -1, CAST(p.punch_time AS DATE))) % 7), DATEADD(DAY, -1, CAST(p.punch_time AS DATE))) AS wk_prev
INTO #pp
FROM staging.punches p;
CREATE CLUSTERED INDEX ix_pp ON #pp (emp_id, d);


SELECT DISTINCT emp_id, CAST(punch_time AS DATE) AS d INTO #evening_days
FROM staging.punches WHERE DATEPART(HOUR, punch_time) >= 18;
CREATE UNIQUE CLUSTERED INDEX ix_evening_days ON #evening_days (emp_id, d);


SELECT pp.emp_id, pp.punch_id, pp.punch_time,
       CASE WHEN pp.mins < 12 * 60 AND s1.shift_code = 'NIGHT'
                 AND (s0.shift_code = 'NIGHT' OR ev.emp_id IS NOT NULL)
            THEN pp.d_prev ELSE pp.d END AS shift_date
INTO staging.punch_shift_date
FROM #pp pp
LEFT JOIN staging.employee_shift_week s0 ON s0.emp_id = pp.emp_id AND s0.week_start = pp.wk_today
LEFT JOIN staging.employee_shift_week s1 ON s1.emp_id = pp.emp_id AND s1.week_start = pp.wk_prev
LEFT JOIN #evening_days ev ON ev.emp_id = pp.emp_id AND ev.d = pp.d_prev;
DROP TABLE #pp;
DROP TABLE #evening_days;
ALTER TABLE staging.punch_shift_date ALTER COLUMN punch_id VARCHAR(20) NOT NULL;
ALTER TABLE staging.punch_shift_date ADD CONSTRAINT pk_stg_punch_shift_date PRIMARY KEY (punch_id);
CREATE INDEX ix_stg_psd ON staging.punch_shift_date (emp_id, shift_date);
GO

DROP TABLE IF EXISTS staging.attendance_daily;
;WITH emp_day AS (
    SELECT e.emp_id, e.plant, c.d AS att_date, c.is_sunday, c.week_start
    FROM staging.employees e
    JOIN staging.calendar c
      ON c.d >= CASE WHEN e.hire_date > '2026-04-01' THEN e.hire_date ELSE CAST('2026-04-01' AS DATE) END
     AND c.d <= CASE WHEN e.separation_date IS NULL OR e.separation_date > '2026-09-30' THEN CAST('2026-09-30' AS DATE) ELSE e.separation_date END),
agg AS (
    SELECT emp_id, shift_date, COUNT(*) AS n_punches, MIN(punch_time) AS first_punch, MAX(punch_time) AS last_punch
    FROM staging.punch_shift_date GROUP BY emp_id, shift_date),
base AS (
    SELECT ed.emp_id, ed.plant, ed.att_date, ed.is_sunday, h.dept_id, ws.shift_code,
           ISNULL(a.n_punches, 0) AS n_punches,
           a.first_punch AS check_in,
           CASE WHEN a.n_punches >= 2 THEN a.last_punch END AS check_out,
           hol.holiday_name, ld.leave_type,
           CASE WHEN ld.emp_id IS NOT NULL THEN 1 ELSE 0 END AS on_leave
    FROM emp_day ed
    LEFT JOIN staging.employment_history h ON h.emp_id = ed.emp_id AND h.valid_from <= ed.att_date AND (h.valid_to IS NULL OR ed.att_date <= h.valid_to)
    LEFT JOIN staging.employee_shift_week ws ON ws.emp_id = ed.emp_id AND ws.week_start = ed.week_start
    LEFT JOIN agg a ON a.emp_id = ed.emp_id AND a.shift_date = ed.att_date
    LEFT JOIN staging.holiday_plant hol ON hol.holiday_date = ed.att_date AND hol.plant = ed.plant
    LEFT JOIN staging.leave_days ld ON ld.emp_id = ed.emp_id AND ld.leave_date = ed.att_date),
st AS (
    SELECT *,
           CASE WHEN is_sunday = 1 AND n_punches = 0 THEN 'Weekly Off'
                WHEN holiday_name IS NOT NULL AND n_punches = 0 THEN 'Holiday'
                WHEN on_leave = 1 THEN 'On Leave'
                WHEN n_punches >= 2 THEN 'Present'
                WHEN n_punches = 1 THEN 'Missing Punch'
                ELSE 'Absent' END AS status,
           CASE WHEN is_sunday = 0 AND holiday_name IS NULL THEN 1 ELSE 0 END AS is_working_day
    FROM base),
sh AS (
    SELECT st.*,
           DATEADD(MINUTE, DATEDIFF(MINUTE, CAST('00:00' AS TIME), s.start_time), CAST(st.att_date AS DATETIME2(0))) AS shift_start_dt,
           DATEADD(MINUTE, DATEDIFF(MINUTE, CAST('00:00' AS TIME), s.end_time),
                   DATEADD(DAY, CASE WHEN s.crosses_midnight = 1 THEN 1 ELSE 0 END, CAST(st.att_date AS DATETIME2(0)))) AS shift_end_dt
    FROM st LEFT JOIN staging.shifts s ON s.shift_code = st.shift_code),
calc AS (
    SELECT *,
           CASE WHEN status = 'Present' AND is_working_day = 1 AND DATEDIFF(SECOND, shift_start_dt, check_in) > 600 THEN 1 ELSE 0 END AS is_late,
           CASE WHEN status = 'Present' AND is_working_day = 1 AND DATEDIFF(SECOND, check_out, shift_end_dt) > 600 THEN 1 ELSE 0 END AS is_early_departure
    FROM sh)
SELECT emp_id, att_date, plant, dept_id, shift_code, n_punches, check_in, check_out, status, holiday_name, leave_type,
       is_working_day, is_late, is_early_departure,
       CAST(CASE WHEN n_punches >= 2 THEN DATEDIFF(SECOND, check_in, check_out) / 3600.0 ELSE 0 END AS DECIMAL(6,2)) AS worked_hours,
       CASE WHEN is_late = 1 THEN DATEDIFF(MINUTE, shift_start_dt, check_in) ELSE 0 END AS late_minutes,
       CASE WHEN is_early_departure = 1 THEN DATEDIFF(MINUTE, check_out, shift_end_dt) ELSE 0 END AS early_departure_minutes,
       CAST(CASE WHEN status = 'Present' AND is_working_day = 1 AND DATEDIFF(SECOND, shift_end_dt, check_out) > 0
                      THEN (DATEDIFF(SECOND, shift_end_dt, check_out) / 1800) * 0.5
                 WHEN status = 'Present' AND is_working_day = 0
                      THEN (DATEDIFF(SECOND, check_in, check_out) / 1800) * 0.5
                 ELSE 0 END AS DECIMAL(5,1)) AS overtime_hours,
       CASE WHEN status = 'Present' AND is_working_day = 0 AND DATEDIFF(SECOND, check_in, check_out) >= 1800
                 THEN CASE WHEN is_sunday = 1 THEN 'SUNDAY' ELSE 'HOLIDAY' END
            WHEN status = 'Present' AND is_working_day = 1 AND DATEDIFF(SECOND, shift_end_dt, check_out) >= 1800 THEN 'WORKDAY' END AS overtime_type
INTO staging.attendance_daily
FROM calc;
ALTER TABLE staging.attendance_daily ALTER COLUMN emp_id VARCHAR(20) NOT NULL;
ALTER TABLE staging.attendance_daily ALTER COLUMN att_date DATE NOT NULL;
ALTER TABLE staging.attendance_daily ADD CONSTRAINT pk_stg_attendance_daily PRIMARY KEY (emp_id, att_date);
GO
