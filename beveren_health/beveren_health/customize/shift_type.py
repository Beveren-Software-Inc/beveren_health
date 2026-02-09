import frappe
from frappe.utils import get_time, time_diff_in_hours
    
def autoname_shift_type(doc, method):
    if not (doc.custom_standard_working_hours and doc.start_time and doc.end_time and doc.custom_weekly_off):
        return
    start_hour = get_time(doc.start_time).hour
    end_hour = get_time(doc.end_time).hour
    doc.name = f"{int(doc.custom_standard_working_hours)} Hours Shift {start_hour}-{end_hour} {doc.custom_weekly_off}-Off"

def before_save(doc, method):
    doc.custom_standard_working_hours = time_diff_in_hours(doc.end_time, doc.start_time)
    autoname_shift_type(doc, method)