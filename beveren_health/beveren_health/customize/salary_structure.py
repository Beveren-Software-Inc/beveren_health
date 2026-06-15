import frappe


def before_insert(doc, method):
    gosi_component = frappe.db.get_single_value("Payroll Settings", "custom_gosi_component")
    if not gosi_component:
        return

    already_added = any(row.salary_component == gosi_component for row in doc.deductions)
    if already_added:
        return

    abbr = frappe.db.get_value("Salary Component", gosi_component, "salary_component_abbr")
    doc.append("deductions", {
        "salary_component": gosi_component,
        "abbr": abbr or "",
        "amount": 0,
        "statistical_component": 0,
        "depends_on_payment_days": 1,
    })
