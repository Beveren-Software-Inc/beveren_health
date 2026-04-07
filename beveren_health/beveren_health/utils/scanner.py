import frappe
from frappe.utils import flt

@frappe.whitelist()
def get_item_and_batch_from_barcode(barcode, warehouse=None):
    """
    Resolve a scanned barcode to item_code and batch_no.
    Checks:
    1. Delimiter-based barcode (ITEMCODE|BATCHNO)
    2. Standard ERPNext item barcode fallback
    """
    result = {
        "item_code": None,
        "batch_no": None,
        "qty": 1
    }

    if not barcode:
        return result

    # 1. Check delimiter-based barcode (ITEMCODE|BATCHNO)
    if "|" in barcode:
        parts = barcode.split("|")
        if len(parts) == 2:
            item_code, batch_no = parts
            if frappe.db.exists("Item", item_code):
                result["item_code"] = item_code
                if frappe.db.exists("Batch", {"name": batch_no, "item": item_code}):
                    result["batch_no"] = batch_no
                return _with_batch_qty(result, warehouse)

    # 2. Fallback to standard ERPNext item barcode
    item_match = frappe.db.get_value(
        "Item Barcode",
        {"barcode": barcode},
        ["parent", "custom_batch"],
        as_dict=True
    )
    if item_match:
        result["item_code"] = item_match.parent
        result["batch_no"] = item_match.get("custom_batch")
        return _with_batch_qty(result, warehouse)

    return result


def _with_batch_qty(result, warehouse):
    """If we have a batch and a warehouse, pull the actual stock balance."""
    if result.get("batch_no") and warehouse:
        from erpnext.stock.doctype.batch.batch import get_batch_qty
        qty = get_batch_qty(
            batch_no=result["batch_no"],
            warehouse=warehouse,
            item_code=result["item_code"]
        )
        result["qty"] = max(flt(qty), 0) or 1

    return result
