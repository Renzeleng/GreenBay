"""
Payroll computation engine.
Thesis reference: Chapter III – Payroll Computation, Table 3.2,
IPO Analysis (Table 3.6).

Computes gross pay and itemized statutory deductions (SSS, PhilHealth,
Pag-IBIG) from verified attendance records, on a bi-weekly schedule.
Deductions are fixed monthly peso amounts (not percentages); the
employee's share is taken in full only on the second/last cutoff of
each month. Withholding tax has been removed per clinic policy.
"""

from datetime import date, datetime
from app.models import get_db

# Employee share of each statutory contribution's TOTAL monthly amount.
# The remainder is the employer's share (e.g. SSS: employer pays 60%).
SSS_EMPLOYEE_SHARE        = 0.40
PHILHEALTH_EMPLOYEE_SHARE = 0.50
PAGIBIG_EMPLOYEE_SHARE    = 0.50


def is_second_cutoff(period_end: str) -> bool:
    """
    Determine whether a bi-weekly pay period is the SECOND (last) cutoff
    of its month, based on the day-of-month of the period's end date.
    Days 1-15 => first cutoff (no statutory deduction this cut).
    Days 16+  => second/last cutoff (full monthly employee share deducted).
    """
    d = period_end
    if isinstance(d, str):
        d = datetime.strptime(d[:10], '%Y-%m-%d').date()
    return d.day > 15


def compute_hours_worked(time_in_str, time_out_str) -> float:
    """Compute decimal hours between time_in and time_out strings."""
    if not time_in_str or not time_out_str:
        return 0.0
    fmt_options = [
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%dT%H:%M',
    ]
    t_in = t_out = None
    for fmt in fmt_options:
        try:
            t_in = datetime.strptime(str(time_in_str), fmt)
            break
        except ValueError:
            continue
    for fmt in fmt_options:
        try:
            t_out = datetime.strptime(str(time_out_str), fmt)
            break
        except ValueError:
            continue
    if t_in and t_out and t_out > t_in:
        return round((t_out - t_in).total_seconds() / 3600, 2)
    return 0.0


def get_attendance_for_period(staff_id: int, period_start: str, period_end: str) -> list:
    """
    Return attendance records for a staff member within a pay period.
    Returns list of dicts with daily time_in, time_out, hours_worked.
    """
    with get_db() as conn:
        rows = conn.execute("""
            SELECT scan_date, time_in, time_out, hours_worked, status
            FROM attendance
            WHERE staff_id = ?
              AND scan_date BETWEEN ? AND ?
              AND scan_type = 'time_out'
            ORDER BY scan_date
        """, (staff_id, period_start, period_end)).fetchall()
    return [dict(r) for r in rows]


