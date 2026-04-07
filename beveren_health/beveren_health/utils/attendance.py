import frappe
from frappe.utils import now_datetime


def update_last_sync_for_all_shifts():
    """
    Mimics core update_last_sync_of_checkin logic.
    Updates Last Sync to latest Employee Checkin time per shift.
    """

    shift_types = frappe.get_all(
        'Shift Type',
        filters={'enable_auto_attendance': 1},
        fields=['name']
    )

    for shift in shift_types:
        try:
            # Get the latest checkin time for this shift
            latest_checkin = frappe.db.get_value(
                'Employee Checkin',
                filters={'shift': shift['name']},
                fieldname='time',
                order_by='time desc'
            )

            if latest_checkin:
                frappe.db.set_value(
                    'Shift Type',
                    shift['name'],
                    'last_sync_of_checkin',
                    latest_checkin
                )
            else:
                # No checkins found — set to now so scheduler doesn't skip
                frappe.db.set_value(
                    'Shift Type',
                    shift['name'],
                    'last_sync_of_checkin',
                    now_datetime()
                )

        except Exception:
            frappe.log_error(
                f"Failed to update Last Sync for: {shift['name']}\n{frappe.get_traceback()}",
                "Shift Last Sync Updater"
            )

    frappe.db.commit()


@frappe.whitelist()
def trigger_manual_last_sync():
    frappe.only_for("System Manager")
    update_last_sync_for_all_shifts()
    return "Last Sync updated based on latest checkin records. Attendance will be marked within the hour."