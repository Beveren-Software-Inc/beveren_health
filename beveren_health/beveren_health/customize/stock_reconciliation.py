# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import frappe
from erpnext import is_perpetual_inventory_enabled
from frappe import _
from frappe.utils import cint, cstr, flt, nowdate, nowtime
from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file

from beveren_health.beveren_health.customize.dispensing_lot import (
	DISPENSING_LOT_FIELD,
	format_dispensing_lot_names_for_field,
)
from beveren_health.beveren_health.customize.stock_scanner import (
	_apply_stock_reconciliation_defaults,
)


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


# ─── Zero batches of a warehouse ────────────────────────────────────────────────
#
# A submitted Stock Reconciliation only covers the batch/warehouse combinations that
# were actually counted. Stock still sitting in the ledger for the same warehouse
# (typically a batch the scanner missed) keeps its balance forever. The helpers below
# find those combinations and build a follow-up draft Stock Reconciliation that zeroes
# them, so the ledger matches what was counted.
#
# The same batch balances also back the Zero Batch from Chosen Warehouse button: on a
# brand new reconciliation, Default Warehouse picks the location and the button fills
# the form with one zero-quantity line per batch in it, so a whole warehouse can be
# written off and submitted without scanning anything.
#
# Scope: only the warehouse the document was counted in (Set Warehouse), never every
# warehouse that happens to appear on a stray line, and never warehouses this document
# does not cover at all.
#
# Balances and values are summed from the Serial and Batch Entry rows of the Stock
# Ledger, which is the same source ERPNext uses itself (get_available_batches ->
# get_batch_qty -> get_stock_balance_for). Stock Ledger Entry.batch_no is NOT populated
# for bundle based stock movements, so it cannot be used for this. Summing the ledger
# also yields the valuation the system holds for the batch (value / qty), which the
# zeroing lines carry so the draft shows what is being written off instead of a zero.

UNRECONCILED_BATCH_QUERY = """
	SELECT
		sle.item_code AS item_code,
		sbe.batch_no AS batch_no,
		sbe.warehouse AS warehouse,
		SUM(sbe.qty) AS qty,
		SUM(sbe.stock_value_difference) AS value
	FROM `tabStock Ledger Entry` sle
	INNER JOIN `tabSerial and Batch Entry` sbe
		ON sle.serial_and_batch_bundle = sbe.parent
	INNER JOIN `tabBatch` b
		ON sbe.batch_no = b.name
	WHERE b.disabled = 0
		AND sle.is_cancelled = 0
		AND sle.warehouse IN %(warehouses)s
	GROUP BY sle.item_code, sbe.batch_no, sbe.warehouse
	HAVING SUM(sbe.qty) <> 0
"""

ZERO_BATCH_NOTE_PREFIX = "Zero un-reconciled batches from "
PREVIEW_LINE_LIMIT = 200


def _get_submitted_reconciliation(name):
	if not name:
		frappe.throw(_("Stock Reconciliation is required."))
	if not frappe.db.exists("Stock Reconciliation", name):
		frappe.throw(_("Stock Reconciliation {0} not found.").format(name))

	doc = frappe.get_doc("Stock Reconciliation", name)
	frappe.has_permission("Stock Reconciliation", "read", doc=doc, throw=True)

	if doc.docstatus != 1:
		frappe.throw(_("Zero Unreconciled Batches is only available on submitted Stock Reconciliation."))

	return doc


def _document_warehouses(doc):
	"""Warehouse(s) this reconciliation covers.

	A reconciliation is a count of one location, so only batches sitting in that
	location may be zeroed. That location is the Set Warehouse of the document.
	Stray lines in other warehouses must not widen the scope. Documents without a
	Set Warehouse fall back to the warehouses used on their lines.
	"""
	if doc.get("set_warehouse"):
		return [doc.set_warehouse]

	warehouses = []
	for row in doc.get("items") or []:
		warehouse = row.get("warehouse")
		if warehouse and warehouse not in warehouses:
			warehouses.append(warehouse)
	return warehouses


def _reconciled_batch_keys(doc):
	"""Item/batch/warehouse combinations already present on the reconciliation."""
	keys = set()
	for row in doc.get("items") or []:
		if row.item_code and row.batch_no:
			keys.add((row.item_code, row.batch_no, row.warehouse))
	return keys


