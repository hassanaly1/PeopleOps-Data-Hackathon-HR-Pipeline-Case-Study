# Why overtime cost keeps rising - top three findings for the CFO

Indus Weave Textiles, 1 April to 30 September 2026. Payroll paid PKR 19.0 million of overtime in the six months, up from PKR 2.81 million
in April to PKR 3.48 million in September. Every number below is queried from the warehouse by the evidence query named under it;
`slides.pdf` is built from the same queries (`python presentation/build_slides.py`).

---

## Finding 1 - We are paying for overtime that nobody worked, and one department explains it

**The number.** Paid overtime hours grew **16%** (5,526 in April to 6,419 in September) while the hours actually worked, measured from
biometric punches, were flat (6,167 to 6,066, -2%). Faisalabad **Stitching** was paid **7,659 hours against 4,906 worked (+56%)**
and was over the 15% line in 5 of 6 months. All **3,174** Stitching overtime requests were approved by one approver, **E10382**;
**2,048** of them (spread over all **158** Stitching employees with overtime) approve more hours than the employee worked that day:
**3,357 hours, about PKR 1.67 million** at each employee's own overtime rate. No other department has a single request that exceeds
the hours worked.

**Why it happens.** Payroll pays overtime from approved requests, not from punches. Payroll overtime hours equal approved request
hours in all 6,572 employee-months, so nothing in the process compares an approval with what happened on the shop floor.

**Evidence queries.**
`presentation/evidence/f1_overtime_trend.sql` (monthly worked, approved, paid hours and PKR),
`presentation/evidence/f1_stitching_overpayment.sql` (overstated hours and PKR by department and approver),
`analytics/q05_overtime_computed_approved_paid.sql` and `analytics/q06_paid_exceeds_computed.sql` (Stitching is the only department above 15%).

**Recommended action.** Hold payment of overtime whose approved hours exceed the punched hours, starting with Stitching; review the
PKR 1.67 million already paid and the approvals of E10382; and make the approval workflow reject (or flag) any request that the
punches do not support, within the half-hour rounding rule.

---

## Finding 2 - PKR 4.8 million went to people with no attendance

**The number.** In 57 employee-months an employee was paid in full but did not attend a single day that month, **PKR 4,825,075** in all:

* **5 employees were paid for months after they left**, 21 pay-months, **PKR 1,948,000** (E10471 alone PKR 660,000 over five months after
  leaving on 23 April; E11222, E10332, E10989, E10295 for four months each after leaving in May).
* **6 active employees have no biometric device and no punch in six months**, 36 pay-months, **PKR 2,877,075**
  (E10399, E10491, E10564, E10907, E11064, E11089). By the rules they are Absent every day, yet payroll made no absence deduction for them.

**Evidence queries.** `presentation/evidence/f2_pay_without_attendance.sql` (summary),
`analytics/q07_paid_zero_attendance.sql` (every employee-month, with the reason),
`analytics/q08_paid_after_separation.sql` (the five leavers).

**Recommended action.** Remove the five leavers from payroll now and recover PKR 1.95 million. Verify that the six employees without a
device exist and work: if they do, enrol them; if they do not, stop their pay and treat the PKR 2.88 million as a fraud
investigation. Add a payroll rule that blocks a payslip when the employee has no attendance in the month or a separation date in the past.

---

## Finding 3 - One punch clock was an hour fast, so SITE numbers could not be trusted

**The number.** `DEV-SITE-01` ran **exactly 60 minutes fast from 1 July to the end of the data**; **45,803** SITE punches are affected. The
other three devices stayed within about 6 minutes of their baselines. After correcting the clock, **95.4%** of SITE working-day
overtime requests since 1 July (2,673 of 2,801) reconcile to the punches, the same as before July (95.9%) and as Korangi (95.7%).
On the raw punch file **none (0 of 2,801)** reconcile, and every SITE day-shift worker would look about an hour late.
The same data also held 6,962 punches from 40 unmapped device users (contractors and visitors) and 16,175 duplicate punches, all
removed and logged.

This is why "attendance looks normal" and "the overtime bill is wrong" can both be said: the modules disagree because the raw data
disagrees with itself, and nobody had a cleaned, reconciled model.

**Evidence queries.** `presentation/evidence/f3_clock_drift.sql` (weekly device evidence and the with / without correction test),
`transform/clock_drift.py` (the detector), `staging.device_clock_correction` / `staging.device_clock_diagnostics`.

**Recommended action.** Fix the SITE device clock and add a monthly device-clock check (the detector in this repository runs on every
export). Run the pipeline on each month's exports so finance, HR and payroll work from one reconciled set of numbers, and keep the data
quality checks (174, all passing) as the gate for it.
