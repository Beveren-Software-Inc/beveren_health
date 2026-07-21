# Copyright (c) 2026, beveren_health contributors
"""ACC-113 / ACC-117 - NBR VAT return, laid out in filing order.

The Report record was created as a Script Report but this module was never
written, so opening the report raised "Not allowed source type: NoneType".
The calculation already existed in utils.vat_return; this is the report
surface over it.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import get_first_day, get_last_day, nowdate

from beveren_health.beveren_health.utils.vat_return import get_vat_return, get_vat_return_lines


def get_columns() -> list[dict]:
	return [
		{"fieldname": "box", "label": _("Box"), "fieldtype": "Data", "width": 60},
		{"fieldname": "description", "label": _("Description"), "fieldtype": "Data", "width": 380},
		{"fieldname": "amount", "label": _("Amount (excl. VAT)"), "fieldtype": "Currency", "width": 170},
		{"fieldname": "vat", "label": _("VAT"), "fieldtype": "Currency", "width": 150},
	]


def execute(filters: dict | None = None):
	filters = frappe._dict(filters or {})
	from_date = filters.get("from_date") or get_first_day(nowdate())
	to_date = filters.get("to_date") or get_last_day(nowdate())
	company = filters.get("company") or frappe.defaults.get_user_default("Company")

	lines = get_vat_return_lines(from_date, to_date, company)
	summary = get_vat_return(from_date, to_date, company)
	totals = summary["totals"]

	data = [
		{
			"box": row.get("box"),
			"description": row.get("description"),
			"amount": row.get("amount"),
			"vat": row.get("vat"),
		}
		for row in lines
	]

	# get_vat_return_lines already ends with the "Net VAT due" row, so only the
	# sales and purchase subtotals are added here.
	data.insert(
		len(data) - 1,
		{"description": _("Total sales"), "amount": totals["total_sales"], "vat": totals["output_vat"]},
	)
	data.insert(
		len(data) - 1,
		{
			"description": _("Total purchases"),
			"amount": totals["total_purchases"],
			"vat": totals["input_vat"],
		},
	)

	message = _(
		"Prepared from submitted invoices for {0} to {1}. Review before filing with the NBR."
	).format(from_date, to_date)

	return get_columns(), data, message