def _zeroing_document_batch_keys(source_name):
	"""Combinations already covered by a draft/submitted document this feature created.

	Guards against double zeroing (and negative stock) when the action is run twice
	from the same reconciliation.
	"""
	keys = set()

	if not frappe.db.has_column("Stock Reconciliation", "custom_notes"):
		return keys

	names = frappe.get_all(
		"Stock Reconciliation",
		filters={
			"docstatus": ("<", 2),
			"custom_notes": ("like", f"{ZERO_BATCH_NOTE_PREFIX}{source_name}%"),
		},
		pluck="name",
	)
	if not names:
		return keys

	for row in frappe.get_all(
		"Stock Reconciliation Item",
		filters={"parent": ("in", names)},
		fields=["item_code", "batch_no", "warehouse"],
	):
		if row.batch_no:
			keys.add((row.item_code, row.batch_no, row.warehouse))

	return keys


def _lot_names_by_item_batch(item_codes, warehouses=None):
	"""{ (item_code, batch_no): [dispensing lot names] } for lots that still hold stock.

	Restricted to the warehouses in scope when they are known, so a lot whose stock
	sits elsewhere is never listed on a line for this reconciliation.
	"""
	if not item_codes:
		return {}

	filters = {"item": ("in", list(item_codes)), "remaining_qty": (">", 0)}
	if warehouses:
		filters["warehouse"] = ("in", list(warehouses))

	mapping = {}
	for row in frappe.get_all(
		"Dispensing Lot",
		filters=filters,
		fields=["name", "item", "batch_no"],
		order_by="name asc",
	):
		if row.batch_no:
			mapping.setdefault((row.item, row.batch_no), []).append(row.name)

	return mapping


def _item_details(item_codes):
	if not item_codes:
		return {}

	fields = ["name", "item_name", "stock_uom"]
	if frappe.db.has_column("Item", "custom_has_dispense_lot"):
		fields.append("custom_has_dispense_lot")

	return {
		row.name: row
		for row in frappe.get_all("Item", filters={"name": ("in", list(item_codes))}, fields=fields)
	}


def _batch_valuation_rate(value, qty):
	"""Valuation rate the ledger holds for a batch balance (same as ERPNext's own).

	This is the rate Stock Reconciliation will use when it writes the batch off, so the
	zeroing line displays it instead of a misleading zero. Stock Reconciliation rejects
	a negative rate, so a batch whose ledger value and quantity disagree in sign falls
	back to 0; the amount written off always comes from the ledger either way.
	"""
	if not flt(qty):
		return 0.0

	rate = flt(flt(value) / flt(qty))
	return rate if rate > 0 else 0.0


def _get_batch_balance_lines(warehouses, excluded=None):
	"""Batch/warehouse combinations holding stock in these warehouses.

	Returns one dict per combination, already enriched with item and dispensing lot
	information, sorted by warehouse/item/batch. Shared by the Zero Unreconciled
	Batches preview and the Zero Batch from Chosen Warehouse action; `excluded` holds
	the (item, batch, warehouse) combinations the caller wants to leave alone.
	"""
	if not warehouses:
		frappe.throw(_("This Stock Reconciliation has no warehouse on its lines."))

	excluded = excluded or set()

	balances = frappe.db.sql(UNRECONCILED_BATCH_QUERY, {"warehouses": warehouses}, as_dict=True)
	balances = [
		row
		for row in balances
		if row.batch_no and (row.item_code, row.batch_no, row.warehouse) not in excluded
	]
	if not balances:
		return []

	balances.sort(key=lambda row: (row.warehouse or "", row.item_code or "", row.batch_no or ""))

	items = _item_details({row.item_code for row in balances})
	lot_items = set()
	for row in balances:
		if cint((items.get(row.item_code) or {}).get("custom_has_dispense_lot")):
			lot_items.add(row.item_code)
	lots_by_item_batch = _lot_names_by_item_batch(lot_items, warehouses)

	lines = []
	for row in balances:
		item = items.get(row.item_code) or frappe._dict()
		needs_lot = bool(cint(item.get("custom_has_dispense_lot")))
		lots = lots_by_item_batch.get((row.item_code, row.batch_no)) or []
		qty = flt(row.qty)

		line = {
			"item_code": row.item_code,
			"item_name": item.get("item_name") or "",
			"stock_uom": item.get("stock_uom") or "",
			"warehouse": row.warehouse,
			"batch_no": row.batch_no,
			"qty": qty,
			"valuation_rate": _batch_valuation_rate(row.value, qty),
			"value": flt(row.value),
			"needs_dispensing_lot": needs_lot,
			"lots": lots,
			"lot_count": len(lots),
		}
		if needs_lot and not lots:
			line["warning"] = _(
				"No Dispensing Lot with stock was found for this batch. "
				"Add a lot to this line before submitting."
			)

		lines.append(line)

	return lines


