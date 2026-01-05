import frappe
from frappe.utils import date_diff, today, getdate

def validate_return_restrictions(doc, method):
    
    if not doc.is_return or not doc.return_against:
        return
    
    return_date = getdate(doc.posting_date)
    original_invoice = frappe.get_doc("Sales Invoice", doc.return_against)
    invoice_date = getdate(original_invoice.posting_date)
    days_diff = date_diff(return_date, invoice_date)

    for item in original_invoice.items:
        item_group = frappe.db.get_value("Item", item.item_code, "item_group")
        is_refrigerated = frappe.db.get_value("Item", item.item_code, "custom_is_refrigerated_")
        if item_group in ["Narcotics", "Semi Control"] or is_refrigerated:
            frappe.throw(
                f"Return not allowed for NHRA item {item.item_name}."
            )
        
        if days_diff > 14:
            frappe.throw("Items can only be returned before 14 days.")
