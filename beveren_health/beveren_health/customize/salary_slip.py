import frappe
from frappe.utils import getdate, add_months

@frappe.whitelist()
def get_lwp_absents(employee, start_date, end_date):
    start_date = getdate(start_date)
    end_date = getdate(end_date)
    prev_month_date = add_months(getdate(start_date), -1)
    start_date = prev_month_date.replace(day=21)
    end_date = getdate(end_date).replace(day=20)
    lwp_entries = frappe.get_all(
        "Leave Application",
        filters={
            "employee": employee,
            "leave_type": "Leave Without Pay",
            "from_date": ["<=", end_date],
            "to_date": [">=", start_date],
            "docstatus": 1
        },
        fields=["from_date", "to_date"]
    )
    total_lwp = 0
    for leave in lwp_entries:
        leave_start = max(getdate(leave.from_date), start_date)
        leave_end = min(getdate(leave.to_date), end_date)
        total_lwp += (leave_end - leave_start).days + 1

    absent_entries = frappe.get_all(
        "Attendance",
        filters={
            "employee": employee,
            "attendance_date": ["between", [start_date, end_date]],
            "status": "Absent",
            "docstatus": 1
        },
        fields=["attendance_date"]
    )

    total_absent = len(absent_entries)

    return {
        "total_lwp": total_lwp,
        "total_absent": total_absent
    }
