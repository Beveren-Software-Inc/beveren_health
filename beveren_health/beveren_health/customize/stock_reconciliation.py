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
# were saved on it. Stock still sitting in the ledger for the same warehouse keeps
# its balance. The helpers below find those combinations and build a follow-up draft
# that zeroes them.
#
# A batch is left alone when it is already on this reconciliation, or when it was
# counted on a Stock Scanner that created this reconciliation (even if ERPNext later
# dropped the line because the quantity already matched). Only the scanners linked
# to this document are read, and only in the warehouse this reconciliation covers.
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


def _line_warehouse(row, fallback=None):
	return row.get("warehouse") or fallback or ""


def _reconciled_batch_keys(doc):
	"""Item/batch/warehouse combinations already present on the reconciliation."""
	fallback = doc.get("set_warehouse")
	keys = set()
	for row in doc.get("items") or []:
		warehouse = _line_warehouse(row, fallback)
		if row.item_code and row.batch_no and warehouse:
			keys.add((row.item_code, row.batch_no, warehouse))
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


def _scanner_batch_keys(doc):
	"""Batches counted on the Stock Scanners that created this reconciliation.

	Limited to this document's warehouse. A counted batch must not be zeroed just
	because it was left off the reconciliation when the quantity already matched.
	"""
	warehouses = _document_warehouses(doc)
	names = _scanners_linked_to_reconciliation(doc)
	if not warehouses or not names:
		return set()

	keys = set()
	for entry in _counted_lines_from_scanners(names, warehouses).values():
		if entry["item_code"] and entry["batch_no"]:
			keys.add((entry["item_code"], entry["batch_no"], entry["warehouse"]))
	return keys


def _get_unreconciled_batch_lines(doc):
	"""Stock in this warehouse that is neither on the reconciliation nor on its scanners."""
	excluded = _reconciled_batch_keys(doc) | _zeroing_document_batch_keys(doc.name) | _scanner_batch_keys(doc)
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
			_(
				"Every batch with stock in this warehouse is already on {0} or was counted on the Stock Scanners that created it."
			).format(doc.name)
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


# ─── Restore stock that was counted but dropped because the quantity matched ─────
#
# Creating a Stock Reconciliation from Stock Scanners includes every counted line.
# On save, ERPNext drops a line whose counted quantity and rate already match the
# ledger ("Removed items with no change in quantity or value"). Those lines are
# therefore absent from the submitted reconciliation.
#
# Zero Unreconciled Batches treats "not on this reconciliation" as "not counted"
# and writes the balance to zero. Counted lines that were only dropped because
# they matched are zeroed too. This button rebuilds a draft from the linked
# Stock Scanners for just those missing lines, at the quantity that was counted,
# so submitting it puts that stock back.

RESTORE_SCANNER_NOTE_PREFIX = "Restore missed scanner stock from "


def _scanners_linked_to_reconciliation(doc):
	"""Stock Scanners this reconciliation was created from."""
	names = []
	if frappe.db.has_column("Stock Scanner", "stock_reconciliation"):
		names = frappe.get_all(
			"Stock Scanner",
			filters={"stock_reconciliation": doc.name, "docstatus": ("<", 2)},
			pluck="name",
		)

	if frappe.db.has_column("Stock Reconciliation Item", "custom_stock_scanner"):
		for row in doc.get("items") or []:
			for part in (row.get("custom_stock_scanner") or "").split(","):
				name = part.strip()
				if name and name not in names and frappe.db.exists("Stock Scanner", name):
					names.append(name)

	return names


def _counted_lines_from_scanners(scanner_names, warehouses):
	"""Merge lines from the scanners that created this reconciliation, in its warehouse only."""
	from beveren_health.beveren_health.customize.dispensing_lot import split_dispensing_lots

	allowed = set(warehouses or [])
	merged = {}
	if not scanner_names or not allowed:
		return merged

	for name in scanner_names:
		scanner = frappe.get_doc("Stock Scanner", name)
		default_wh = scanner.set_warehouse
		for row in scanner.get("items") or []:
			if not row.item_code:
				continue
			warehouse = row.warehouse or default_wh
			if not warehouse or warehouse not in allowed:
				continue
			key = (row.item_code, row.batch_no or "", warehouse)
			lots = split_dispensing_lots(row.get("serial_no") or "")
			if key not in merged:
				merged[key] = {
					"item_code": row.item_code,
					"item_name": row.item_name or "",
					"batch_no": row.batch_no or "",
					"warehouse": warehouse,
					"qty": flt(row.qty),
					"valuation_rate": flt(row.valuation_rate),
					"stock_uom": row.stock_uom or "",
					"lots": list(lots),
					"gtin": row.get("gtin") or "",
					"manufacturing_date": row.get("manufacturing_date"),
					"expiry_date": row.get("expiry_date"),
					"stock_scanners": [scanner.name],
				}
			else:
				entry = merged[key]
				entry["qty"] = flt(entry["qty"]) + flt(row.qty)
				for lot in lots:
					if lot and lot not in entry["lots"]:
						entry["lots"].append(lot)
				if scanner.name not in entry["stock_scanners"]:
					entry["stock_scanners"].append(scanner.name)
				if not entry["valuation_rate"] and flt(row.valuation_rate):
					entry["valuation_rate"] = flt(row.valuation_rate)
	return merged


