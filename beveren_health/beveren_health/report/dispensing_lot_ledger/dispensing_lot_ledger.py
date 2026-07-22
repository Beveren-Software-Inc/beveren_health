# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, today


def execute(filters: dict | None = None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns() -> list[dict]:
	return [
		{
			"label": _("Date"),
			"fieldname": "posting_date",
			"fieldtype": "Date",
			"width": 100,
		},
		{
			"label": _("Days"),
			"fieldname": "days",
			"fieldtype": "Int",
			"width": 70,
		},
		{
			"label": _("Dispensing Lot"),
			"fieldname": "dispensing_lot",
			"fieldtype": "Link",
			"options": "Dispensing Lot",
			"width": 160,
		},
		{
			"label": _("Batch"),
			"fieldname": "batch_no",
			"fieldtype": "Link",
			"options": "Batch",
			"width": 120,
		},
		{
			"label": _("Item"),
			"fieldname": "item",
			"fieldtype": "Link",
			"options": "Item",
			"width": 120,
		},
		{
			"label": _("Item Name"),
			"fieldname": "item_name",
			"fieldtype": "Data",
			"width": 160,
		},
		{
			"label": _("Warehouse"),
			"fieldname": "warehouse",
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 140,
		},
		{
			"label": _("Cost Center"),
			"fieldname": "cost_center",
			"fieldtype": "Link",
			"options": "Cost Center",
			"width": 140,
		},
		{
			"label": _("Movement"),
			"fieldname": "movement",
			"fieldtype": "Data",
			"width": 90,
		},
		{
			"label": _("Qty"),
			"fieldname": "qty",
			"fieldtype": "Float",
			"width": 90,
		},
		{
			"label": _("UOM"),
			"fieldname": "uom",
			"fieldtype": "Link",
			"options": "UOM",
			"width": 80,
		},
		{
			"label": _("Transaction DocType"),
			"fieldname": "transaction_doctype",
			"fieldtype": "Link",
			"options": "DocType",
			"width": 150,
		},
		{
			"label": _("Transaction"),
			"fieldname": "transaction_name",
			"fieldtype": "Dynamic Link",
			"options": "transaction_doctype",
			"width": 160,
		},
		{
			"label": _("Remaining Qty"),
			"fieldname": "remaining_qty",
			"fieldtype": "Float",
			"width": 110,
		},
		{
			"label": _("Status"),
			"fieldname": "status",
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"label": _("Remarks"),
			"fieldname": "remarks",
			"fieldtype": "Data",
			"width": 180,
		},
	]


def get_conditions(filters: frappe._dict) -> tuple[str, dict]:
	conditions = ["1=1"]
	values = {}

	if filters.get("from_date"):
		conditions.append("dlt.posting_date >= %(from_date)s")
		values["from_date"] = filters.from_date

	if filters.get("to_date"):
		conditions.append("dlt.posting_date <= %(to_date)s")
		values["to_date"] = filters.to_date

	if filters.get("item"):
		conditions.append("dl.item = %(item)s")
		values["item"] = filters.item

	if filters.get("batch_no"):
		conditions.append("dl.batch_no = %(batch_no)s")
		values["batch_no"] = filters.batch_no

	if filters.get("warehouse"):
		conditions.append("dl.warehouse = %(warehouse)s")
		values["warehouse"] = filters.warehouse

	if filters.get("cost_center"):
		conditions.append("wh.custom_cost_center = %(cost_center)s")
		values["cost_center"] = filters.cost_center

	if filters.get("dispensing_lot"):
		conditions.append("dl.name = %(dispensing_lot)s")
		values["dispensing_lot"] = filters.dispensing_lot

	if filters.get("movement"):
		conditions.append("dlt.transaction_type = %(movement)s")
		values["movement"] = filters.movement

	if filters.get("transaction_doctype"):
		conditions.append("dlt.reference_doctype = %(transaction_doctype)s")
		values["transaction_doctype"] = filters.transaction_doctype

	if filters.get("status"):
		conditions.append("dl.status = %(status)s")
		values["status"] = filters.status

	return " and ".join(conditions), values


def get_data(filters: frappe._dict) -> list[dict]:
	conditions, values = get_conditions(filters)
	as_on = getdate(filters.get("to_date") or today())

	rows = frappe.db.sql(
		f"""
		select
			dlt.posting_date,
			dl.name as dispensing_lot,
			dl.batch_no,
			dl.item,
			dl.item_name,
			dl.warehouse,
			wh.custom_cost_center as cost_center,
			dlt.transaction_type as movement,
			dlt.qty,
			dlt.uom,
			dlt.reference_doctype as transaction_doctype,
			dlt.reference_name as transaction_name,
			dl.remaining_qty,
			dl.status,
			dlt.remarks
		from `tabDispensing Lot Transaction` dlt
		inner join `tabDispensing Lot` dl on dl.name = dlt.parent
		left join `tabWarehouse` wh on wh.name = dl.warehouse
		where {conditions}
		order by dlt.posting_date asc, dl.name asc, dlt.idx asc
		""",
		values,
		as_dict=True,
	)

	for row in rows:
		posting_date = getdate(row.posting_date) if row.posting_date else None
		row["days"] = date_diff(as_on, posting_date) if posting_date else None

		# Signed qty for totals: In +, Out -, Transfer 0 movement impact
		if row.movement == "Out":
			row["qty"] = -abs(row.qty or 0)
		elif row.movement == "Transfer":
			row["qty"] = 0
		else:
			row["qty"] = abs(row.qty or 0)

	return rows
