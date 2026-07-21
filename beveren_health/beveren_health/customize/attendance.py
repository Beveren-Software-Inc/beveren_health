import frappe
from frappe.utils import get_datetime, time_diff_in_hours, add_to_date, get_time

def before_insert(doc, method):
    shift = frappe.db.get_value(
        "Shift Type",
        doc.shift,
        ["start_time", "end_time", "late_entry_grace_period", "early_exit_grace_period", "custom_less_time_type"],
        as_dict=True
    )
    
    if not shift:
        return
    
    doc.standard_working_hours = time_diff_in_hours(shift.end_time, shift.start_time)

    # Feeding-hours entitlement: reduce a nursing mother's expected hours by her daily paid
    # feeding break (2h while child < 6 months, 1h from 6-12 months) so the less-time engine
    # below does not dock her for the entitled break. No effect for employees without an
    # active Feeding Hours Entitlement.
    from beveren_health.beveren_health.doctype.feeding_hours_entitlement.feeding_hours_entitlement import (
        get_feeding_hours,
    )

    feeding_hours = get_feeding_hours(doc.employee, doc.attendance_date)
    if feeding_hours:
        doc.custom_feeding_hours = feeding_hours
        doc.standard_working_hours = max(0, doc.standard_working_hours - feeding_hours)

    if not (doc.in_time and doc.out_time and doc.shift):
        return

    # Convert shift times to datetime based on attendance date
    shift_start = get_datetime(f"{doc.attendance_date} {shift.start_time}")
    shift_end = get_datetime(f"{doc.attendance_date} {shift.end_time}")

    # Grace periods in hours
    checkin_grace_hours = (shift.late_entry_grace_period or 0) / 60
    checkout_grace_hours = (shift.early_exit_grace_period or 0) / 60

    doc.custom_grace_hours = 0

    # -------- Check-in Grace --------
    late_checkin_hours = time_diff_in_hours(doc.in_time, shift_start)

    if late_checkin_hours > 0 and late_checkin_hours <= checkin_grace_hours:
        doc.custom_grace_hours += late_checkin_hours
        doc.working_hours += late_checkin_hours

    # -------- Check-out Grace --------
    early_checkout_hours = time_diff_in_hours(shift_end, doc.out_time)

    if early_checkout_hours > 0 and early_checkout_hours <= checkout_grace_hours:
        doc.custom_grace_hours += early_checkout_hours
        doc.working_hours += early_checkout_hours
    
    if doc.working_hours < doc.standard_working_hours:
        doc.custom_less_time_type = shift.custom_less_time_type
        doc.custom_actual_lesstime_duration = doc.standard_working_hours - doc.working_hours