def _sr_line_keys(doc):
	fallback = doc.get("set_warehouse")
	keys = set()
	for row in doc.get("items") or []:
		if not row.item_code:
			continue
		warehouse = _line_warehouse(row, fallback)
		if warehouse:
			keys.add((row.item_code, row.batch_no or "", warehouse))
	return keys


def _existing_restore_reconciliation(source_name):
	if not frappe.db.has_column("Stock Reconciliation", "custom_notes"):
		return None
	return frappe.db.get_value(
		"Stock Reconciliation",
		{
			"docstatus": ("<", 2),
			"custom_notes": ("like", f"{RESTORE_SCANNER_NOTE_PREFIX}{source_name}%"),
		},
		"name",
	)


def _ledger_qty_and_rate(item_code, warehouse, batch_no, posting_date, posting_time):
	"""Current quantity (batch quantity when a batch is set) and warehouse valuation rate."""
	from erpnext.stock.doctype.batch.batch import get_batch_qty
	from erpnext.stock.utils import get_stock_balance

	balance = get_stock_balance(item_code, warehouse, posting_date, posting_time, with_valuation_rate=True)
	qty, rate = balance if isinstance(balance, tuple) else (balance, 0)
	if batch_no:
		qty = (
			get_batch_qty(
				batch_no,
				warehouse,
				item_code,
				posting_date=posting_date,
				posting_time=posting_time,
				for_stock_levels=True,
				consider_negative_batches=True,
			)
			or 0
		)
	return flt(qty), flt(rate)


def _missed_scanner_lines(doc):
	"""Counted scanner lines that are not on this reconciliation and no longer match stock."""
	scanner_names = _scanners_linked_to_reconciliation(doc)
	if not scanner_names:
		frappe.throw(
			_("{0} was not created from Stock Scanners, so there are no counted lines to restore.").format(
				doc.name
			)
		)

	warehouses = _document_warehouses(doc)
	if not warehouses:
		frappe.throw(_("Set a warehouse on {0} before restoring counted stock.").format(doc.name))

	on_document = _sr_line_keys(doc)
	posting_date = nowdate()
	posting_time = nowtime()
	missed = []
	unchanged = 0

	for key, entry in _counted_lines_from_scanners(scanner_names, warehouses).items():
		if key in on_document:
			continue

		counted_qty = flt(entry["qty"])
		if not counted_qty:
			counted_qty = len(entry["lots"]) if entry["lots"] else 1
		entry["qty"] = counted_qty

		current_qty, current_rate = _ledger_qty_and_rate(
			entry["item_code"],
			entry["warehouse"],
			entry["batch_no"],
			posting_date,
			posting_time,
		)
		if flt(counted_qty, 6) == flt(current_qty, 6):
			unchanged += 1
			continue

		rate = flt(entry["valuation_rate"]) or current_rate
		entry["current_qty"] = current_qty
		entry["current_valuation_rate"] = current_rate
		entry["valuation_rate"] = rate
		entry["value"] = counted_qty * rate
		missed.append(entry)

	missed.sort(key=lambda row: (row["warehouse"], row["item_code"], row["batch_no"]))
	return scanner_names, missed, unchanged


