# Serene BRD — HR: route a leave application to the employee's OWN department head.
#
# The two-level workflow (see leave_workflow.py) restricts the first-level
# approval to the application's `leave_approver`. This makes sure that approver
# is the employee's department head, so e.g. every Nursing application goes to
# the Nursing department head only.
#
# Department head = the first approver in Department.leave_approvers.

import frappe


def set_department_head_as_approver(doc, method=None):
    """If no leave approver is chosen, default it to the head (leave approver)
    configured on the employee's department."""
    if doc.leave_approver:
        return

    department = doc.department or frappe.db.get_value("Employee", doc.employee, "department")
    if not department:
        return

    approver = get_department_head(department)
    if approver:
        doc.leave_approver = approver
        doc.leave_approver_name = frappe.db.get_value("User", approver, "full_name")


def get_department_head(department):
    """First leave approver configured on the department (its head)."""
    return frappe.db.get_value(
        "Department Approver",
        {"parent": department, "parentfield": "leave_approvers"},
        "approver",
        order_by="idx asc",
    )
