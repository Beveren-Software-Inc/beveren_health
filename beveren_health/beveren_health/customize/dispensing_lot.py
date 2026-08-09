# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import math

import frappe
from frappe import _
from frappe.utils import cint, flt

DISPENSING_LOT_FIELD = "custom_dispensing_lot"
DISPENSING_UOM = "UNIT"

STOCK_DOC_CONFIG = {
	"Purchase Receipt": {
		"items_field": "items",
		"warehouse_field": "warehouse",
		"use_parent_warehouse": True,
	},
	"Stock Reconciliation": {
		"items_field": "items",
		"warehouse_field": "warehouse",
		"use_parent_warehouse": True,
		"parent_warehouse_field": "set_warehouse",
	},
	"Stock Entry": {
		"items_field": "items",
		"warehouse_field": None,
		"use_stock_entry_warehouse": True,
	},
}


DISPENSING_LOT_VALIDATION_SETTING = {
	"Stock Entry": "validate_dispensing_lot_on_stock_entry",
	"Sales Invoice": "validate_dispensing_lot_on_sales_invoice",
	"Delivery Note": "validate_dispensing_lot_on_delivery_note",
	"Stock Reconciliation": "validate_dispensing_lot_on_stock_reconciliation",
	"Purchase Receipt": "validate_dispensing_lot_on_purchase_receipt",
	"Stock Scanner": "validate_dispensing_lot_on_stock_scanner",
}

# Documents that consume / restore dispensing lots on submit / cancel
DISPENSING_LOT_SALE_DOCTYPES = frozenset({"Sales Invoice", "Delivery Note"})


def is_dispensing_lot_validation_enabled(doctype):
	"""Whether Dispensing Setting requires lots on this doctype."""
	fieldname = DISPENSING_LOT_VALIDATION_SETTING.get(doctype)
	if not fieldname:
		return False
	return bool(cint(frappe.db.get_single_value("Dispensing Setting", fieldname) or 0))


def item_requires_dispensing_lot(item_code):
	"""Item flagged on master — dispensing lot mandatory (like serial no)."""
	if not item_code:
		return False
	return bool(cint(frappe.db.get_value("Item", item_code, "custom_has_dispense_lot") or 0))


def validate_row_has_dispensing_lot(row, row_label=None, lot_field=None):
	"""Raise if item requires a dispensing lot but the stock/sales line has none."""
	if not item_requires_dispensing_lot(row.get("item_code")):
		return

	if lot_field:
		serials = split_dispensing_lots(row.get(lot_field) or "")
	else:
		serials = _serials_from_stock_row(row)

	if serials:
		return

	label = row_label or _("row {0}").format(row.get("idx") or "")
	frappe.throw(
		_("Dispensing Lot is required for Item {0} ({1}). Scan or select a lot on the line.").format(
			row.item_code, label
		)
	)


def split_dispensing_lots(value):
	if not value:
		return []

	if "\n" in value:
		return [s.strip() for s in value.split("\n") if s.strip()]
	if "," in value:
		return [s.strip() for s in value.split(",") if s.strip()]

	return [value.strip()] if value.strip() else []


def _item_has_unit_uom(item):
	for row in item.get("uoms") or []:
		if row.uom == DISPENSING_UOM:
			return True
	return False


def _get_unit_conversion_factor(item):
	"""UNIT → stock-UOM factor; 1 when the item has no UNIT row."""
	for row in item.get("uoms") or []:
		if row.uom == DISPENSING_UOM:
			return flt(row.conversion_factor) or 1.0
	return 1.0


def get_pack_size_and_uom(item_code):
	"""Return (pack_size in dispensing UOM, dispensing_uom) for one physical pack."""
	item = frappe.get_cached_doc("Item", item_code)
	stock_uom = item.stock_uom

	if _item_has_unit_uom(item):
		cf = _get_unit_conversion_factor(item)
		if cf >= 1:
			return cf, DISPENSING_UOM
		return flt(1 / cf, 6), DISPENSING_UOM

	# No UNIT: dispensing qty is the stock qty itself (no conversion / no pack-size default).
	return 1, stock_uom


def stock_qty_to_dispensing_qty(stock_qty, item_code):
	"""Convert stock-UOM qty to dispensing-UOM qty."""
	item = frappe.get_cached_doc("Item", item_code)

	if not _item_has_unit_uom(item):
		return flt(stock_qty, 6)

	cf = _get_unit_conversion_factor(item)
	if cf == 1:
		return flt(stock_qty, 6)
	return flt(flt(stock_qty) / cf, 6)


def round_dispensing_qty(qty):
	"""
	Round a UNIT quantity for dispensing lots.

	Fractional part >= 0.80 rounds up (e.g. 9.99 → 10); below 0.80 rounds down.
	Only used when the item has a UNIT UOM row.
	"""
	qty = flt(qty, 6)
	if qty <= 0:
		return 0

	whole = math.floor(qty + 1e-9)
	frac = round(qty - whole, 2)
	if frac >= 0.80:
		return whole + 1
	return whole


def finalize_dispensing_lot_qty(qty, item_code):
	"""Apply UNIT rounding rules, or keep stock qty as-is when the item has no UNIT."""
	qty = flt(qty, 6)
	if qty <= 0:
		return 0

	item = frappe.get_cached_doc("Item", item_code)
	if _item_has_unit_uom(item):
		return round_dispensing_qty(qty)
	return qty


def compute_dispensing_qty_per_serial(row_stock_qty, serials, pack_size=None, item_code=None):
	"""
	Distribute a stock-UOM line qty across dispensing lots.

	Each serial before the last represents one full pack; the last serial
	gets any fractional remainder (e.g. 1.86 PACK with 2 lots → 1 + 0.86).
	Quantities are returned in dispensing UOM (e.g. UNIT).
	"""
	n = len(serials or [])
	if not n:
		return []

	total = flt(row_stock_qty)

	def to_dispensing_qty(pack_qty):
		if item_code:
			return stock_qty_to_dispensing_qty(pack_qty, item_code)
		pack_size_val = flt(pack_size) or 1
		return flt(pack_qty) * pack_size_val

	def finalize(pack_qty):
		raw = to_dispensing_qty(pack_qty)
		if item_code:
			return finalize_dispensing_lot_qty(raw, item_code)
		return round_dispensing_qty(raw)

	if n == 1:
		return [finalize(total)]

	quantities = []
	remaining = total

	for i in range(n):
		if i == n - 1:
			lot_stock_qty = remaining
		elif remaining >= 1:
			lot_stock_qty = 1
		else:
			lot_stock_qty = remaining

		quantities.append(finalize(lot_stock_qty))
		remaining = flt(remaining - lot_stock_qty, 6)

	return quantities