def _get_unreconciled_batch_lines(doc):
	"""Batch/warehouse combinations holding stock that the reconciliation does not cover."""
	excluded = _reconciled_batch_keys(doc) | _zeroing_document_batch_keys(doc.name)
	return _get_batch_balance_lines(_document_warehouses(doc), excluded)


def _summarise_unreconciled_lines(lines):
	warehouses = {line["warehouse"] for line in lines}
	lot_lines = [line for line in lines if line["needs_dispensing_lot"]]

	return {
		"total_lines": len(lines),
		"total_qty": flt(sum(line["qty"] for line in lines)),
		"total_value": flt(sum(line["value"] for line in lines)),
		"warehouse_count": len(warehouses),
		"lot_lines": len(lot_lines),
		"lot_count": sum(line["lot_count"] for line in lot_lines),
		"warning_lines": len([line for line in lines if line.get("warning")]),
	}


@frappe.whitelist()
def get_unreconciled_batches(name: str):
	"""Preview of the batch/warehouse combinations a zeroing reconciliation would write off."""
	doc = _get_submitted_reconciliation(name)
	lines = _get_unreconciled_batch_lines(doc)

	summary = _summarise_unreconciled_lines(lines)
	summary["source"] = doc.name
	summary["company"] = doc.company
	summary["currency"] = frappe.get_cached_value("Company", doc.company, "default_currency")
	summary["warehouses"] = _document_warehouses(doc)
	summary["lines"] = lines[:PREVIEW_LINE_LIMIT]
	summary["truncated"] = len(lines) > PREVIEW_LINE_LIMIT

	return summary


def _build_zeroing_item_row(line):
	"""A Stock Reconciliation line that writes the batch balance off to zero.

	The quantity is 0, and the line keeps the valuation rate the system holds for the
	batch, so the draft shows the value being written off instead of a bare zero.
	Stock Reconciliation itself takes the write-off amount from the ledger, so the
	`current_*` columns are the counted balance and are for display only.

	The same shape is handed to the desk when a whole warehouse is zeroed from the
	form, so a line filled in the browser and a line created here are identical.
	"""
	qty = flt(line.get("qty"))
	rate = flt(line.get("valuation_rate"))
	value = flt(line.get("value"))

	item_row = {
		"item_code": line["item_code"],
		"item_name": line["item_name"],
		"warehouse": line["warehouse"],
		"batch_no": line["batch_no"],
		"qty": 0,
		"valuation_rate": rate,
		"amount": 0,
		"current_qty": qty,
		"current_valuation_rate": rate,
		"current_amount": value,
		"quantity_difference": -qty,
		"amount_difference": -value,
		"stock_uom": line["stock_uom"],
		"use_serial_batch_fields": 1,
		"allow_zero_valuation_rate": 1,
	}
	if line.get("lots") and frappe.db.has_column("Stock Reconciliation Item", DISPENSING_LOT_FIELD):
		item_row[DISPENSING_LOT_FIELD] = format_dispensing_lot_names_for_field(line["lots"])
	return item_row


