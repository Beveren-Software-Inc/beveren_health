# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import cint, date_diff, getdate, today

from beveren_health.beveren_health.customize.dispensing_lot import (
	process_sales_invoice_dispensing_lots,
	reverse_sales_invoice_dispensing_lots,
	validate_sales_invoice_dispensing_lots,
)


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
			frappe.throw(f"Return not allowed for NHRA item {item.item_name}.")

		if days_diff > 14:
			frappe.throw("Items can only be returned before 14 days.")


def validate_dispensing_lots(doc, method):
	# Lot consumption belongs on Delivery Note / stock-updating invoices only.
	if not cint(doc.get("update_stock")):
		return
	validate_sales_invoice_dispensing_lots(doc)


def update_dispensing_lots_on_submit(doc, method):
	if not cint(doc.get("update_stock")):
		return
	process_sales_invoice_dispensing_lots(doc, is_return=bool(doc.get("is_return")))


def restore_dispensing_lots_on_cancel(doc, method):
	if not cint(doc.get("update_stock")):
		return
	reverse_sales_invoice_dispensing_lots(doc)