def compute_dispensing_qty_per_serial_for_item(row_stock_qty, serials, item_code):
	return compute_dispensing_qty_per_serial(row_stock_qty, serials, item_code=item_code)


def _get_dispensing_uom_from_item(item):
	if _item_has_unit_uom(item):
		return DISPENSING_UOM
	return item.stock_uom


def _is_material_transfer_stock_entry(doc):
	return doc.doctype == "Stock Entry" and doc.get("purpose") == "Material Transfer"


def get_warehouse_for_row(doc, row, config):
	if config.get("use_stock_entry_warehouse"):
		purpose = doc.get("purpose")
		if purpose == "Material Transfer":
			return row.get("t_warehouse")
		if purpose in ("Material Receipt", "Manufacture", "Repack"):
			return row.get("t_warehouse")
		if purpose in ("Material Issue", "Material Transfer for Manufacture"):
			return row.get("s_warehouse")
		return row.get("t_warehouse") or row.get("s_warehouse")

	if config.get("use_parent_warehouse"):
		parent_wh = doc.get(config.get("parent_warehouse_field") or "set_warehouse")
		return row.get(config.get("warehouse_field")) or parent_wh

	return row.get(config.get("warehouse_field"))


def _serials_from_stock_row(row):
	"""Resolve manufacturer serial(s) from custom_dispensing_lot (text or Dispensing Lot link)."""
	raw = row.get(DISPENSING_LOT_FIELD) or ""
	serials = []
	for token in split_dispensing_lots(raw):
		if frappe.db.exists("Dispensing Lot", token):
			serial_no = frappe.db.get_value("Dispensing Lot", token, "serial_no")
			serials.append(serial_no or token)
		else:
			serials.append(token)
	return serials


def _lot_is_partially_consumed(lot):
	"""True if any units were sold/consumed — full pack only may be transferred."""
	if lot.status == "Partially Sold":
		return True

	initial = flt(lot.initial_qty)
	remaining = flt(lot.remaining_qty)
	if initial > 0 and remaining < initial:
		return True

	issued = 0
	returned = 0
	for row in lot.transactions:
		if row.transaction_type == "Transfer":
			continue
		qty = flt(row.qty)
		if row.transaction_type == "In":
			returned += qty
		elif row.transaction_type == "Out":
			issued += qty

	return issued > returned


def _validate_lot_eligible_for_transfer(lot, serial_no):
	"""Only full, unconsumed packs (Active, full remaining qty) may be transferred."""
	if lot.status in ("Inactive", "Delivered"):
		frappe.throw(
			_("Dispensing Lot {0} ({1}) cannot be transferred (status: {2}).").format(
				lot.name, serial_no, lot.status
			)
		)

	if _lot_is_partially_consumed(lot):
		frappe.throw(
			_(
				"Dispensing Lot {0} ({1}) has been partially consumed and cannot be transferred. "
				"Remaining {2} {3} of {4} {3}. Only a full pack with no sales may be moved."
			).format(
				lot.name,
				serial_no,
				lot.remaining_qty,
				lot.uom,
				lot.initial_qty,
			)
		)


def _transfer_dispensing_lot_on_material_transfer(doc, row, serial_no):
	"""Move an existing pack to the target warehouse, or create it there if missing."""
	dest_wh = row.get("t_warehouse")
	source_wh = row.get("s_warehouse")

	if not dest_wh:
		frappe.throw(
			_("Target Warehouse is required on the row to transfer Dispensing Lot {0}").format(
				serial_no
			)
		)

	lot_name = _get_lot_name_by_serial(serial_no)
	if not lot_name:
		# First time seeing this serial on transfer — create the lot at destination
		return _create_missing_lot_on_material_transfer(doc, row, serial_no, dest_wh, source_wh)

	lot = frappe.get_doc("Dispensing Lot", lot_name)
	_validate_lot_eligible_for_transfer(lot, serial_no)

	if source_wh and lot.warehouse and lot.warehouse != source_wh:
		frappe.throw(
			_("Dispensing Lot {0} is in warehouse {1}, not source warehouse {2}.").format(
				lot.name, lot.warehouse, source_wh
			)
		)

	if _lot_has_reference_transaction(lot, doc.doctype, doc.name, "Transfer"):
		return lot.name

	lot.warehouse = dest_wh
	if row.batch_no:
		lot.batch_no = row.batch_no

	posting_date = doc.get("posting_date") or frappe.utils.today()
	_append_lot_transaction(
		lot,
		transaction_type="Transfer",
		qty=0,
		uom=lot.uom,
		reference_doctype=doc.doctype,
		reference_name=doc.name,
		posting_date=posting_date,
		remarks=_("Transferred from {0} to {1}").format(source_wh or "—", dest_wh),
	)
	return lot.name


def _create_missing_lot_on_material_transfer(doc, row, serial_no, dest_wh, source_wh):
	"""Create a Dispensing Lot at the transfer destination when the serial is new."""
	if not row.item_code or not row.batch_no:
		frappe.throw(
			_(
				"Item and Batch are required to create Dispensing Lot for serial {0} on transfer."
			).format(serial_no)
		)

	_validate_stock_row_batch_item(row)

	serials = _serials_from_stock_row(row)
	row_stock_qty = flt(row.get("qty")) or len(serials) or 1
	lot_quantities = compute_dispensing_qty_per_serial(
		row_stock_qty, serials, item_code=row.item_code
	)

	try:
		lot_qty = lot_quantities[serials.index(serial_no)]
	except (ValueError, IndexError):
		lot_qty = lot_quantities[0] if lot_quantities else 1

	_pack_size, dispensing_uom = get_pack_size_and_uom(row.item_code)
	gtin = row.get("custom_gstin") or frappe.db.get_value(
		"Item", row.item_code, "custom_gtin_number"
	)
	posting_date = doc.get("posting_date") or frappe.utils.today()

	lot_name = _create_dispensing_lot_if_missing(
		item=row.item_code,
		batch_no=row.batch_no,
		serial_no=serial_no,
		warehouse=dest_wh,
		lot_qty=lot_qty,
		dispensing_uom=dispensing_uom,
		gtin=gtin,
		reference_doctype=doc.doctype,
		reference_name=doc.name,
		posting_date=posting_date,
		row_idx=row.idx,
	)

	lot = frappe.get_doc("Dispensing Lot", lot_name)
	if _lot_has_reference_transaction(lot, doc.doctype, doc.name, "Transfer"):
		return lot.name

	_append_lot_transaction(
		lot,
		transaction_type="Transfer",
		qty=0,
		uom=lot.uom,
		reference_doctype=doc.doctype,
		reference_name=doc.name,
		posting_date=posting_date,
		remarks=_("Created on transfer from {0} to {1}").format(source_wh or "—", dest_wh),
	)
	return lot.name


