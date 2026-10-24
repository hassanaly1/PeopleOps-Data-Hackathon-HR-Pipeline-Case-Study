-- 20_staging_punches.sql - Stage 2 (part 2): biometric punches.

DROP TABLE IF EXISTS staging.device_mapping;
SELECT LTRIM(RTRIM(device_id)) AS device_id, LTRIM(RTRIM(device_user_id)) AS device_user_id, LTRIM(RTRIM(emp_id)) AS emp_id,
       staging.fn_parse_date(enrolled_on) AS enrolled_on
INTO staging.device_mapping FROM raw.device_mapping;
ALTER TABLE staging.device_mapping ALTER COLUMN device_id VARCHAR(40) NOT NULL;
ALTER TABLE staging.device_mapping ALTER COLUMN device_user_id VARCHAR(40) NOT NULL;
ALTER TABLE staging.device_mapping ADD CONSTRAINT pk_stg_device_mapping PRIMARY KEY (device_id, device_user_id);
GO


DROP TABLE IF EXISTS staging.punches_all;
SELECT LTRIM(RTRIM(p.punch_id)) AS punch_id, LTRIM(RTRIM(p.device_id)) AS device_id, LTRIM(RTRIM(p.device_user_id)) AS device_user_id,
       TRY_CONVERT(DATETIME2(0), p.punch_time, 120) AS punch_time_raw,
       ISNULL(c.correction_minutes, 0) AS correction_minutes,
       DATEADD(MINUTE, ISNULL(c.correction_minutes, 0), TRY_CONVERT(DATETIME2(0), p.punch_time, 120)) AS punch_time
INTO staging.punches_all
FROM raw.biometric_punches p
LEFT JOIN staging.device_clock_correction c
       ON c.device_id = LTRIM(RTRIM(p.device_id))
      AND TRY_CONVERT(DATE, p.punch_time, 120) >= c.valid_from
      AND (c.valid_to IS NULL OR TRY_CONVERT(DATE, p.punch_time, 120) <= c.valid_to);
ALTER TABLE staging.punches_all ALTER COLUMN punch_id VARCHAR(20) NOT NULL;
ALTER TABLE staging.punches_all ADD CONSTRAINT pk_stg_punches_all PRIMARY KEY (punch_id);
GO


DROP TABLE IF EXISTS staging.rejected_punches;
SELECT p.punch_id, p.device_id, p.device_user_id, p.punch_time_raw, p.punch_time,
       CAST('No row in device_mapping for this device_id + device_user_id (contractor or visitor)' AS VARCHAR(200)) AS reject_reason
INTO staging.rejected_punches
FROM staging.punches_all p
LEFT JOIN staging.device_mapping m ON m.device_id = p.device_id AND m.device_user_id = p.device_user_id
WHERE m.emp_id IS NULL;
ALTER TABLE staging.rejected_punches ADD CONSTRAINT pk_stg_rejected_punches PRIMARY KEY (punch_id);
GO


DROP TABLE IF EXISTS staging.duplicate_punches;
DROP TABLE IF EXISTS staging.punches;
SELECT m.emp_id, p.punch_id, p.device_id, p.punch_time_raw, p.punch_time, p.correction_minutes,
       LAG(p.punch_id)   OVER (PARTITION BY m.emp_id ORDER BY p.punch_time, p.punch_id) AS prev_punch_id,
       DATEDIFF(SECOND, LAG(p.punch_time) OVER (PARTITION BY m.emp_id ORDER BY p.punch_time, p.punch_id), p.punch_time) AS gap_seconds
INTO #mapped
FROM staging.punches_all p
JOIN staging.device_mapping m ON m.device_id = p.device_id AND m.device_user_id = p.device_user_id;

SELECT emp_id, punch_id, device_id, punch_time_raw, punch_time, correction_minutes
INTO staging.punches FROM #mapped WHERE gap_seconds IS NULL OR gap_seconds > 120;
ALTER TABLE staging.punches ALTER COLUMN punch_id VARCHAR(20) NOT NULL;
ALTER TABLE staging.punches ADD CONSTRAINT pk_stg_punches PRIMARY KEY (punch_id);
CREATE INDEX ix_stg_punches_emp_time ON staging.punches (emp_id, punch_time);

SELECT punch_id, emp_id, device_id, punch_time, prev_punch_id AS kept_punch_id, gap_seconds,
       CAST('Within 120 seconds of the same employee''s previous punch (rule 9)' AS VARCHAR(200)) AS reason
INTO staging.duplicate_punches FROM #mapped WHERE gap_seconds <= 120;
ALTER TABLE staging.duplicate_punches ALTER COLUMN punch_id VARCHAR(20) NOT NULL;
ALTER TABLE staging.duplicate_punches ADD CONSTRAINT pk_stg_duplicate_punches PRIMARY KEY (punch_id);
DROP TABLE #mapped;
GO
