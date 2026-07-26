# Serene — IP Package Approval workflow on Quotation.
#
# Patient package quotations:
#   * Standard package -> pre-approved; Reception activates in one step (submitted,
#     flows to Accounts as approved).
#   * Custom package (or any modification of a standard one) -> mandatory sequential
#     chain, blocked until all three approve:
#         Patient Relations Manager -> CEO -> Chairman
#     Any rejection -> Rejected (resubmit a new request from step 1).
#
# Built as a native Frappe Workflow so approvals are permissioned, email-alerted and
# audit-logged. Idempotent: safe to re-run (patch + manual).

import frappe

WF_NAME = "IP Package Approval (Quotation)"
OLD_WF = "Quotation"           # the previous single-level CEO workflow (deactivated)
DOCTYPE = "Quotation"

PRM = "Patient Relations Manager"
CEO = "CEO"
CHAIRMAN = "Chairman"
SALES = "Sales User"           # Reception / quotation creators

CUSTOM_STATES = ["Pending Patient Relations Manager", "Pending CEO", "Pending Chairman"]

# (state, doc_status, allow_edit)
STATES = [
    ("Draft",                              "0", SALES),
    ("Pending Patient Relations Manager",  "0", PRM),
    ("Pending CEO",                        "0", CEO),
    ("Pending Chairman",                   "0", CHAIRMAN),
    ("Approved",                           "1", SALES),
    ("Rejected",                           "0", SALES),
]

STD = 'doc.custom_package_type == "Standard"'
CUS = 'doc.custom_package_type == "Custom"'

# (state, action, next_state, allowed_role, condition)
TRANSITIONS = [
    ("Draft", "Activate (Standard Package)", "Approved",                          SALES,    STD),
    ("Draft", "Submit for Approval",         "Pending Patient Relations Manager", SALES,    CUS),
    ("Pending Patient Relations Manager", "Approve", "Pending CEO",      PRM,      None),
    ("Pending Patient Relations Manager", "Reject",  "Rejected",         PRM,      None),
    ("Pending CEO",      "Approve", "Pending Chairman", CEO,      None),
    ("Pending CEO",      "Reject",  "Rejected",         CEO,      None),
    ("Pending Chairman", "Approve", "Approved",         CHAIRMAN, None),
    ("Pending Chairman", "Reject",  "Rejected",         CHAIRMAN, None),
]


def ensure_roles():
    for r in (PRM, CHAIRMAN):
        if not frappe.db.exists("Role", r):
            frappe.get_doc({"doctype": "Role", "role_name": r, "desk_access": 1}).insert(ignore_permissions=True)


def ensure_states():
    for s in CUSTOM_STATES:
        if not frappe.db.exists("Workflow State", s):
            frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": s,
                            "style": "Warning"}).insert(ignore_permissions=True)


def ensure_actions():
    for a in ("Activate (Standard Package)", "Submit for Approval"):
        if not frappe.db.exists("Workflow Action Master", a):
            frappe.get_doc({"doctype": "Workflow Action Master",
                            "workflow_action_name": a}).insert(ignore_permissions=True)


def ensure_package_type_field():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_field
    if not frappe.db.exists("Custom Field", "Quotation-custom_package_type"):
        insert_after = "custom_package" if frappe.db.exists("Custom Field", "Quotation-custom_package") else "quotation_to"
        create_custom_field(DOCTYPE, {
            "fieldname": "custom_package_type",
            "label": "Package Type",
            "fieldtype": "Select",
            "options": "Standard\nCustom",
            "default": "Standard",
            "insert_after": insert_after,
            "in_standard_filter": 1,
        })


def _grant(doctype, role, props):
    from frappe.permissions import add_permission, update_permission_property
    has = frappe.get_all("Custom DocPerm", filters={"parent": doctype, "role": role, "permlevel": 0}, limit=1) \
        or frappe.get_all("DocPerm", filters={"parent": doctype, "role": role, "permlevel": 0}, limit=1)
    if not has:
        add_permission(doctype, role, 0)
    for p in props:
        update_permission_property(doctype, role, 0, p, 1)


def ensure_permissions():
    _grant(DOCTYPE, PRM, ("read", "write", "email"))
    _grant(DOCTYPE, CEO, ("read", "write", "submit", "email"))
    _grant(DOCTYPE, CHAIRMAN, ("read", "write", "submit", "email"))
    # Quotation.validate re-reads party details -> approvers need to read the Customer.
    for role in (PRM, CEO, CHAIRMAN):
        _grant("Customer", role, ("read",))


def setup_quotation_approval_workflow():
    ensure_roles()
    ensure_states()
    ensure_actions()
    ensure_package_type_field()
    ensure_permissions()

    # only one active workflow per doctype — retire the old single-level one
    if frappe.db.exists("Workflow", OLD_WF) and OLD_WF != WF_NAME:
        frappe.db.set_value("Workflow", OLD_WF, "is_active", 0)

    wf = frappe.get_doc("Workflow", WF_NAME) if frappe.db.exists("Workflow", WF_NAME) else frappe.new_doc("Workflow")
    wf.update({
        "doctype": "Workflow",
        "workflow_name": WF_NAME,
        "document_type": DOCTYPE,
        "is_active": 1,
        "send_email_alert": 1,
        "workflow_state_field": "workflow_state",
    })
    wf.set("states", [])
    for state, doc_status, allow_edit in STATES:
        wf.append("states", {"state": state, "doc_status": doc_status, "allow_edit": allow_edit})
    wf.set("transitions", [])
    for state, action, next_state, role, condition in TRANSITIONS:
        wf.append("transitions", {"state": state, "action": action, "next_state": next_state,
                                  "allowed": role, "allow_self_approval": 1, "condition": condition or ""})
    wf.save(ignore_permissions=True)
    frappe.db.commit()
    return wf.name