def _reverse_material_transfer_dispensing_lots(doc):
	"""On cancel of Material Transfer, move lots back to source warehouse (no Out/In)."""
	for row in doc.get("items") or []:
		serials = _serials_from_stock_row(row)
		source_wh = row.get("s_warehouse")
		dest_wh = row.get("t_warehouse")

		if not serials or not source_wh:
			continue

		for serial in serials:
			lot_name = _get_lot_name_by_serial(serial)
			if not lot_name:
				continue

			lot = frappe.get_doc("Dispensing Lot", lot_name)
			if not dest_wh or lot.warehouse != dest_wh:
				continue

			cancel_remark = _("Cancelled transfer {0} — returned to {1}").format(
				doc.name, source_wh
			)
			if any(
				row.transaction_type == "Transfer"
				and row.reference_name == doc.name
				and cancel_remark in (row.remarks or "")
				for row in lot.transactions
			):
				continue

			lot.warehouse = source_wh
			posting_date = doc.get("posting_date") or frappe.utils.today()
			_append_lot_transaction(
				lot,
				transaction_type="Transfer",
				qty=0,
				uom=lot.uom,
				reference_doctype=doc.doctype,
				reference_name=doc.name,
				posting_date=posting_date,
				remarks=cancel_remark,
			)


def validate_stock_document_dispensing_lots(doc, method=None):
	"""Require dispensing lot on lines when Item.custom_has_dispense_lot is set."""
	if not is_dispensing_lot_validation_enabled(doc.doctype):
		return

	config = STOCK_DOC_CONFIG.get(doc.doctype)
	if not config:
		return

	for row in doc.get(config["items_field"]) or []:
		if not row.item_code:
			continue
		validate_row_has_dispensing_lot(row, row_label=_("row {0}").format(row.idx))


def validate_stock_scanner_dispensing_lots(doc, method=None):
	"""Require dispensing lot (serial_no) on Stock Scanner lines when setting is on."""
	if not is_dispensing_lot_validation_enabled("Stock Scanner"):
		return

	for row in doc.get("items") or []:
		if not row.item_code:
			continue
		validate_row_has_dispensing_lot(
			row,
			row_label=_("row {0}").format(row.idx),
			lot_field="serial_no",
		)


def _stock_entry_line_needs_dispensing_lot(doc, row):
	if not item_requires_dispensing_lot(row.item_code):
		return False
	purpose = doc.get("purpose")
	if purpose == "Material Transfer":
		return True
	if purpose in ("Material Receipt", "Manufacture", "Repack"):
		return True
	return False


def validate_stock_entry_dispensing_lots(doc, method=None):
	"""Require lots on flagged items; block partial pack transfer when lot already exists."""
	if is_dispensing_lot_validation_enabled("Stock Entry"):
		for row in doc.get("items") or []:
			if not row.item_code:
				continue
			if _stock_entry_line_needs_dispensing_lot(doc, row):
				validate_row_has_dispensing_lot(row, row_label=_("row {0}").format(row.idx))

	if not _is_material_transfer_stock_entry(doc):
		return

	for row in doc.get("items") or []:
		if not item_requires_dispensing_lot(row.item_code):
			continue

		for serial in _serials_from_stock_row(row):
			lot_name = _get_lot_name_by_serial(serial)
			if not lot_name:
				# Missing lot will be created on submit at the target warehouse
				continue
			lot = frappe.get_doc("Dispensing Lot", lot_name)
			_validate_lot_eligible_for_transfer(lot, serial)


def create_dispensing_lots_on_submit(doc, method=None):
	"""Create Dispensing Lot records from scanned serials on stock document submit."""
	config = STOCK_DOC_CONFIG.get(doc.doctype)
	if not config:
		return

	for row in doc.get(config["items_field"]) or []:
		serials = _serials_from_stock_row(row)
		if not serials or not row.item_code or not row.batch_no:
			continue

		_validate_stock_row_batch_item(row)

		if _is_material_transfer_stock_entry(doc):
			for serial in serials:
				_transfer_dispensing_lot_on_material_transfer(doc, row, serial)
			continue

		_pack_size, dispensing_uom = get_pack_size_and_uom(row.item_code)
		warehouse = get_warehouse_for_row(doc, row, config)

		gtin = row.get("custom_gstin") or frappe.db.get_value(
			"Item", row.item_code, "custom_gtin_number"
		)

		posting_date = doc.get("posting_date") or frappe.utils.today()
		row_stock_qty = flt(row.get("qty")) or len(serials)
		lot_quantities = compute_dispensing_qty_per_serial(
			row_stock_qty, serials, item_code=row.item_code
		)

		for serial, lot_qty in zip(serials, lot_quantities):
			_create_dispensing_lot_if_missing(
				item=row.item_code,
				batch_no=row.batch_no,
				serial_no=serial,
				warehouse=warehouse,
				lot_qty=lot_qty,
				dispensing_uom=dispensing_uom,
				gtin=gtin,
				reference_doctype=doc.doctype,
				reference_name=doc.name,
				posting_date=posting_date,
				row_idx=row.idx,
			)


def _validate_stock_row_batch_item(row):
	"""Batch master must match the item on the stock document line."""
	batch_item = frappe.db.get_value("Batch", row.batch_no, "item")
	if batch_item and batch_item != row.item_code:
		frappe.throw(
			_("Row {0}: Batch {1} belongs to item {2}, not {3}.").format(
				row.idx, row.batch_no, batch_item, row.item_code
			)
		)


