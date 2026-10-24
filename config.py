"""Shared settings. Everything can be overridden with environment variables."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

DATA_DIR = Path(os.environ.get("HR_DATA_DIR", ROOT / "data"))

SQL_SERVER = os.environ.get("HR_SQL_SERVER", "localhost")
DATABASE = os.environ.get("HR_DB", "IndusWeaveHR")
ODBC_DRIVER = os.environ.get("HR_ODBC_DRIVER", "ODBC Driver 18 for SQL Server")
SQL_USER = os.environ.get("HR_SQL_USER")
SQL_PASSWORD = os.environ.get("HR_SQL_PASSWORD")

PERIOD_START = "2026-04-01"
PERIOD_END = "2026-09-30"

CSV_FILES = {
    "employees.csv": "employees",
    "employment_history.csv": "employment_history",
    "departments.csv": "departments",
    "shift_roster.csv": "shift_roster",
    "device_mapping.csv": "device_mapping",
    "biometric_punches.csv": "biometric_punches",
    "holidays.csv": "holidays",
    "overtime_requests.csv": "overtime_requests",
    "payroll_lines.csv": "payroll_lines",
    "applications.csv": "applications",
}
JSON_FILES = {
    "shifts.json": ("shifts", "$.shifts"),
    "leave_requests.json": ("leave_requests", None),
}
