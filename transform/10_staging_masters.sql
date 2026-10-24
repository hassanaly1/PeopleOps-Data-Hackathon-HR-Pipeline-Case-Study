-- 10_staging_masters.sql - Stage 2 (part 1): typed, trimmed, de-duplicated master data.

CREATE OR ALTER FUNCTION staging.fn_parse_date (@s VARCHAR(60))
RETURNS DATE
AS
BEGIN
    SET @s = NULLIF(LTRIM(RTRIM(@s)), '');
    RETURN CASE
        WHEN @s LIKE '____-__-__'  THEN TRY_CONVERT(DATE, @s, 23)
        WHEN @s LIKE '__/__/____'  THEN TRY_CONVERT(DATE, @s, 103)
        WHEN @s LIKE '__-___-____' THEN TRY_CONVERT(DATE, REPLACE(@s, '-', ' '), 106)
        ELSE NULL END;
END
GO


DROP TABLE IF EXISTS staging.plants;
CREATE TABLE staging.plants (plant_code VARCHAR(5) NOT NULL PRIMARY KEY, plant VARCHAR(60) NOT NULL);
INSERT staging.plants VALUES ('HO','Head Office'),('KOR','Korangi Plant'),('SITE','SITE Plant'),('FSD','Faisalabad Plant');
GO


DROP TABLE IF EXISTS staging.calendar;
CREATE TABLE staging.calendar (
    d DATE NOT NULL PRIMARY KEY, dow TINYINT NOT NULL, is_sunday BIT NOT NULL,
    week_start DATE NOT NULL, month_start DATE NOT NULL, month_end DATE NOT NULL, ym CHAR(7) NOT NULL);
;WITH n AS (SELECT TOP (DATEDIFF(DAY, '2026-03-30', '2026-10-31') + 1)
                   DATEADD(DAY, ROW_NUMBER() OVER (ORDER BY (SELECT 1)) - 1, CAST('2026-03-30' AS DATE)) d
            FROM sys.all_objects a CROSS JOIN sys.all_objects b)
INSERT staging.calendar
SELECT d, DATEDIFF(DAY, '1900-01-01', d) % 7,
       CASE WHEN DATEDIFF(DAY, '1900-01-01', d) % 7 = 6 THEN 1 ELSE 0 END,
       DATEADD(DAY, -(DATEDIFF(DAY, '1900-01-01', d) % 7), d),
       DATEFROMPARTS(YEAR(d), MONTH(d), 1), EOMONTH(d), FORMAT(d, 'yyyy-MM')
FROM n;
GO


DROP TABLE IF EXISTS staging.departments;
SELECT CAST(LTRIM(RTRIM(dept_id)) AS VARCHAR(10)) AS dept_id, LTRIM(RTRIM(dept_name)) AS dept_name,
       LTRIM(RTRIM(plant)) AS plant, LTRIM(RTRIM(cost_center)) AS cost_center,
       NULLIF(LTRIM(RTRIM(previous_name)), '') AS previous_name,
       staging.fn_parse_date(renamed_on) AS renamed_on
INTO staging.departments
FROM raw.departments;
ALTER TABLE staging.departments ALTER COLUMN dept_id VARCHAR(10) NOT NULL;
ALTER TABLE staging.departments ADD CONSTRAINT pk_stg_departments PRIMARY KEY (dept_id);
GO


DROP TABLE IF EXISTS staging.shifts;
SELECT j.shift_code, j.name, CAST(j.start_time AS TIME(0)) AS start_time, CAST(j.end_time AS TIME(0)) AS end_time,
       j.crosses_midnight, j.grace_minutes, j.applies_to
INTO staging.shifts
FROM raw.shifts r
CROSS APPLY OPENJSON(r.record_json) WITH (
    shift_code VARCHAR(10) '$.shift_code', name VARCHAR(40) '$.name',
    start_time VARCHAR(8) '$.start_time', end_time VARCHAR(8) '$.end_time',
    crosses_midnight BIT '$.crosses_midnight', grace_minutes INT '$.grace_minutes', applies_to VARCHAR(80) '$.applies_to') j;
ALTER TABLE staging.shifts ALTER COLUMN shift_code VARCHAR(10) NOT NULL;
ALTER TABLE staging.shifts ADD CONSTRAINT pk_stg_shifts PRIMARY KEY (shift_code);
GO


DROP TABLE IF EXISTS staging.holidays;
SELECT staging.fn_parse_date(holiday_date) AS holiday_date, LTRIM(RTRIM(holiday_name)) AS holiday_name, UPPER(LTRIM(RTRIM(scope))) AS scope
INTO staging.holidays FROM raw.holidays;
GO
DROP TABLE IF EXISTS staging.holiday_plant;
SELECT h.holiday_date, h.holiday_name, p.plant
INTO staging.holiday_plant
FROM staging.holidays h JOIN staging.plants p ON h.scope = 'ALL' OR p.plant_code = h.scope;
ALTER TABLE staging.holiday_plant ALTER COLUMN holiday_date DATE NOT NULL;
ALTER TABLE staging.holiday_plant ALTER COLUMN plant VARCHAR(60) NOT NULL;
ALTER TABLE staging.holiday_plant ADD CONSTRAINT pk_stg_holiday_plant PRIMARY KEY (holiday_date, plant);
GO