def _ensure_lot_item_matches_stock_row(lot, item, serial_no, row_idx=None):
	"""Reject or correct when an existing lot serial is tied to a different item."""
	if not lot.item or lot.item == item:
		return

	row_ref = _("row {0}").format(row_idx) if row_idx else _("this document line")

	if _lot_is_partially_consumed(lot) or _lot_has_sales_invoice_out(lot):
		frappe.throw(
			_(
				"{0}: Dispensing Lot serial {1} is already registered for item {2}, "
				"not {3}. This conflicts with existing lot {4}. "
				"Remove the serial from the line or correct the Dispensing Lot first."
			).format(row_ref, serial_no, lot.item, item, lot.name)
		)

	lot.item = item


def _get_lot_name_by_serial(serial_no):
	"""Find Dispensing Lot by manufacturer serial (field or document name)."""
	if not serial_no:
		return None

	name = frappe.db.get_value("Dispensing Lot", {"serial_no": serial_no}, "name")
	if name:
		return name

	if frappe.db.exists("Dispensing Lot", serial_no):
		return serial_no

	return None


def _lot_has_cancel_out(lot):
	for row in lot.transactions:
		if row.transaction_type == "Out" and "Cancelled" in (row.remarks or ""):
			return True
	return False


def _lot_needs_stock_reactivation(lot):
	"""True when lot was zeroed by cancelling a stock document and can be received again."""
	if lot.status == "Inactive":
		return True
	if flt(lot.remaining_qty) > 0 and lot.status == "Active":
		return False
	if flt(lot.remaining_qty) <= 0 and _lot_has_cancel_out(lot):
		return True
	return False


def _restore_dispensing_lot_from_stock_doc(
	lot,
	serial_no,
	item,
	batch_no,
	warehouse,
	lot_qty,
	dispensing_uom,
	gtin,
	reference_doctype,
	reference_name,
	posting_date,
):
	"""Re-activate an existing lot when the same serial is received on a new stock document."""
	if _lot_has_sales_invoice_out(lot) and lot.status == "Delivered":
		frappe.throw(
			_("Dispensing Lot for serial {0} was sold and cannot be received again.").format(
				lot.serial_no or serial_no
			)
		)

	lot_qty = flt(lot_qty) or flt(lot.initial_qty) or 1

	lot.item = item
	lot.batch_no = batch_no
	if warehouse:
		lot.warehouse = warehouse
	lot.uom = dispensing_uom or lot.uom
	lot.initial_qty = lot_qty
	if gtin:
		lot.gtin = gtin
	if serial_no and not lot.serial_no:
		lot.serial_no = serial_no

	lot.source_doctype = reference_doctype
	lot.source_document = reference_name

	in_qty = lot_qty - flt(lot.remaining_qty)

	if in_qty > 0 and not _lot_has_reference_transaction(
		lot, reference_doctype, reference_name, "In"
	):
		_append_lot_transaction(
			lot,
			transaction_type="In",
			qty=in_qty,
			uom=lot.uom,
			reference_doctype=reference_doctype,
			reference_name=reference_name,
			posting_date=posting_date,
			remarks=_("Received from {0} {1}").format(reference_doctype, reference_name),
		)
	else:
		lot.save(ignore_permissions=True)

	return lot.name


def _create_dispensing_lot_if_missing(
	item,
	batch_no,
	serial_no,
	warehouse,
	lot_qty,
	dispensing_uom,
	gtin=None,
	reference_doctype=None,
	reference_name=None,
	posting_date=None,
	row_idx=None,
):
	posting_date = posting_date or frappe.utils.today()
	lot_qty = flt(lot_qty) or 1
	lot_name = _get_lot_name_by_serial(serial_no)

	if lot_name:
		lot = frappe.get_doc("Dispensing Lot", lot_name)
		if gtin and not lot.gtin:
			lot.gtin = gtin

		if _lot_needs_stock_reactivation(lot):
			return _restore_dispensing_lot_from_stock_doc(
				lot,
				serial_no,
				item,
				batch_no,
				warehouse,
				lot_qty,
				dispensing_uom,
				gtin,
				reference_doctype,
				reference_name,
				posting_date,
			)

		# Already active — refresh source link to this document
		_ensure_lot_item_matches_stock_row(lot, item, serial_no, row_idx=row_idx)
		lot.source_doctype = reference_doctype
		lot.source_document = reference_name
		if warehouse:
			lot.warehouse = warehouse
		lot.batch_no = batch_no
		if dispensing_uom:
			lot.uom = dispensing_uom
		lot.save(ignore_permissions=True)
		return lot.name

	lot = frappe.get_doc(
		{
			"doctype": "Dispensing Lot",
			"naming_series": "DL-.YYYY.-",
			"item": item,
			"batch_no": batch_no,
			"warehouse": warehouse,
			"serial_no": serial_no,
			"gtin": gtin,
			"uom": dispensing_uom,
			"initial_qty": lot_qty,
			"remaining_qty": lot_qty,
			"status": "Active",
			"source_doctype": reference_doctype,
			"source_document": reference_name,
		}
	)
	lot.insert(ignore_permissions=True)
	return lot.name


@frappe.whitelist()
def get_dispensing_lots_for_stock_document(source_doctype, source_document):
	"""Return dispensing lots created from a stock document (for review / amendment)."""
	if not source_doctype or not source_document:
		return []

	return frappe.get_all(
		"Dispensing Lot",
		filters={
			"source_doctype": source_doctype,
			"source_document": source_document,
		},
		fields=[
			"name",
			"item",
			"item_name",
			"serial_no",
			"batch_no",
			"initial_qty",
			"remaining_qty",
			"uom",
			"status",
		],
		order_by="item asc, serial_no asc",
	)


def build_expected_lot_quantities_for_stock_document(doc):
	"""Build expected dispensing qty maps from stock document lines."""
	config = STOCK_DOC_CONFIG.get(doc.doctype)
	if not config:
		return {"by_lot": {}, "by_serial": {}}

	by_lot = {}
	by_serial = {}

	for row in doc.get(config["items_field"]) or []:
		serials = _serials_from_stock_row(row)
		if not serials or not row.item_code:
			continue

		row_stock_qty = flt(row.get("qty")) or len(serials)
		lot_quantities = compute_dispensing_qty_per_serial(
			row_stock_qty, serials, item_code=row.item_code
		)

		for serial, lot_qty in zip(serials, lot_quantities):
			by_serial[serial] = lot_qty
			lot_name = _get_lot_name_by_serial(serial)
			if lot_name:
				by_lot[lot_name] = lot_qty

	return {"by_lot": by_lot, "by_serial": by_serial}


