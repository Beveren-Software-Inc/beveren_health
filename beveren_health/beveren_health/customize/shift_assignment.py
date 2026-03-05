import frappe

def on_submit_shift_assignment(doc, method):
    holiday_assignments = frappe.get_doc(
        "Holiday List Assignment",
        filters={
            "employee": doc.employee,
            "from_date": doc.start_date,
            "to_date": doc.end_date,
            "docstatus": 0
        },
        pluck="name"
    )

    for ha in holiday_assignments:
        holiday_doc = frappe.get_doc("Holiday Assignment", ha)
        holiday_doc.submit()