DROP TABLE IF EXISTS staging.employee_merge_log;
DROP TABLE IF EXISTS staging.employees;
;WITH ranked AS (
    SELECT r.*, TRY_CONVERT(DATETIME2(0), r.updated_at) AS updated_ts,
           ROW_NUMBER() OVER (PARTITION BY r.emp_id ORDER BY TRY_CONVERT(DATETIME2(0), r.updated_at) DESC, r._row_id DESC) AS rn
    FROM raw.employees r)
SELECT LTRIM(RTRIM(k.emp_id)) AS emp_id, LTRIM(RTRIM(k.full_name)) AS full_name, UPPER(LTRIM(RTRIM(k.gender))) AS gender,
       staging.fn_parse_date(k.date_of_birth) AS date_of_birth, LOWER(LTRIM(RTRIM(k.email))) AS email, LTRIM(RTRIM(k.phone)) AS phone,
       LTRIM(RTRIM(k.plant)) AS plant, d.dept_id AS dept_id_on_profile, d.dept_name AS department,
       LTRIM(RTRIM(k.designation)) AS designation, UPPER(LTRIM(RTRIM(k.grade))) AS grade, LTRIM(RTRIM(k.employment_type)) AS employment_type,
       staging.fn_parse_date(k.hire_date) AS hire_date, staging.fn_parse_date(k.separation_date) AS separation_date,
       LTRIM(RTRIM(k.status)) AS status, TRY_CONVERT(INT, k.annual_leave_entitlement) AS annual_leave_entitlement,
       k.updated_ts AS updated_at, k._row_id AS source_row_id
INTO staging.employees
FROM ranked k
LEFT JOIN staging.departments d ON d.plant = LTRIM(RTRIM(k.plant))
     AND LTRIM(RTRIM(k.department)) IN (d.dept_name, ISNULL(d.previous_name, '~'))
WHERE k.rn = 1;
ALTER TABLE staging.employees ALTER COLUMN emp_id VARCHAR(20) NOT NULL;
ALTER TABLE staging.employees ADD CONSTRAINT pk_stg_employees PRIMARY KEY (emp_id);
GO

CREATE TABLE staging.employee_merge_log (
    emp_id VARCHAR(20) NOT NULL, kept_row_id INT NOT NULL, kept_updated_at DATETIME2(0),
    dropped_row_id INT NOT NULL PRIMARY KEY, dropped_updated_at DATETIME2(0),
    reason VARCHAR(200) NOT NULL, columns_that_differ VARCHAR(400) NULL);
;WITH ranked AS (
    SELECT r.*, TRY_CONVERT(DATETIME2(0), r.updated_at) AS updated_ts,
           ROW_NUMBER() OVER (PARTITION BY r.emp_id ORDER BY TRY_CONVERT(DATETIME2(0), r.updated_at) DESC, r._row_id DESC) AS rn
    FROM raw.employees r)
INSERT staging.employee_merge_log
SELECT LTRIM(RTRIM(k.emp_id)), k._row_id, k.updated_ts, o._row_id, o.updated_ts,
       'Duplicate emp_id: older updated_at dropped, latest kept',
       NULLIF(CONCAT_WS(', ',
         CASE WHEN LTRIM(RTRIM(k.full_name)) <> LTRIM(RTRIM(o.full_name)) THEN 'full_name' END,
         CASE WHEN LTRIM(RTRIM(k.department)) <> LTRIM(RTRIM(o.department)) THEN 'department (text differs: ' + LTRIM(RTRIM(o.department)) + ' -> ' + LTRIM(RTRIM(k.department)) + ')' END,
         CASE WHEN LTRIM(RTRIM(k.designation)) <> LTRIM(RTRIM(o.designation)) THEN 'designation' END,
         CASE WHEN LTRIM(RTRIM(k.grade)) <> LTRIM(RTRIM(o.grade)) THEN 'grade' END,
         CASE WHEN LTRIM(RTRIM(k.plant)) <> LTRIM(RTRIM(o.plant)) THEN 'plant' END,
         CASE WHEN LTRIM(RTRIM(k.employment_type)) <> LTRIM(RTRIM(o.employment_type)) THEN 'employment_type' END,
         CASE WHEN ISNULL(staging.fn_parse_date(k.hire_date), '1900-01-01') <> ISNULL(staging.fn_parse_date(o.hire_date), '1900-01-01') THEN 'hire_date' END,
         CASE WHEN ISNULL(staging.fn_parse_date(k.separation_date), '1900-01-01') <> ISNULL(staging.fn_parse_date(o.separation_date), '1900-01-01') THEN 'separation_date' END,
         CASE WHEN LTRIM(RTRIM(k.status)) <> LTRIM(RTRIM(o.status)) THEN 'status' END,
         CASE WHEN k.annual_leave_entitlement <> o.annual_leave_entitlement THEN 'annual_leave_entitlement' END), '')