def _expected_qty_for_lot(lot, expected_maps, doc):
	by_lot = expected_maps.get("by_lot") or {}
	by_serial = expected_maps.get("by_serial") or {}

	if lot.name in by_lot:
		return by_lot[lot.name]

	for token in (lot.serial_no, lot.name):
		if token and token in by_serial:
			return by_serial[token]

	config = STOCK_DOC_CONFIG.get(doc.doctype)
	if not config:
		return None

	lot_tokens = {t for t in (lot.serial_no, lot.name) if t}

	for row in doc.get(config["items_field"]) or []:
		serials = _serials_from_stock_row(row)
		if not serials:
			continue

		matched = False
		for serial in serials:
			if serial in lot_tokens or _get_lot_name_by_serial(serial) == lot.name:
				matched = True
				break

		if not matched:
			continue

		row_stock_qty = flt(row.get("qty")) or len(serials)
		lot_quantities = compute_dispensing_qty_per_serial(
			row_stock_qty, serials, item_code=row.item_code
		)
		for serial, lot_qty in zip(serials, lot_quantities):
			if serial in lot_tokens or _get_lot_name_by_serial(serial) == lot.name:
				return lot_qty

	return None


def _qty_matches_expected(current_qty, expected_qty, item_code):
	item = frappe.get_cached_doc("Item", item_code)
	precision = 3 if _item_has_unit_uom(item) else 6
	return flt(expected_qty, precision) == flt(current_qty, precision)


def _lot_safe_for_qty_correction(lot):
	"""Only correct lots that were never consumed (wrong qty from legacy submit logic)."""
	if lot.status != "Active":
		return False

	if flt(lot.remaining_qty) != flt(lot.initial_qty):
		return False

	for row in lot.transactions:
		if row.transaction_type == "Out":
			return False

	return True


def _collect_lot_names_for_stock_correction(doc):
	"""All dispensing lots tied to this document by source link or row serial."""
	names = set()

	for ref in frappe.get_all(
		"Dispensing Lot",
		filters={"source_doctype": doc.doctype, "source_document": doc.name},
		fields=["name"],
	):
		names.add(ref.name)

	config = STOCK_DOC_CONFIG.get(doc.doctype)
	if not config:
		return sorted(names)

	for row in doc.get(config["items_field"]) or []:
		if not row.item_code:
			continue
		for serial in _serials_from_stock_row(row):
			lot_name = _get_lot_name_by_serial(serial)
			if lot_name:
				names.add(lot_name)
			elif frappe.db.exists("Dispensing Lot", serial):
				names.add(serial)

	return sorted(names)


def _preview_dispensing_lot_qty_corrections(doc):
	expected_maps = build_expected_lot_quantities_for_stock_document(doc)
	fixable = []
	skipped = []
	unchanged = []

	for lot_name in _collect_lot_names_for_stock_correction(doc):
		if not frappe.db.exists("Dispensing Lot", lot_name):
			continue

		lot = frappe.get_doc("Dispensing Lot", lot_name)
		expected_qty = _expected_qty_for_lot(lot, expected_maps, doc)

		if expected_qty is None:
			skipped.append(
				{
					"name": lot.name,
					"serial_no": lot.serial_no,
					"item": lot.item,
					"reason": _("No matching line on this document"),
				}
			)
			continue

		current_qty = flt(lot.initial_qty)
		item = frappe.get_cached_doc("Item", lot.item)
		precision = 3 if _item_has_unit_uom(item) else 6

		if _qty_matches_expected(current_qty, expected_qty, lot.item):
			unchanged.append(
				{
					"name": lot.name,
					"serial_no": lot.serial_no,
					"item": lot.item,
					"current_qty": flt(current_qty, precision),
					"expected_qty": flt(expected_qty, precision),
					"uom": lot.uom,
				}
			)
			continue

		if not _lot_safe_for_qty_correction(lot):
			skipped.append(
				{
					"name": lot.name,
					"serial_no": lot.serial_no,
					"item": lot.item,
					"current_qty": flt(current_qty, precision),
					"expected_qty": flt(expected_qty, precision),
					"uom": lot.uom,
					"reason": _("Already used or not Active"),
				}
			)
			continue

		fixable.append(
			{
				"name": lot.name,
				"item": lot.item,
				"serial_no": lot.serial_no,
				"current_qty": flt(current_qty, precision),
				"expected_qty": flt(expected_qty, precision),
				"uom": lot.uom,
			}
		)

	return {"fixable": fixable, "skipped": skipped, "unchanged": unchanged}


@frappe.whitelist()
def preview_dispensing_lot_qty_corrections(source_doctype, source_document):
	"""List dispensing lots whose quantities can be auto-corrected from the stock document."""
	if source_doctype != "Stock Reconciliation":
		frappe.throw(_("Quantity correction is only supported for Stock Reconciliation."))

	doc = frappe.get_doc(source_doctype, source_document)
	if doc.docstatus != 1:
		frappe.throw(_("Submit the document before correcting dispensing lot quantities."))

	return _preview_dispensing_lot_qty_corrections(doc)


@frappe.whitelist()
def correct_dispensing_lot_quantities(source_doctype, source_document):
	"""One-time fix: set initial/remaining qty from stock document line totals."""
	if source_doctype != "Stock Reconciliation":
		frappe.throw(_("Quantity correction is only supported for Stock Reconciliation."))

	doc = frappe.get_doc(source_doctype, source_document)
	if doc.docstatus != 1:
		frappe.throw(_("Submit the document before correcting dispensing lot quantities."))

	preview = _preview_dispensing_lot_qty_corrections(doc)
	corrected = []

	for entry in preview["fixable"]:
		lot = frappe.get_doc("Dispensing Lot", entry["name"])
		old_qty = flt(lot.initial_qty)
		item = frappe.get_cached_doc("Item", lot.item)
		precision = 3 if _item_has_unit_uom(item) else 6
		new_qty = flt(entry["expected_qty"], precision)

		lot.initial_qty = new_qty
		lot.remaining_qty = new_qty
		lot.source_doctype = source_doctype
		lot.source_document = source_document
		lot.save(ignore_permissions=True)

		corrected.append(
			{
				"name": lot.name,
				"serial_no": lot.serial_no,
				"old_qty": old_qty,
				"new_qty": new_qty,
				"uom": lot.uom,
			}
		)

	return {
		"corrected": corrected,
		"skipped": preview["skipped"],
		"unchanged": preview.get("unchanged", []),
	}


