# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cstr, flt
from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file


def _valuation_rates_from_file(file_url):
	"""Return {item_code: valuation_rate} from the spreadsheet."""
	if not file_url:
		frappe.throw(_("Upload the valuation rate spreadsheet."))

	rows = read_xlsx_file_from_attached_file(file_url=file_url) or []
	if not rows:
		frappe.throw(_("The spreadsheet is empty."))

	header = [cstr(cell).strip().lower() for cell in (rows[0] or [])]

	try:
		item_idx = header.index("item_code")
	except ValueError:
		frappe.throw(_("The spreadsheet must have an item_code column."))

	rate_idx = None
	for label in ("valuation rate", "valuation_rate", "rate"):
		if label in header:
			rate_idx = header.index(label)
			break
	if rate_idx is None:
		frappe.throw(_("The spreadsheet must have a Valuation rate column."))

	rates = {}
	for row in rows[1:]:
		if not row or item_idx >= len(row):
			continue
		item_code = cstr(row[item_idx]).strip()
		if not item_code:
			continue
		rate_raw = row[rate_idx] if rate_idx < len(row) else None
		if rate_raw in (None, ""):
			continue
		rates[item_code] = flt(rate_raw)

	if not rates:
		frappe.throw(_("No valuation rates found in the spreadsheet."))
	return rates


@frappe.whitelist()
def update_valuation_rates_from_file(name: str, file_url: str):
	"""
	Update Stock Reconciliation item valuation_rate from an uploaded spreadsheet
	with item_code and Valuation rate columns.
	"""
	if not name:
		frappe.throw(_("Stock Reconciliation is required."))
	if not frappe.db.exists("Stock Reconciliation", name):
		frappe.throw(_("Stock Reconciliation {0} not found.").format(name))

	doc = frappe.get_doc("Stock Reconciliation", name)
	frappe.has_permission("Stock Reconciliation", "write", doc=doc, throw=True)

	if doc.docstatus != 0:
		frappe.throw(_("Update Reconciliation is only allowed on draft Stock Reconciliation."))

	rates = _valuation_rates_from_file(file_url)

	updated = []
	unchanged = []
	not_in_file = []

	for row in doc.get("items") or []:
		if not row.item_code:
			continue
		if row.item_code not in rates:
			not_in_file.append(
				{
					"idx": row.idx,
					"item_code": row.item_code,
					"item_name": row.item_name or "",
				}
			)
			continue

		new_rate = flt(rates[row.item_code])
		old_rate = flt(row.valuation_rate)
		if old_rate == new_rate:
			unchanged.append(row.item_code)
			continue

		row.valuation_rate = new_rate
		row.amount = flt(row.qty) * new_rate
		if hasattr(row, "allow_zero_valuation_rate"):
			row.allow_zero_valuation_rate = 1
		updated.append(
			{
				"idx": row.idx,
				"item_code": row.item_code,
				"item_name": row.item_name or "",
				"old_rate": old_rate,
				"new_rate": new_rate,
			}
		)

	if updated:
		doc.flags.ignore_validate_update_after_submit = True
		doc.save()

	message = _(
		"Updated valuation on {0} line(s). {1} already matched. {2} line(s) had no rate in the file."
	).format(len(updated), len(unchanged), len(not_in_file))

	return {
		"message": message,
		"updated_count": len(updated),
		"unchanged_count": len(unchanged),
		"missing_count": len(not_in_file),
		"updated": updated,
		"missing": not_in_file[:50],
	}
