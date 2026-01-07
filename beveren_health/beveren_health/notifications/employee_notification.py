import frappe
from frappe.utils import getdate, add_days, today, formatdate

def notify_document_expiry():
    notify_date = add_days(today(), 90)
    employees = frappe.get_all("Employee", fields=["name", "employee_name"])
    for emp in employees:
        documents = frappe.get_all(
            "Employee Document",
            fields=["name", "document_name", "document_expiry_date"],
            filters={"parent": emp.name}
        )
        for doc in documents:
            if doc.document_expiry_date and doc.document_expiry_date < getdate(notify_date):
                message = f"Document '{doc.document_name}' of employee {emp.employee_name} will expire on {formatdate(doc.document_expiry_date)}."
                frappe.get_doc({
                        "doctype": "Notification Log",
                        "subject": message,
                        "document_type": "Employee",
                        "document_name": emp.name,
                        "for_user": None,   
                        "for_role": "HR User",  
                        "type": "Alert",
                        "seen": 0,
                        "email_content": message
                    }).insert(ignore_permissions=True)


def notify_ending_probation_period():
    notify_date = add_days(today(), 30)
    employees = frappe.get_all("Employee", fields=["name", "employee_name", "date_of_joining", "custom_probation_period", "custom_is_probation_period_"])
    for emp in employees:
        if emp.custom_is_probation_period_:
            probation_period = add_days(emp.date_of_joining, emp.custom_probation_period)
            if getdate(probation_period) < getdate(notify_date):
                message = f"Employee {emp.employee_name} probation period is going to end on {formatdate(probation_period)}."
                frappe.get_doc({
                        "doctype": "Notification Log",
                        "subject": message,
                        "document_type": "Employee",
                        "document_name": emp.name,
                        "for_user": None,   
                        "for_role": "HR User",  
                        "type": "Alert",
                        "seen": 0,
                        "email_content": message
                    }).insert(ignore_permissions=True)