FROM ranked k JOIN ranked o ON o.emp_id = k.emp_id AND o.rn > 1
WHERE k.rn = 1;
GO


DROP TABLE IF EXISTS staging.history_rejected;
DROP TABLE IF EXISTS staging.employment_history;
SELECT h.*, CASE WHEN h.pick = 1 THEN 'kept' ELSE 'Same effective_from as a later change on that date; Hire record superseded' END AS decision
INTO #h
FROM (SELECT r._row_id, LTRIM(RTRIM(r.emp_id)) AS emp_id, staging.fn_parse_date(r.effective_from) AS valid_from,
             staging.fn_parse_date(r.effective_to) AS raw_effective_to, LTRIM(RTRIM(r.dept_id)) AS dept_id,
             LTRIM(RTRIM(r.designation)) AS designation, UPPER(LTRIM(RTRIM(r.grade))) AS grade,
             TRY_CONVERT(DECIMAL(12,2), r.basic_salary) AS basic_salary, LTRIM(RTRIM(r.change_reason)) AS change_reason,
             ROW_NUMBER() OVER (PARTITION BY LTRIM(RTRIM(r.emp_id)), staging.fn_parse_date(r.effective_from)
                                ORDER BY CASE WHEN LTRIM(RTRIM(r.change_reason)) = 'Hire' THEN 1 ELSE 0 END, r._row_id DESC) AS pick
      FROM raw.employment_history r) h;

SELECT emp_id, valid_from, DATEADD(DAY, -1, LEAD(valid_from) OVER (PARTITION BY emp_id ORDER BY valid_from)) AS valid_to,
       raw_effective_to, dept_id, designation, grade, basic_salary, change_reason, _row_id AS source_row_id
INTO staging.employment_history
FROM #h WHERE pick = 1;
ALTER TABLE staging.employment_history ALTER COLUMN emp_id VARCHAR(20) NOT NULL;
ALTER TABLE staging.employment_history ALTER COLUMN valid_from DATE NOT NULL;
ALTER TABLE staging.employment_history ADD CONSTRAINT pk_stg_employment_history PRIMARY KEY (emp_id, valid_from);

SELECT _row_id AS source_row_id, emp_id, valid_from AS effective_from, change_reason, basic_salary, decision AS reason
INTO staging.history_rejected FROM #h WHERE pick > 1;
DROP TABLE #h;
GO


DROP TABLE IF EXISTS staging.shift_roster;
SELECT LTRIM(RTRIM(emp_id)) AS emp_id, staging.fn_parse_date(week_start) AS week_start, UPPER(LTRIM(RTRIM(shift_code))) AS shift_code
INTO staging.shift_roster FROM raw.shift_roster;
ALTER TABLE staging.shift_roster ALTER COLUMN emp_id VARCHAR(20) NOT NULL;
ALTER TABLE staging.shift_roster ALTER COLUMN week_start DATE NOT NULL;
ALTER TABLE staging.shift_roster ADD CONSTRAINT pk_stg_shift_roster PRIMARY KEY (emp_id, week_start);
GO


DROP TABLE IF EXISTS staging.employee_shift_week;
;WITH weeks AS (SELECT DISTINCT week_start FROM staging.calendar),
span AS (SELECT e.emp_id,
                (SELECT week_start FROM staging.calendar WHERE d = CASE WHEN e.hire_date < '2026-03-30' THEN CAST('2026-03-30' AS DATE) ELSE e.hire_date END) AS first_wk
         FROM staging.employees e)
SELECT s.emp_id, w.week_start,
       COALESCE(r.shift_code, prev.shift_code) AS shift_code,
       CASE WHEN r.shift_code IS NULL THEN 1 ELSE 0 END AS inferred_from_previous_week
INTO staging.employee_shift_week
FROM span s
JOIN weeks w ON w.week_start >= s.first_wk
LEFT JOIN staging.shift_roster r ON r.emp_id = s.emp_id AND r.week_start = w.week_start
OUTER APPLY (SELECT TOP 1 r2.shift_code FROM staging.shift_roster r2
             WHERE r2.emp_id = s.emp_id AND r2.week_start < w.week_start ORDER BY r2.week_start DESC) prev;
ALTER TABLE staging.employee_shift_week ALTER COLUMN emp_id VARCHAR(20) NOT NULL;
ALTER TABLE staging.employee_shift_week ALTER COLUMN week_start DATE NOT NULL;
ALTER TABLE staging.employee_shift_week ADD CONSTRAINT pk_stg_employee_shift_week PRIMARY KEY (emp_id, week_start);
GO
