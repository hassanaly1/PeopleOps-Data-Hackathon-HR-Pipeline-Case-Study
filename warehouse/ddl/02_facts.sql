-- 02_facts.sql - Stage 4: fact tables (run after 01_dimensions.sql).

CREATE TABLE warehouse.fact_attendance_daily (
    attendance_key          BIGINT IDENTITY(1,1) NOT NULL,
    employee_key            INT          NOT NULL,
    department_key          INT          NOT NULL,
    shift_key               INT          NOT NULL,
    date_key                INT          NOT NULL,
    status                  VARCHAR(15)  NOT NULL,
    is_working_day          BIT          NOT NULL,
    n_punches               TINYINT      NOT NULL,
    check_in                DATETIME2(0) NULL,
    check_out               DATETIME2(0) NULL,
    worked_hours            DECIMAL(6,2) NOT NULL,
    late_minutes            INT          NOT NULL,
    early_departure_minutes INT          NOT NULL,
    is_late                 BIT          NOT NULL,
    is_early_departure      BIT          NOT NULL,
    overtime_hours          DECIMAL(5,1) NOT NULL,
    overtime_type           VARCHAR(10)  NULL,
    holiday_name            VARCHAR(100) NULL,
    leave_type              VARCHAR(20)  NULL,
    CONSTRAINT pk_fact_attendance_daily PRIMARY KEY (attendance_key),
    CONSTRAINT uq_fact_attendance_day UNIQUE (employee_key, date_key),
    CONSTRAINT ck_fact_attendance_status CHECK (status IN ('Present','Absent','On Leave','Holiday','Weekly Off','Missing Punch')),
    CONSTRAINT fk_fact_attendance_employee   FOREIGN KEY (employee_key)   REFERENCES warehouse.dim_employee (employee_key),
    CONSTRAINT fk_fact_attendance_department FOREIGN KEY (department_key) REFERENCES warehouse.dim_department (department_key),
    CONSTRAINT fk_fact_attendance_shift      FOREIGN KEY (shift_key)      REFERENCES warehouse.dim_shift (shift_key),
    CONSTRAINT fk_fact_attendance_date       FOREIGN KEY (date_key)       REFERENCES warehouse.dim_date (date_key));
CREATE INDEX ix_fact_attendance_date ON warehouse.fact_attendance_daily (date_key, department_key);
GO

CREATE TABLE warehouse.fact_leave_day (
    leave_day_key  BIGINT IDENTITY(1,1) NOT NULL,
    employee_key   INT         NOT NULL,
    department_key INT         NOT NULL,
    date_key       INT         NOT NULL,
    leave_type     VARCHAR(10) NOT NULL,
    request_id     VARCHAR(20) NOT NULL,
    CONSTRAINT pk_fact_leave_day PRIMARY KEY (leave_day_key),
    CONSTRAINT uq_fact_leave_day UNIQUE (employee_key, date_key),
    CONSTRAINT ck_fact_leave_type CHECK (leave_type IN ('Annual','Casual','Sick')),
    CONSTRAINT fk_fact_leave_employee   FOREIGN KEY (employee_key)   REFERENCES warehouse.dim_employee (employee_key),
    CONSTRAINT fk_fact_leave_department FOREIGN KEY (department_key) REFERENCES warehouse.dim_department (department_key),
    CONSTRAINT fk_fact_leave_date       FOREIGN KEY (date_key)       REFERENCES warehouse.dim_date (date_key));
GO

CREATE TABLE warehouse.fact_overtime_approved (
    request_id      VARCHAR(20)  NOT NULL,
    employee_key    INT          NOT NULL,
    department_key  INT          NOT NULL,
    date_key        INT          NOT NULL,
    requested_hours DECIMAL(5,1) NOT NULL,
    approved_hours  DECIMAL(5,1) NOT NULL,
    approver_id     VARCHAR(20)  NULL,
    requested_at    DATETIME2(0) NULL,
    CONSTRAINT pk_fact_overtime_approved PRIMARY KEY (request_id),
    CONSTRAINT fk_fact_ot_employee   FOREIGN KEY (employee_key)   REFERENCES warehouse.dim_employee (employee_key),
    CONSTRAINT fk_fact_ot_department FOREIGN KEY (department_key) REFERENCES warehouse.dim_department (department_key),
    CONSTRAINT fk_fact_ot_date       FOREIGN KEY (date_key)       REFERENCES warehouse.dim_date (date_key));
GO

CREATE TABLE warehouse.fact_payroll_line (
    line_id         VARCHAR(20)   NOT NULL,
    employee_key    INT           NOT NULL,
    department_key  INT           NOT NULL,
    date_key        INT           NOT NULL,
    payroll_month   CHAR(7)       NOT NULL,
    component       VARCHAR(20)   NOT NULL,
    component_type  VARCHAR(10)   NOT NULL,
    units           DECIMAL(12,2) NULL,
    amount          DECIMAL(14,2) NOT NULL,
    CONSTRAINT pk_fact_payroll_line PRIMARY KEY (line_id),
    CONSTRAINT ck_fact_payroll_component CHECK (component IN ('BASIC','HOUSE_RENT','MEDICAL','CONVEYANCE','OVERTIME',
                                                              'INCOME_TAX','EOBI','ABSENCE_DEDUCTION','LOAN_INSTALLMENT')),
    CONSTRAINT ck_fact_payroll_type CHECK (component_type IN ('EARNING','DEDUCTION')),
    CONSTRAINT fk_fact_payroll_employee   FOREIGN KEY (employee_key)   REFERENCES warehouse.dim_employee (employee_key),
    CONSTRAINT fk_fact_payroll_department FOREIGN KEY (department_key) REFERENCES warehouse.dim_department (department_key),
    CONSTRAINT fk_fact_payroll_date       FOREIGN KEY (date_key)       REFERENCES warehouse.dim_date (date_key));
CREATE INDEX ix_fact_payroll_month ON warehouse.fact_payroll_line (payroll_month, department_key);
GO