def _lot_has_dispensing_uom_unit_sales(lot):
	"""True if this pack was already sold in dispensing UOM (tabs/units), not as a full pack."""
	stock_uom = lot.stock_uom
	dispensing_uom = lot.uom
	if not stock_uom or not dispensing_uom or stock_uom == dispensing_uom:
		return False

	for row in lot.transactions:
		if row.transaction_type != "Out" or row.reference_doctype not in DISPENSING_LOT_SALE_DOCTYPES:
			continue
		if row.uom == dispensing_uom and flt(row.qty) > 0:
			return True
	return False


def _validate_pack_sale_on_lot(lot, item_code, issue_uom, issue_qty):
	"""
	Block selling in stock UOM (full pack) when the physical pack is no longer intact
	(e.g. 30 of 50 tabs sold — only unit sales allowed for the remaining 20).
	"""
	stock_uom = lot.stock_uom or frappe.db.get_value("Item", item_code, "stock_uom")
	if issue_uom != stock_uom or flt(issue_qty) < 1:
		return

	if flt(lot.remaining_qty) < flt(lot.initial_qty):
		frappe.throw(
			_(
				"Cannot sell in {0} for Dispensing Lot {1}. "
				"This pack was partially sold in {2} (remaining {3} {2} of {4}). "
				"Sell the balance in {2} only, not as a full {0}."
			).format(
				stock_uom,
				lot.name,
				lot.uom,
				lot.remaining_qty,
				lot.initial_qty,
			)
		)

	if _lot_has_dispensing_uom_unit_sales(lot):
		frappe.throw(
			_(
				"Cannot sell in {0} for Dispensing Lot {1}. "
				"Units were already sold from this pack in {2}. "
				"Sell only the remaining {3} {2}."
			).format(stock_uom, lot.name, lot.uom, lot.remaining_qty)
		)

	if flt(issue_qty) > 1:
		frappe.throw(
			_(
				"Only one {0} can be sold per Dispensing Lot. "
				"This line issues {1} {0} against one lot — select one serial/lot per pack "
				"(comma-separated on POS) or use separate invoice lines."
			).format(stock_uom, issue_qty)
		)


def validate_dispensing_lot_for_sale(item_row, lot):
	"""Shared validation for desk Sales Invoice and POS."""
	issue_uom, issue_qty = compute_issue_from_sales_item(item_row, lot)
	if not issue_qty:
		return

	stock_uom = lot.stock_uom or frappe.db.get_value("Item", item_row.item_code, "stock_uom")

	if issue_uom == stock_uom and flt(issue_qty) >= 1:
		_validate_pack_sale_on_lot(lot, item_row.item_code, issue_uom, issue_qty)
		if lot.status == "Delivered":
			frappe.throw(_("Dispensing Lot {0} is already delivered").format(lot.name))
		return

	if lot.status == "Delivered":
		frappe.throw(_("Dispensing Lot {0} is already delivered").format(lot.name))

	if flt(lot.remaining_qty) < flt(issue_qty):
		frappe.throw(
			_("Insufficient quantity on Dispensing Lot {0}. Remaining {1} {2}, selling {3}.").format(
				lot.name, lot.remaining_qty, lot.uom, issue_qty
			)
		)


def compute_issue_from_sales_item(item_row, lot):
	"""Return (uom, qty) for a dispensing lot transaction from a Sales Invoice Item row."""
	stock_uom = lot.stock_uom or frappe.db.get_value("Item", item_row.item_code, "stock_uom")
	dispensing_uom = lot.uom
	invoice_uom = item_row.uom
	invoice_qty = abs(flt(item_row.qty))

	if not invoice_qty:
		return None, 0

	if invoice_uom == stock_uom:
		return stock_uom, invoice_qty

	if invoice_uom == dispensing_uom:
		return dispensing_uom, invoice_qty

	stock_qty = abs(flt(item_row.stock_qty))
	pack_size = flt(lot.initial_qty) or 1

	if stock_uom == dispensing_uom:
		return dispensing_uom, stock_qty

	return dispensing_uom, stock_qty * pack_size


def _lot_has_reference_transaction(lot, reference_doctype, reference_name, transaction_type):
	for row in lot.transactions:
		if (
			row.reference_doctype == reference_doctype
			and row.reference_name == reference_name
			and row.transaction_type == transaction_type
		):
			return True
	return False


def _lot_has_cancel_reversal(lot, reference_doctype, reference_name):
	for row in lot.transactions:
		if (
			row.reference_doctype == reference_doctype
			and row.reference_name == reference_name
			and row.transaction_type == "Out"
			and "Cancelled" in (row.remarks or "")
		):
			return True
	return False


def _lot_has_sales_invoice_out(lot):
	for row in lot.transactions:
		if row.transaction_type == "Out" and row.reference_doctype in DISPENSING_LOT_SALE_DOCTYPES:
			return True
	return False


def _lot_eligible_for_stock_doc_cancel(lot, doc):
	"""Only reverse lots that this stock document originally introduced."""
	source_doctype = lot.get("source_doctype")
	source_document = lot.get("source_document")

	if source_doctype and source_document:
		return source_doctype == doc.doctype and source_document == doc.name

	# Legacy lots (no source): reverse only if never sold and still at full pack qty
	if _lot_has_sales_invoice_out(lot):
		return False
	return flt(lot.remaining_qty) == flt(lot.initial_qty) and flt(lot.initial_qty) > 0


def _append_lot_transaction(
	lot,
	transaction_type,
	qty,
	uom,
	reference_doctype,
	reference_name,
	posting_date,
	remarks,
):
	if not flt(qty) and transaction_type != "Transfer":
		return

	lot.append(
		"transactions",
		{
			"posting_date": posting_date,
			"transaction_type": transaction_type,
			"qty": flt(qty),
			"uom": uom,
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"remarks": remarks,
		},
	)
	lot.save(ignore_permissions=True)