def _build_restore_item_row(line):
	qty = flt(line["qty"])
	rate = flt(line["valuation_rate"])
	current_qty = flt(line.get("current_qty"))
	current_rate = flt(line.get("current_valuation_rate"))

	item_row = {
		"item_code": line["item_code"],
		"item_name": line["item_name"],
		"warehouse": line["warehouse"],
		"batch_no": line["batch_no"] or None,
		"qty": qty,
		"valuation_rate": rate,
		"amount": qty * rate,
		"current_qty": current_qty,
		"current_valuation_rate": current_rate,
		"current_amount": current_qty * current_rate,
		"quantity_difference": qty - current_qty,
		"amount_difference": (qty * rate) - (current_qty * current_rate),
		"stock_uom": line["stock_uom"],
		"use_serial_batch_fields": 1,
		"allow_zero_valuation_rate": 1,
	}
	if line.get("lots") and frappe.db.has_column("Stock Reconciliation Item", DISPENSING_LOT_FIELD):
		item_row[DISPENSING_LOT_FIELD] = format_dispensing_lot_names_for_field(line["lots"])
	if frappe.db.has_column("Stock Reconciliation Item", "custom_stock_scanner"):
		item_row["custom_stock_scanner"] = ", ".join(line.get("stock_scanners") or [])
	if line.get("gtin") and frappe.db.has_column("Stock Reconciliation Item", "custom_gstin"):
		item_row["custom_gstin"] = line["gtin"]
	if line.get("manufacturing_date") and frappe.db.has_column(
		"Stock Reconciliation Item", "custom_manufacturing_date"
	):
		item_row["custom_manufacturing_date"] = line["manufacturing_date"]
	if line.get("expiry_date") and frappe.db.has_column("Stock Reconciliation Item", "custom_expiry_date"):
		item_row["custom_expiry_date"] = line["expiry_date"]
	return item_row


@frappe.whitelist()
def get_missed_scanner_lines(name: str):
	"""Preview counted scanner lines missing from this reconciliation."""
	doc = _get_submitted_reconciliation(name)
	scanners, missed, unchanged = _missed_scanner_lines(doc)
	existing = _existing_restore_reconciliation(doc.name)

	return {
		"source": doc.name,
		"scanners": scanners,
		"unchanged": unchanged,
		"existing": existing,
		"currency": frappe.get_cached_value("Company", doc.company, "default_currency"),
		"total_lines": len(missed),
		"total_qty": flt(sum(flt(row["qty"]) for row in missed)),
		"lines": [
			{
				"item_code": row["item_code"],
				"item_name": row["item_name"],
				"warehouse": row["warehouse"],
				"batch_no": row["batch_no"],
				"qty": row["qty"],
				"current_qty": row["current_qty"],
				"valuation_rate": row["valuation_rate"],
				"stock_scanners": ", ".join(row.get("stock_scanners") or []),
			}
			for row in missed[:PREVIEW_LINE_LIMIT]
		],
		"truncated": len(missed) > PREVIEW_LINE_LIMIT,
	}


@frappe.whitelist()
def create_missed_scanner_reconciliation(name: str, posting_date: str | None = None) -> str:
	"""Draft Stock Reconciliation for counted lines dropped because the quantity matched."""
	doc = _get_submitted_reconciliation(name)
	frappe.has_permission("Stock Reconciliation", "create", throw=True)

	existing = _existing_restore_reconciliation(doc.name)
	if existing:
		frappe.throw(
			_("Draft or submitted reconciliation {0} already restores the missed lines of {1}.").format(
				existing, doc.name
			)
		)

	_scanners, missed, _unchanged = _missed_scanner_lines(doc)
	if not missed:
		frappe.throw(
			_(
				"No counted Stock Scanner line is missing from {0}. Lines whose quantity still matches stock are left out."
			).format(doc.name)
		)

	sr = frappe.new_doc("Stock Reconciliation")
	sr.company = doc.company
	sr.purpose = "Stock Reconciliation"
	sr.posting_date = posting_date or nowdate()
	sr.posting_time = nowtime()
	if doc.set_warehouse:
		sr.set_warehouse = doc.set_warehouse
	sr.cost_center = doc.cost_center or None
	if frappe.db.has_column("Stock Reconciliation", "custom_notes"):
		sr.custom_notes = f"{RESTORE_SCANNER_NOTE_PREFIX}{doc.name}"

	_apply_stock_reconciliation_defaults(sr, base_scanner=doc)

	if is_perpetual_inventory_enabled(sr.company) and not sr.expense_account:
		frappe.throw(
			_(
				"Could not resolve a Difference Account for {0}. Set a Stock Adjustment Account on the Company first."
			).format(sr.company)
		)

	for line in missed:
		sr.append("items", _build_restore_item_row(line))

	sr.insert()
	# The desk opens this draft immediately after the call returns.
	frappe.db.commit()  # nosemgrep
	return sr.name
