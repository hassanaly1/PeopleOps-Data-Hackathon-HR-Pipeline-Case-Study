/* Finding 3 - evidence: the SITE biometric clock and what it does to the overtime check.
   Part A: the detector's weekly evidence (staging.device_clock_diagnostics) around the change.
   Part B: how many approved SITE overtime requests on WORKING days (1 Jul - 30 Sep) reconcile to the punches, with and
           without the correction. 'without' adds the 60 minutes back to the check-out, which is what the raw SITE punch
           file would have shown. Sunday / holiday overtime is left out on purpose: it is check-out minus check-in, so a
           constant clock offset does not change it (77 such requests, 75 reconcile either way).                       */

-- Part A
SELECT device_id, week_start, valid_days, avg_morning_edge_minute, avg_deviation_minutes
FROM staging.device_clock_diagnostics
WHERE week_start BETWEEN '2026-06-08' AND '2026-07-20' AND device_id IN ('DEV-SITE-01', 'DEV-KOR-01')
ORDER BY device_id, week_start;

-- Part B
WITH s AS (
    SELECT o.approved_hours, f.overtime_hours AS ot_corrected, f.status, f.is_working_day, f.check_out,
           DATEADD(MINUTE, DATEDIFF(MINUTE, CAST('00:00' AS TIME), sh.end_time),
                   DATEADD(DAY, CASE WHEN sh.crosses_midnight = 1 THEN 1 ELSE 0 END, CAST(dd.full_date AS DATETIME2(0)))) AS shift_end_dt
    FROM warehouse.fact_overtime_approved o
    JOIN warehouse.fact_attendance_daily f ON f.employee_key = o.employee_key AND f.date_key = o.date_key
    JOIN warehouse.dim_employee e ON e.employee_key = o.employee_key
    JOIN warehouse.dim_shift sh   ON sh.shift_key = f.shift_key
    JOIN warehouse.dim_date dd    ON dd.date_key = o.date_key
    WHERE e.plant = 'SITE Plant' AND dd.full_date >= '2026-07-01'
      AND f.status = 'Present' AND f.is_working_day = 1
)
SELECT COUNT(*) AS approved_site_requests,
       SUM(CASE WHEN ot_corrected = approved_hours THEN 1 ELSE 0 END) AS match_with_correction,
       SUM(CASE WHEN (CASE WHEN status = 'Present' AND is_working_day = 1 AND DATEDIFF(SECOND, shift_end_dt, DATEADD(MINUTE, 60, check_out)) > 0
                           THEN (DATEDIFF(SECOND, shift_end_dt, DATEADD(MINUTE, 60, check_out)) / 1800) * 0.5
                           ELSE ot_corrected END) = approved_hours THEN 1 ELSE 0 END) AS match_without_correction
FROM s;