def reverse_stock_document_dispensing_lots(doc, method=None):
	"""
	On cancel of Purchase Receipt / Stock Entry / Stock Reconciliation,
	post Out for remaining qty so the lot goes to zero and status Inactive.

	Material Transfer cancel only moves warehouse back to the source (no Out/In).
	"""
	if _is_material_transfer_stock_entry(doc):
		_reverse_material_transfer_dispensing_lots(doc)
		return

	config = STOCK_DOC_CONFIG.get(doc.doctype)
	if not config:
		return

	posting_date = doc.get("posting_date") or frappe.utils.today()

	for row in doc.get(config["items_field"]) or []:
		serials = _serials_from_stock_row(row)
		if not serials:
			continue

		for serial in serials:
			lot_name = _get_lot_name_by_serial(serial)
			if not lot_name:
				continue

			lot = frappe.get_doc("Dispensing Lot", lot_name)
			if not _lot_eligible_for_stock_doc_cancel(lot, doc):
				continue

			if _lot_has_cancel_reversal(lot, doc.doctype, doc.name):
				continue

			out_qty = flt(lot.remaining_qty)
			if out_qty <= 0:
				continue

			_append_lot_transaction(
				lot,
				transaction_type="Out",
				qty=out_qty,
				uom=lot.uom,
				reference_doctype=doc.doctype,
				reference_name=doc.name,
				posting_date=posting_date,
				remarks=_("Cancelled {0}").format(doc.name),
			)


def resolve_dispensing_lot_names_from_field(raw_value):
	"""
	Parse Sales Invoice Item.custom_dispensing_lot (Long Text): comma/newline-separated
	Dispensing Lot docnames (or manufacturer serial tokens resolved to a lot).
	"""
	seen = set()
	names = []

	for token in split_dispensing_lots(raw_value or ""):
		if frappe.db.exists("Dispensing Lot", token):
			if token not in seen:
				names.append(token)
				seen.add(token)
			continue

		resolved = _get_lot_name_by_serial(token)
		if resolved and resolved not in seen:
			names.append(resolved)
			seen.add(resolved)

	return names


def format_dispensing_lot_names_for_field(lot_names):
	"""Store multiple lots on one SI line in custom_dispensing_lot."""
	clean = []
	seen = set()
	for name in lot_names or []:
		token = (name or "").strip()
		if token and token not in seen:
			clean.append(token)
			seen.add(token)
	return "\n".join(clean)


def _resolve_dispensing_lot_names_from_si_row(item_row):
	"""All dispensing lots on one Sales Invoice line from custom_dispensing_lot only."""
	return resolve_dispensing_lot_names_from_field(item_row.get("custom_dispensing_lot"))


def _resolve_dispensing_lot_from_si_row(item_row):
	"""First dispensing lot on the line (backward compatibility)."""
	names = _resolve_dispensing_lot_names_from_si_row(item_row)
	return names[0] if names else None


def _si_row_is_multi_pack_sale(item_row, lot_names):
	"""One invoice line, multiple packs — one physical lot per serial."""
	if len(lot_names) <= 1:
		return False
	stock_uom = frappe.db.get_value("Item", item_row.item_code, "stock_uom")
	return item_row.uom == stock_uom


def _sale_row_for_lot(item_row, lot, multi_pack):
	if multi_pack:
		stock_uom = lot.stock_uom or frappe.db.get_value("Item", item_row.item_code, "stock_uom")
		return frappe._dict(
			item_code=item_row.item_code,
			uom=stock_uom,
			qty=1,
			stock_qty=1,
		)
	return item_row


def _sale_rows_for_lots(item_row, lots, multi_pack):
	"""
	Sale rows aligned with `lots` for one sales line.

	Several lots on a line sold in the dispensing UOM share the line quantity:
	each lot is filled up to its remaining qty, in order. Without this every lot
	would be charged the whole line qty (2 UNIT against two 1-UNIT lots would
	fail as insufficient, and would consume double on submit).
	"""
	if multi_pack or len(lots) <= 1:
		return [_sale_row_for_lot(item_row, lot, multi_pack) for lot in lots]

	issue_uom, total_qty = compute_issue_from_sales_item(item_row, lots[0])
	if not total_qty:
		return [_sale_row_for_lot(item_row, lot, multi_pack) for lot in lots]

	rows = []
	remaining = flt(total_qty)
	last_index = len(lots) - 1

	for index, lot in enumerate(lots):
		if index == last_index:
			# Last lot absorbs any shortfall so validation reports it against that lot.
			lot_qty = remaining
		else:
			lot_qty = min(remaining, max(flt(lot.remaining_qty), 0))

		rows.append(
			frappe._dict(
				item_code=item_row.item_code,
				uom=issue_uom,
				qty=lot_qty,
				stock_qty=lot_qty,
			)
		)
		remaining = flt(remaining - lot_qty, 6)

	return rows


def _get_lot_docs(lot_names, validate_exists=False):
	lots = []
	for lot_name in lot_names:
		if validate_exists and not frappe.db.exists("Dispensing Lot", lot_name):
			frappe.throw(_("Dispensing Lot {0} does not exist").format(lot_name))
		lots.append(frappe.get_doc("Dispensing Lot", lot_name))
	return lots


def _recorded_lot_transaction(lot, reference_doctype, reference_name, transaction_type):
	"""(uom, qty) already posted on this lot for a reference."""
	qty = 0
	uom = None
	for row in lot.transactions:
		if (
			row.reference_doctype == reference_doctype
			and row.reference_name == reference_name
			and row.transaction_type == transaction_type
		):
			qty += flt(row.qty)
			uom = uom or row.uom
	return uom, qty


