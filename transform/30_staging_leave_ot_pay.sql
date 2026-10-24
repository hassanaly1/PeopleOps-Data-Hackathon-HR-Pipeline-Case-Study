-- 30_staging_leave_ot_pay.sql - Stage 2 (part 3): leave, overtime, payroll, applications.

DROP TABLE IF EXISTS staging.leave_approval_steps;
DROP TABLE IF EXISTS staging.leave_requests;
SELECT j.request_id, j.emp_id, j.plant, j.leave_type,
       TRY_CONVERT(DATE, j.leave_from, 23) AS leave_from, TRY_CONVERT(DATE, j.leave_to, 23) AS leave_to,
       j.days_requested, TRY_CONVERT(DATETIME2(0), j.submitted_at, 126) AS submitted_at,
       TRY_CONVERT(DATETIME2(0), NULLIF(j.cancelled_at, ''), 126) AS cancelled_at,
       r._row_id AS source_row_id, j.approvals_json
INTO #lr
FROM raw.leave_requests r
CROSS APPLY OPENJSON(r.record_json) WITH (
    request_id VARCHAR(20) '$.request_id', emp_id VARCHAR(20) '$.employee.emp_id', plant VARCHAR(60) '$.employee.plant',
    leave_type VARCHAR(20) '$.leave.type', leave_from VARCHAR(10) '$.leave.from', leave_to VARCHAR(10) '$.leave.to',
    days_requested INT '$.leave.days_requested', submitted_at VARCHAR(30) '$.submitted_at', cancelled_at VARCHAR(30) '$.cancelled_at',
    approvals_json NVARCHAR(MAX) '$.approvals' AS JSON) j;


SELECT l.request_id, a.step, a.approver_role, a.approver_id, a.action, TRY_CONVERT(DATETIME2(0), a.acted_at, 126) AS acted_at
INTO staging.leave_approval_steps
FROM #lr l
CROSS APPLY OPENJSON(l.approvals_json) WITH (
    step INT '$.step', approver_role VARCHAR(20) '$.approver_role', approver_id VARCHAR(20) '$.approver_id',
    action VARCHAR(20) '$.action', acted_at VARCHAR(30) '$.acted_at') a;
ALTER TABLE staging.leave_approval_steps ALTER COLUMN request_id VARCHAR(20) NOT NULL;
ALTER TABLE staging.leave_approval_steps ALTER COLUMN step INT NOT NULL;
ALTER TABLE staging.leave_approval_steps ADD CONSTRAINT pk_stg_leave_approval_steps PRIMARY KEY (request_id, step);


SELECT l.request_id, l.emp_id, l.plant, l.leave_type, l.leave_from, l.leave_to, l.days_requested, l.submitted_at, l.cancelled_at,
       s1.action AS manager_action, s2.action AS hr_action,
       CASE WHEN s1.action = 'Approved' AND s2.action = 'Approved' AND l.cancelled_at IS NULL THEN 1 ELSE 0 END AS is_counted,
       CASE WHEN l.cancelled_at IS NOT NULL THEN 'Cancelled'
            WHEN s1.action IS NULL OR s2.action IS NULL THEN 'Missing approval step'
            WHEN s1.action <> 'Approved' THEN 'Manager ' + LOWER(s1.action)
            WHEN s2.action <> 'Approved' THEN 'HR ' + LOWER(s2.action)
            ELSE 'Counted' END AS decision_reason,
       l.source_row_id
INTO staging.leave_requests
FROM #lr l
LEFT JOIN staging.leave_approval_steps s1 ON s1.request_id = l.request_id AND s1.step = 1
LEFT JOIN staging.leave_approval_steps s2 ON s2.request_id = l.request_id AND s2.step = 2;
ALTER TABLE staging.leave_requests ALTER COLUMN request_id VARCHAR(20) NOT NULL;
ALTER TABLE staging.leave_requests ADD CONSTRAINT pk_stg_leave_requests PRIMARY KEY (request_id);
DROP TABLE #lr;
GO


DROP TABLE IF EXISTS staging.leave_days;
;WITH x AS (
    SELECT l.emp_id, c.d AS leave_date, l.leave_type, l.request_id,
           ROW_NUMBER() OVER (PARTITION BY l.emp_id, c.d ORDER BY l.request_id) AS rn
    FROM staging.leave_requests l
    JOIN staging.calendar c ON c.d BETWEEN l.leave_from AND l.leave_to
    WHERE l.is_counted = 1
      AND c.is_sunday = 0
      AND NOT EXISTS (SELECT 1 FROM staging.holiday_plant h WHERE h.holiday_date = c.d AND h.plant = l.plant))
SELECT emp_id, leave_date, leave_type, request_id
INTO staging.leave_days FROM x WHERE rn = 1;
ALTER TABLE staging.leave_days ALTER COLUMN emp_id VARCHAR(20) NOT NULL;
ALTER TABLE staging.leave_days ALTER COLUMN leave_date DATE NOT NULL;
ALTER TABLE staging.leave_days ADD CONSTRAINT pk_stg_leave_days PRIMARY KEY (emp_id, leave_date);
GO


DROP TABLE IF EXISTS staging.overtime_requests;
SELECT LTRIM(RTRIM(request_id)) AS request_id, LTRIM(RTRIM(emp_id)) AS emp_id, staging.fn_parse_date(ot_date) AS ot_date,
       TRY_CONVERT(DECIMAL(5,1), NULLIF(requested_hours, '')) AS requested_hours,
       TRY_CONVERT(DECIMAL(5,1), NULLIF(approved_hours, '')) AS approved_hours,
       LTRIM(RTRIM(status)) AS status, NULLIF(LTRIM(RTRIM(approver_id)), '') AS approver_id,
       TRY_CONVERT(DATETIME2(0), requested_at, 126) AS requested_at
INTO staging.overtime_requests FROM raw.overtime_requests;
ALTER TABLE staging.overtime_requests ALTER COLUMN request_id VARCHAR(20) NOT NULL;
ALTER TABLE staging.overtime_requests ADD CONSTRAINT pk_stg_overtime_requests PRIMARY KEY (request_id);
GO


DROP TABLE IF EXISTS staging.payroll_lines;
SELECT LTRIM(RTRIM(line_id)) AS line_id, LTRIM(RTRIM(payroll_month)) AS payroll_month, LTRIM(RTRIM(emp_id)) AS emp_id,
       UPPER(LTRIM(RTRIM(component))) AS component, UPPER(LTRIM(RTRIM(component_type))) AS component_type,
       TRY_CONVERT(DECIMAL(12,2), NULLIF(units, '')) AS units, TRY_CONVERT(DECIMAL(14,2), amount) AS amount
INTO staging.payroll_lines FROM raw.payroll_lines;
ALTER TABLE staging.payroll_lines ALTER COLUMN line_id VARCHAR(20) NOT NULL;
ALTER TABLE staging.payroll_lines ADD CONSTRAINT pk_stg_payroll_lines PRIMARY KEY (line_id);
GO


DROP TABLE IF EXISTS staging.applications;
SELECT LTRIM(RTRIM(application_id)) AS application_id, LTRIM(RTRIM(candidate_id)) AS candidate_id, LTRIM(RTRIM(job_req_id)) AS job_req_id,
       LTRIM(RTRIM(dept_id)) AS dept_id, LTRIM(RTRIM(stage)) AS stage, staging.fn_parse_date(stage_date) AS stage_date
INTO staging.applications FROM raw.applications;
GO
