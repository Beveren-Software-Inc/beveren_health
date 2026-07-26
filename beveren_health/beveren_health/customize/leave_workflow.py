# Serene BRD — HR: multi-level Leave Application approval hierarchy.
#
# Chain:  Employee applies  ->  Department Head approves  ->  HR (final) approves -> submitted.
# Reject is available at either level. Built as a Frappe Workflow so it is fully
# native (email alerts, permissions, audit trail) and survives HRMS upgrades.
#
# Idempotent: safe to run repeatedly (used from a patch and can be re-run manually).

import frappe

WORKFLOW_NAME = "Leave Approval (Serene)"
DOCTYPE = "Leave Application"
DEPT_HEAD_ROLE = "Department Head"
HR_ROLE = "HR Manager"

# Custom workflow-state master records we need in addition to the built-in ones.
CUSTOM_STATES = ["Pending Department Head Approval", "Approved by Department Head"]

# (state, doc_status, allow_edit, update_field, update_value)
STATES = [
    ("Pending Department Head Approval", "0", "Employee",  "status", "Open"),
    ("Approved by Department Head",      "0", HR_ROLE,     "status", "Open"),
    ("Approved",                         "1", HR_ROLE,     "status", "Approved"),
    ("Rejected",                         "1", HR_ROLE,     "status", "Rejected"),
]

# Level-1 routing: only the application's own leave approver (= the employee's
# department head) may action the first level, so e.g. Nursing leaves reach the
# Nursing head only — not every Department Head. Level 2 (HR) stays central.
DEPT_HEAD_COND = "doc.leave_approver and frappe.session.user == doc.leave_approver"

# (state, action, next_state, allowed_role, condition)
TRANSITIONS = [
    ("Pending Department Head Approval", "Approve", "Approved by Department Head", DEPT_HEAD_ROLE, DEPT_HEAD_COND),
    ("Pending Department Head Approval", "Reject",  "Rejected",                    DEPT_HEAD_ROLE, DEPT_HEAD_COND),
    ("Approved by Department Head",      "Approve", "Approved",                    HR_ROLE,        None),
    ("Approved by Department Head",      "Reject",  "Rejected",                    HR_ROLE,        None),
]


def ensure_role():
    if not frappe.db.exists("Role", DEPT_HEAD_ROLE):
        frappe.get_doc({
            "doctype": "Role",
            "role_name": DEPT_HEAD_ROLE,
            "desk_access": 1,
        }).insert(ignore_permissions=True)


def ensure_workflow_states():
    for s in CUSTOM_STATES:
        if not frappe.db.exists("Workflow State", s):
            frappe.get_doc({
                "doctype": "Workflow State",
                "workflow_state_name": s,
                "style": "Warning" if "Pending" in s else "Primary",
            }).insert(ignore_permissions=True)


def _grant(doctype, role, props):
    from frappe.permissions import add_permission, update_permission_property
    has_row = frappe.get_all("Custom DocPerm",
        filters={"parent": doctype, "role": role, "permlevel": 0}, limit=1) \
        or frappe.get_all("DocPerm",
        filters={"parent": doctype, "role": role, "permlevel": 0}, limit=1)
    if not has_row:
        add_permission(doctype, role, 0)
    for prop in props:
        update_permission_property(doctype, role, 0, prop, 1)


def ensure_permissions():
    """Grant the Department Head role what it needs to action the first-level
    approval. HR Manager already has full perms out of the box.
    (Restrict a head to their own department via User Permissions if needed.)

    - Leave Application: read/write/email  -> action the workflow transition.
    - Employee: read                       -> HRMS validate_leave_access() lets a
      user validate an employee's leave balance only if they are the employee,
      the configured leave approver, OR can read the Employee record."""
    _grant(DOCTYPE, DEPT_HEAD_ROLE, ("read", "write", "email"))
    _grant("Employee", DEPT_HEAD_ROLE, ("read",))


def setup_leave_approval_workflow():
    ensure_role()
    ensure_workflow_states()
    ensure_permissions()

    wf = frappe.get_doc("Workflow", WORKFLOW_NAME) if frappe.db.exists("Workflow", WORKFLOW_NAME) \
        else frappe.new_doc("Workflow")

    wf.update({
        "doctype": "Workflow",
        "workflow_name": WORKFLOW_NAME,
        "document_type": DOCTYPE,
        "is_active": 1,
        "override_status": 1,
        "send_email_alert": 1,
        "workflow_state_field": "workflow_state",
    })

    wf.set("states", [])
    for state, doc_status, allow_edit, uf, uv in STATES:
        wf.append("states", {
            "state": state,
            "doc_status": doc_status,
            "allow_edit": allow_edit,
            "update_field": uf,
            "update_value": uv,
        })

    wf.set("transitions", [])
    for state, action, next_state, role, condition in TRANSITIONS:
        wf.append("transitions", {
            "state": state,
            "action": action,
            "next_state": next_state,
            "allowed": role,
            "allow_self_approval": 0,
            "condition": condition or "",
        })

    wf.save(ignore_permissions=True)
    frappe.db.commit()
    return wf.name
