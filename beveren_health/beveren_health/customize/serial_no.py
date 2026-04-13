

import frappe 
import frappe

def set_gtin_universal(doc, method):
    # if not doc.name:
    #     return
    
    voucher_type = doc.reference_doctype
    voucher_no = doc.reference_name

    if not voucher_type or not voucher_no:
        return

    # Map parent -> child table
    doctype_map = {
        "Purchase Receipt": "Purchase Receipt Item",
        "Stock Entry": "Stock Entry Detail",
        "Stock Reconciliation": "Stock Reconciliation Item"
    }

    child_doctype = doctype_map.get(voucher_type)

    if not child_doctype:
        return

    # Fetch rows
    rows = frappe.get_all(
        child_doctype,
        filters={"parent": voucher_no},
        fields=["serial_no", "custom_gstin"]
    )
    frappe.throw("" + str(rows))
    for row in rows:
        if not row.serial_no or not row.custom_gstin:
            continue

        # Normalize serial list
        serials = []
        if "\n" in row.serial_no:
            serials = row.serial_no.split("\n")
        elif "," in row.serial_no:
            serials = row.serial_no.split(",")
        else:
            serials = [row.serial_no]

        serials = [s.strip() for s in serials]

        if doc.name in serials:
            frappe.db.set_value(
                "Serial No",
                doc.name,
                "custom_gtin",
                row.custom_gstin
            )
            return
        
import frappe

def split_serials(serial_no):
    if not serial_no:
        return []

    if "\n" in serial_no:
        return [s.strip() for s in serial_no.split("\n")]
    if "," in serial_no:
        return [s.strip() for s in serial_no.split(",")]

    return [serial_no.strip()]


def update_serial_gtin(doc, method):
    # Map parent doctype → child table field
    child_table_map = {
        "Purchase Receipt": "items",
        "Stock Entry": "items",
        "Stock Reconciliation": "items"
    }

    child_field = child_table_map.get(doc.doctype)

    if not child_field:
        return

    for row in doc.get(child_field):
        if not row.serial_no or not row.custom_gstin:
            continue

        serials = split_serials(row.serial_no)

        for serial in serials:
            if not serial:
                continue

            # Update Serial No
            frappe.db.set_value(
                "Serial No",
                serial,
                "custom_gtin",
                row.custom_gstin
            )
            
            