def apply_sales_invoice_to_dispensing_lot(item_row, reference_doctype, reference_name, posting_date, is_return=False):
	"""Post Out/In on each dispensing lot on this SI line (one pack per lot when multiple serials)."""
	lot_names = _resolve_dispensing_lot_names_from_si_row(item_row)
	if not lot_names:
		return

	multi_pack = _si_row_is_multi_pack_sale(item_row, lot_names)
	lots = _get_lot_docs(lot_names, validate_exists=True)
	sale_rows = _sale_rows_for_lots(item_row, lots, multi_pack)

	for lot, sale_row in zip(lots, sale_rows, strict=True):
		issue_uom, issue_qty = compute_issue_from_sales_item(sale_row, lot)

		if not issue_qty:
			continue

		transaction_type = "In" if is_return else "Out"

		if _lot_has_reference_transaction(lot, reference_doctype, reference_name, transaction_type):
			continue

		# Hospital flow: DN already consumed the lot; skip when SI is billed from that DN.
		if (
			not is_return
			and reference_doctype == "Sales Invoice"
			and item_row.get("delivery_note")
			and _lot_has_reference_transaction(
				lot, "Delivery Note", item_row.get("delivery_note"), "Out"
			)
		):
			continue

		if not is_return:
			validate_dispensing_lot_for_sale(sale_row, lot)

		_append_lot_transaction(
			lot,
			transaction_type=transaction_type,
			qty=issue_qty,
			uom=issue_uom,
			reference_doctype=reference_doctype,
			reference_name=reference_name,
			posting_date=posting_date,
			remarks=_("Return {0} {1}").format(reference_doctype, reference_name)
			if is_return
			else _("{0} {1}").format(reference_doctype, reference_name),
		)


def validate_sales_invoice_dispensing_lots(doc):
	if doc.get("is_return"):
		return

	# Hospital / DN flow: stock (and lot consumption) already happened on Delivery Note.
	# Only require/validate dispensing lots when this invoice itself updates stock.
	if not doc.get("update_stock"):
		return

	require_lot = is_dispensing_lot_validation_enabled("Sales Invoice")

	for row in doc.items:
		if not row.item_code:
			continue

		lot_names = _resolve_dispensing_lot_names_from_si_row(row)

		if require_lot and item_requires_dispensing_lot(row.item_code) and not lot_names:
			frappe.throw(
				_("Dispensing Lot is required for Item {0} in row {1}.").format(
					row.item_code, row.idx
				)
			)

		if not lot_names:
			continue

		multi_pack = _si_row_is_multi_pack_sale(row, lot_names)
		if multi_pack:
			lot_count = len(lot_names)
			if lot_count and flt(row.qty) != lot_count:
				frappe.throw(
					_(
						"Row {0}: quantity {1} must match the number of dispensing lots on the line ({2})."
					).format(row.idx, row.qty, lot_count)
				)

		lots = _get_lot_docs(lot_names)
		sale_rows = _sale_rows_for_lots(row, lots, multi_pack)
		for lot, sale_row in zip(lots, sale_rows, strict=True):
			validate_dispensing_lot_for_sale(sale_row, lot)


def process_sales_invoice_dispensing_lots(doc, is_return=False):
	for row in doc.items:
		if not _resolve_dispensing_lot_names_from_si_row(row):
			continue

		apply_sales_invoice_to_dispensing_lot(
			row,
			doc.doctype,
			doc.name,
			doc.posting_date or frappe.utils.today(),
			is_return=is_return,
		)


def reverse_sales_invoice_dispensing_lots(doc):
	"""On cancel, post opposite transactions if not already reversed."""
	is_return = doc.get("is_return")
	for row in doc.items:
		lot_names = _resolve_dispensing_lot_names_from_si_row(row)
		if not lot_names:
			continue

		multi_pack = _si_row_is_multi_pack_sale(row, lot_names)
		lots = _get_lot_docs(lot_names)
		sale_rows = _sale_rows_for_lots(row, lots, multi_pack)

		for lot, sale_row in zip(lots, sale_rows, strict=True):
			original_type = "In" if is_return else "Out"
			reverse_type = "Out" if is_return else "In"

			if not _lot_has_reference_transaction(lot, doc.doctype, doc.name, original_type):
				continue

			if _lot_has_reference_transaction(lot, doc.doctype, doc.name, reverse_type):
				continue

			# Mirror what was posted: re-splitting now would give a different share
			# per lot, because the original transaction already moved remaining_qty.
			issue_uom, issue_qty = _recorded_lot_transaction(
				lot, doc.doctype, doc.name, original_type
			)
			if not issue_qty:
				issue_uom, issue_qty = compute_issue_from_sales_item(sale_row, lot)
			if not issue_qty:
				continue

			_append_lot_transaction(
				lot,
				transaction_type=reverse_type,
				qty=issue_qty,
				uom=issue_uom,
				reference_doctype=doc.doctype,
				reference_name=doc.name,
				posting_date=doc.posting_date or frappe.utils.today(),
				remarks=_("Cancelled {0}").format(doc.name),
			)


def validate_delivery_note_dispensing_lots(doc, method=None):
	"""Validate dispensing lots on Delivery Note (hospital POS submits DN from Sales Order)."""
	if doc.get("is_return"):
		return

	require_lot = is_dispensing_lot_validation_enabled("Delivery Note")

	for row in doc.items:
		if not row.item_code:
			continue

		lot_names = _resolve_dispensing_lot_names_from_si_row(row)

		if require_lot and item_requires_dispensing_lot(row.item_code) and not lot_names:
			frappe.throw(
				_("Dispensing Lot is required for Item {0} in row {1}.").format(
					row.item_code, row.idx
				)
			)

		if not lot_names:
			continue

		multi_pack = _si_row_is_multi_pack_sale(row, lot_names)
		if multi_pack:
			lot_count = len(lot_names)
			if lot_count and flt(row.qty) != lot_count:
				frappe.throw(
					_(
						"Row {0}: quantity {1} must match the number of dispensing lots on the line ({2})."
					).format(row.idx, row.qty, lot_count)
				)

		lots = _get_lot_docs(lot_names)
		sale_rows = _sale_rows_for_lots(row, lots, multi_pack)
		for lot, sale_row in zip(lots, sale_rows, strict=True):
			validate_dispensing_lot_for_sale(sale_row, lot)


def process_delivery_note_dispensing_lots(doc, method=None):
	"""Consume / restore dispensing lots when Delivery Note is submitted."""
	process_sales_invoice_dispensing_lots(doc, is_return=bool(doc.get("is_return")))


def reverse_delivery_note_dispensing_lots(doc, method=None):
	"""Restore dispensing lots when Delivery Note is cancelled."""
	reverse_sales_invoice_dispensing_lots(doc)