@frappe.whitelist()
def create_unreconciled_batch_reconciliation(
	name: str, posting_date: str | None = None, posting_time: str | None = None
) -> str:
	"""Create a draft Stock Reconciliation zeroing every un-reconciled batch."""
	doc = _get_submitted_reconciliation(name)
	frappe.has_permission("Stock Reconciliation", "create", throw=True)

	lines = _get_unreconciled_batch_lines(doc)
	if not lines:
		frappe.throw(
			_("Every batch with stock in these warehouses is already covered by {0}.").format(doc.name)
		)

	sr = frappe.new_doc("Stock Reconciliation")
	sr.company = doc.company
	sr.purpose = "Stock Reconciliation"
	sr.posting_date = posting_date or nowdate()
	sr.posting_time = posting_time or nowtime()
	if doc.set_warehouse:
		sr.set_warehouse = doc.set_warehouse
	sr.cost_center = doc.cost_center or None
	if frappe.db.has_column("Stock Reconciliation", "custom_notes"):
		sr.custom_notes = f"{ZERO_BATCH_NOTE_PREFIX}{doc.name}"

	_apply_stock_reconciliation_defaults(sr, base_scanner=doc)

	if is_perpetual_inventory_enabled(sr.company) and not sr.expense_account:
		frappe.throw(
			_(
				"Could not resolve a Difference Account for {0}. Set a Stock Adjustment Account "
				"on the Company before zeroing un-reconciled batches."
			).format(sr.company)
		)

	for line in lines:
		sr.append("items", _build_zeroing_item_row(line))

	sr.insert()
	# The desk opens the new draft in a separate request right after this call (set_route),
	# so commit here to make sure the document is already on the database when that request
	# reads it - same pattern as create_stock_reconciliation_from_scanner.
	frappe.db.commit()  # nosemgrep

	return sr.name


def _zeroing_defaults(company, purpose=None):
	"""Difference Account and cost center the zeroing lines need, resolved as on a draft.

	Filled in by the desk only when the field is still empty, so a form the user already
	configured is never overwritten.
	"""
	if not company:
		return {}

	sr = frappe._dict(
		company=company,
		purpose=purpose or "Stock Reconciliation",
		cost_center=None,
		expense_account=None,
	)
	_apply_stock_reconciliation_defaults(sr)

	defaults = {
		"cost_center": sr.cost_center,
		"expense_account": sr.expense_account,
		"perpetual_inventory": bool(is_perpetual_inventory_enabled(company)),
	}
	return defaults


@frappe.whitelist()
def get_warehouse_zeroing_lines(
	warehouse: str, company: str | None = None, purpose: str | None = None
) -> dict:
	"""Every batch balance of one warehouse as zero-quantity reconciliation lines.

	Backs the Zero Batch from Chosen Warehouse button on a (draft) Stock Reconciliation:
	each batch holding stock in that warehouse is returned with the quantity it is to be
	counted down to (0), the valuation rate the ledger holds for it, and the dispensing
	lots of the batch, so the form can be filled and submitted without scanning.

	Nothing is written here — the lines are handed to the desk and the user submits the
	document. Submitting counts those batches down to zero and sets their dispensing lots
	to Inactive, exactly like a hand-written zero line.
	"""
	if not warehouse:
		frappe.throw(_("Set the Default Warehouse on this Stock Reconciliation first."))

	frappe.has_permission("Stock Reconciliation", "create", throw=True)
	frappe.has_permission("Warehouse", "read", doc=warehouse, throw=True)

	warehouse_details = frappe.db.get_value("Warehouse", warehouse, ["company", "is_group"], as_dict=True)
	if not warehouse_details:
		frappe.throw(_("Warehouse {0} not found.").format(warehouse))
	if cint(warehouse_details.is_group):
		frappe.throw(
			_("Warehouse {0} is a group warehouse and holds no stock. Pick the warehouse itself.").format(
				warehouse
			)
		)

	company = company or warehouse_details.company
	if warehouse_details.company and company and warehouse_details.company != company:
		frappe.throw(
			_("Warehouse {0} belongs to {1}. Change the Company on this Stock Reconciliation first.").format(
				warehouse, warehouse_details.company
			)
		)

	lines = _get_batch_balance_lines([warehouse])

	summary = _summarise_unreconciled_lines(lines)
	summary["warehouse"] = warehouse
	summary["warehouses"] = [warehouse]
	summary["company"] = company
	summary["currency"] = frappe.get_cached_value("Company", company, "default_currency") if company else None
	summary["lines"] = lines[:PREVIEW_LINE_LIMIT]
	summary["truncated"] = len(lines) > PREVIEW_LINE_LIMIT
	summary["grid_rows"] = [_build_zeroing_item_row(line) for line in lines]
	summary["defaults"] = _zeroing_defaults(company, purpose)

	return summary
