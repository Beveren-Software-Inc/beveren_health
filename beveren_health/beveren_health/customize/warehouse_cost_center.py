# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import frappe


def get_warehouse_cost_center(warehouse):
	if not warehouse:
		return None
	return frappe.db.get_value("Warehouse", warehouse, "custom_cost_center")


def _apply_cost_center(doc, warehouse, force=False):
	cost_center = get_warehouse_cost_center(warehouse)
	if not cost_center:
		return

	meta = frappe.get_meta(doc.doctype)
	if meta.has_field("cost_center") and (force or not doc.get("cost_center")):
		doc.cost_center = cost_center

	items = doc.get("items") or []
	if not items:
		return

	item_meta = frappe.get_meta(items[0].doctype)
	if not item_meta.has_field("cost_center"):
		return

	for item in items:
		if force or not item.get("cost_center"):
			item.cost_center = cost_center


def set_cost_center_from_set_warehouse(doc, method=None):
	"""PO / PR / PI / Stock Reconciliation: use set_warehouse."""
	warehouse = doc.get("set_warehouse")
	if not warehouse:
		for item in doc.get("items") or []:
			warehouse = item.get("warehouse")
			if warehouse:
				break
	if warehouse:
		_apply_cost_center(doc, warehouse)


def set_cost_center_from_stock_entry_warehouse(doc, method=None):
	"""Stock Entry: prefer to_warehouse, else from_warehouse; rows use t/s warehouse."""
	header_warehouse = doc.get("to_warehouse") or doc.get("from_warehouse")
	if header_warehouse:
		_apply_cost_center(doc, header_warehouse)

	for item in doc.get("items") or []:
		row_warehouse = item.get("t_warehouse") or item.get("s_warehouse")
		cost_center = get_warehouse_cost_center(row_warehouse)
		if cost_center and not item.get("cost_center"):
			item.cost_center = cost_center
