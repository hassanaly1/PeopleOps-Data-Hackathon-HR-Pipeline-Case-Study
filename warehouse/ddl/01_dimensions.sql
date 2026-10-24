-- 01_dimensions.sql - Stage 4: dimension tables of the warehouse star schema.

DROP TABLE IF EXISTS warehouse.fact_payroll_line;
DROP TABLE IF EXISTS warehouse.fact_overtime_approved;
DROP TABLE IF EXISTS warehouse.fact_leave_day;
DROP TABLE IF EXISTS warehouse.fact_attendance_daily;
DROP TABLE IF EXISTS warehouse.dim_employee;
DROP TABLE IF EXISTS warehouse.dim_shift;
DROP TABLE IF EXISTS warehouse.dim_department;
DROP TABLE IF EXISTS warehouse.dim_date;
GO

CREATE TABLE warehouse.dim_date (
    date_key      INT          NOT NULL,
    full_date     DATE         NOT NULL,
    [year]        SMALLINT     NOT NULL,
    [quarter]     TINYINT      NOT NULL,
    [month]       TINYINT      NOT NULL,
    month_name    VARCHAR(10)  NOT NULL,
    year_month    CHAR(7)      NOT NULL,
    day_of_month  TINYINT      NOT NULL,
    day_of_week   TINYINT      NOT NULL,
    day_name      VARCHAR(10)  NOT NULL,
    is_sunday     BIT          NOT NULL,
    week_start    DATE         NOT NULL,
    month_start   DATE         NOT NULL,
    month_end     DATE         NOT NULL,
    is_month_end  BIT          NOT NULL,
    CONSTRAINT pk_dim_date PRIMARY KEY (date_key),
    CONSTRAINT uq_dim_date_full_date UNIQUE (full_date));
GO

CREATE TABLE warehouse.dim_department (
    department_key INT IDENTITY(1,1) NOT NULL,
    dept_id        VARCHAR(10)  NOT NULL,
    dept_name      VARCHAR(100) NOT NULL,
    plant          VARCHAR(60)  NOT NULL,
    cost_center    VARCHAR(20)  NOT NULL,
    previous_name  VARCHAR(100) NULL,
    renamed_on     DATE         NULL,
    CONSTRAINT pk_dim_department PRIMARY KEY (department_key),
    CONSTRAINT uq_dim_department_dept_id UNIQUE (dept_id));
GO

CREATE TABLE warehouse.dim_shift (
    shift_key        INT IDENTITY(1,1) NOT NULL,
    shift_code       VARCHAR(10) NOT NULL,
    shift_name       VARCHAR(40) NOT NULL,
    start_time       TIME(0)     NOT NULL,
    end_time         TIME(0)     NOT NULL,
    crosses_midnight BIT         NOT NULL,
    grace_minutes    INT         NOT NULL,
    applies_to       VARCHAR(80) NULL,
    CONSTRAINT pk_dim_shift PRIMARY KEY (shift_key),
    CONSTRAINT uq_dim_shift_code UNIQUE (shift_code));
GO

CREATE TABLE warehouse.dim_employee (
    employee_key             INT IDENTITY(1,1) NOT NULL,
    emp_id                   VARCHAR(20)  NOT NULL,
    full_name                VARCHAR(100) NOT NULL,
    gender                   CHAR(1)      NULL,
    plant                    VARCHAR(60)  NOT NULL,
    employment_type          VARCHAR(20)  NOT NULL,
    hire_date                DATE         NOT NULL,
    separation_date          DATE         NULL,
    status                   VARCHAR(20)  NOT NULL,
    annual_leave_entitlement INT          NOT NULL,
    has_device_mapping       BIT          NOT NULL,

    department_key           INT          NOT NULL,
    designation              VARCHAR(100) NOT NULL,
    grade                    VARCHAR(5)   NOT NULL,
    basic_salary             DECIMAL(12,2) NOT NULL,
    change_reason            VARCHAR(30)  NOT NULL,
    valid_from               DATE         NOT NULL,
    valid_to                 DATE         NOT NULL,
    is_current               BIT          NOT NULL,
    CONSTRAINT pk_dim_employee PRIMARY KEY (employee_key),
    CONSTRAINT uq_dim_employee_version UNIQUE (emp_id, valid_from),
    CONSTRAINT ck_dim_employee_range CHECK (valid_from <= valid_to),
    CONSTRAINT fk_dim_employee_department FOREIGN KEY (department_key) REFERENCES warehouse.dim_department (department_key));
CREATE INDEX ix_dim_employee_lookup ON warehouse.dim_employee (emp_id, valid_from, valid_to);
GO
