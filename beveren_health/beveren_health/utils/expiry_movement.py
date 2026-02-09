# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate


def move_expired_batches_to_expiry_warehouse():
	"""
	Move expired batches from their current warehouse to the default expiry warehouse.
	Uses Stock Entry of type Material Transfer.
	Runs daily via scheduler (after midnight) or can be triggered manually from Stock Settings.
	"""
	# Get default expiry warehouse from Healthcare Settings
	try:
		default_expiry_warehouse = frappe.db.get_single_value(
			"Healthcare Settings", "default_expiry_warehouse"
		)
	except Exception:
		return {"success": False, "message": _("Healthcare Settings not found.")}

	if not default_expiry_warehouse:
		return {"success": False, "message": _("Default Expiry Warehouse is not set in Healthcare Settings.")}

	# Validate expiry warehouse exists
	if not frappe.db.exists("Warehouse", default_expiry_warehouse):
		return {"success": False, "message": _("Default Expiry Warehouse does not exist.")}

	expiry_warehouse_company = frappe.db.get_value("Warehouse", default_expiry_warehouse, "company")
	if not expiry_warehouse_company:
		return {"success": False, "message": _("Expiry warehouse has no company.")}

	today = getdate(nowdate())

	# Get all expired batches (expiry_date < today)
	expired_batches = frappe.db.sql(
		"""
		SELECT name, item
		FROM `tabBatch`
		WHERE expiry_date IS NOT NULL AND expiry_date < %s
		""",
		(today,),
		as_dict=True,
	)

	if not expired_batches:
		return {"success": True, "message": _("No expired batches found."), "stock_entries": []}

	# Get batch-wise stock for each expired batch (exclude expiry warehouse)
	items_to_transfer = []
	for batch_doc in expired_batches:
		batch_no = batch_doc.name
		item_code = batch_doc.item

		# get_batch_qty returns list of {batch_no, qty, warehouse} when warehouse is None
		from erpnext.stock.doctype.batch.batch import get_batch_qty

		batches = get_batch_qty(
			batch_no=batch_no,
			item_code=item_code,
			for_stock_levels=True,
			consider_negative_batches=False,
		)

		if not isinstance(batches, list):
			batches = [batches] if batches else []

		for b in batches:
			wh = b.get("warehouse") if isinstance(b, dict) else getattr(b, "warehouse", None)
			qty = flt(b.get("qty") if isinstance(b, dict) else getattr(b, "qty", 0))

			if not wh or not qty or qty <= 0:
				continue
			if wh == default_expiry_warehouse:
				continue

			# Ensure source warehouse is in same company as expiry warehouse
			wh_company = frappe.db.get_value("Warehouse", wh, "company")
			if wh_company != expiry_warehouse_company:
				continue

			items_to_transfer.append({
				"item_code": item_code,
				"batch_no": batch_no,
				"s_warehouse": wh,
				"t_warehouse": default_expiry_warehouse,
				"qty": qty,
			})

	if not items_to_transfer:
		return {"success": True, "message": _("No expired batch stock to move (all already in expiry warehouse)."), "stock_entries": []}

	# Create Stock Entry per company (Material Transfer)
	created_entries = []
	company_items = {}
	for row in items_to_transfer:
		company = frappe.db.get_value("Warehouse", row["s_warehouse"], "company")
		if company not in company_items:
			company_items[company] = []
		company_items[company].append(row)

	for company, rows in company_items.items():
		se_doc = frappe.get_doc(
			doctype="Stock Entry",
			purpose="Material Transfer",
			company=company,
			remarks=_("Expiry Movement: Moved expired batches to expiry warehouse"),
		)
		se_doc.set_stock_entry_type()

		for r in rows:
			se_doc.append(
				"items",
				{
					"item_code": r["item_code"],
					"batch_no": r["batch_no"],
					"s_warehouse": r["s_warehouse"],
					"t_warehouse": r["t_warehouse"],
					"qty": r["qty"],
					"transfer_qty": r["qty"],
				},
			)

		se_doc.insert()
		se_doc.submit()
		created_entries.append(se_doc.name)

	return {
		"success": True,
		"message": _("Moved {0} expired batch item(s) to expiry warehouse.").format(len(items_to_transfer)),
		"stock_entries": created_entries,
	}


@frappe.whitelist()
def trigger_expiry_movement():
	"""Whitelisted method to trigger expiry movement from Stock Settings button."""
	result = move_expired_batches_to_expiry_warehouse()
	return result