def compute_payroll(staff_id: int, period_start: str, period_end: str,
                    allowances: float = 0.0, allowances_note: str = '',
                    other_deductions: float = 0.0, other_deductions_note: str = '') -> dict:
    """
    Compute payroll for a staff member for a given bi-weekly pay period.

    Steps:
    1. Fetch staff salary configuration
    2. Aggregate verified attendance records
    3. Compute gross pay: if monthly_rate is set, convert to a daily-
       equivalent rate (monthly_rate / 26 working days — the standard
       Philippine payroll convention) and multiply by days actually
       worked in the period; otherwise fall back to days_worked *
       daily_rate.
    4. Apply statutory deductions — ONLY on the second (last) bi-weekly
       cutoff of the month (i.e. when period_end falls in the second
       half of its month). The employee's share is a fixed fraction of
       the configured monthly TOTAL contribution: SSS 40%, PhilHealth
       50%, Pag-IBIG 50%. Zero on the first cutoff of the month.
    5. Compute net pay

    Returns a dict matching the payroll table schema.
    """
    with get_db() as conn:
        staff = conn.execute("""
            SELECT * FROM staff WHERE id = ?
        """, (staff_id,)).fetchone()

    if not staff:
        raise ValueError(f"Staff ID {staff_id} not found")

    staff = dict(staff)
    attendance_records = get_attendance_for_period(staff_id, period_start, period_end)

    # Aggregate
    total_hours = sum(r.get('hours_worked') or 0.0 for r in attendance_records)
    total_days  = len([r for r in attendance_records if r.get('hours_worked', 0) > 0])

    # Gross pay computation
    STANDARD_WORKING_DAYS_PER_MONTH = 26
    monthly_rate = float(staff.get('monthly_rate') or 0.0)
    daily_rate   = float(staff.get('daily_rate') or 0.0)

    if monthly_rate > 0:
        daily_equivalent = monthly_rate / STANDARD_WORKING_DAYS_PER_MONTH
        gross_pay = round(total_days * daily_equivalent, 2)
    elif daily_rate > 0:
        gross_pay = round(total_days * daily_rate, 2)
    else:
        gross_pay = 0.0

    gross_pay += float(allowances or 0.0)

    # Statutory deductions only apply on the LAST bi-weekly cutoff of the
    # month. A period's end-day determines which cutoff it is: day <= 15
    # is the first cutoff (no deduction), day > 15 is the second/last
    # cutoff of that month (full monthly employee share deducted).
    is_last_cutoff_of_month = is_second_cutoff(period_end)

    if is_last_cutoff_of_month:
        sss        = round(float(staff.get('sss_monthly_total') or 0.0) * SSS_EMPLOYEE_SHARE, 2)
        philhealth = round(float(staff.get('philhealth_monthly_total') or 0.0) * PHILHEALTH_EMPLOYEE_SHARE, 2)
        pagibig    = round(float(staff.get('pagibig_monthly_total') or 0.0) * PAGIBIG_EMPLOYEE_SHARE, 2)
    else:
        sss = philhealth = pagibig = 0.0

    other_ded = round(float(other_deductions or 0.0), 2)

    total_deductions = round(sss + philhealth + pagibig + other_ded, 2)
    net_pay          = round(gross_pay - total_deductions, 2)

    return {
        'staff_id':               staff_id,
        'pay_period_start':       period_start,
        'pay_period_end':         period_end,
        'total_days_worked':      total_days,
        'total_hours_worked':     total_hours,
        'gross_pay':              gross_pay,
        'sss_deduction':          sss,
        'philhealth_deduction':   philhealth,
        'pagibig_deduction':      pagibig,
        'withholding_tax':        0.0,
        'other_deductions':       other_ded,
        'other_deductions_note':  other_deductions_note,
        'total_deductions':       total_deductions,
        'net_pay':                net_pay,
        'allowances':             float(allowances or 0.0),
        'allowances_note':        allowances_note,
        'status':                 'draft',
        # metadata for display
        '_staff_name':            f"{staff['first_name']} {staff['last_name']}",
        '_position':              staff.get('position', ''),
        '_attendance':            attendance_records,
        '_is_last_cutoff':        is_last_cutoff_of_month,
    }


def save_payroll(payroll_data: dict, created_by_user_id: int = None) -> int:
    """
    Persist a computed payroll record and return its new ID.
    Also records a report entry for audit trail.
    """
    with get_db() as conn:
        # Remove display-only keys
        data = {k: v for k, v in payroll_data.items() if not k.startswith('_')}

        cursor = conn.execute("""
            INSERT INTO payroll (
                staff_id, pay_period_start, pay_period_end,
                total_days_worked, total_hours_worked, gross_pay,
                sss_deduction, philhealth_deduction, pagibig_deduction,
                withholding_tax, other_deductions, other_deductions_note,
                total_deductions, net_pay, allowances, allowances_note, status
            ) VALUES (
                :staff_id, :pay_period_start, :pay_period_end,
                :total_days_worked, :total_hours_worked, :gross_pay,
                :sss_deduction, :philhealth_deduction, :pagibig_deduction,
                :withholding_tax, :other_deductions, :other_deductions_note,
                :total_deductions, :net_pay, :allowances, :allowances_note, :status
            )
        """, data)
        payroll_id = cursor.lastrowid

        if created_by_user_id:
            import json
            conn.execute("""
                INSERT INTO report (report_type, parameters, generated_by)
                VALUES ('payroll_computed', ?, ?)
            """, (json.dumps({'payroll_id': payroll_id, 'staff_id': data['staff_id']}),
                  created_by_user_id))

    return payroll_id
