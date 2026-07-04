# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint, flt

DISPENSING_LOT_FIELD = "custom_dispensing_lot"

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


def item_requires_dispensing_lot(item_code):
	"""Item flagged on master — dispensing lot mandatory (like serial no)."""
	if not item_code:
		return False
	return bool(cint(frappe.db.get_value("Item", item_code, "custom_has_dispense_lot") or 0))


def validate_row_has_dispensing_lot(row, row_label=None):
	"""Raise if item requires a dispensing lot but the stock/sales line has none."""
	if not item_requires_dispensing_lot(row.get("item_code")):
		return

	if _serials_from_stock_row(row):
		return

	# label = row_label or _("row {0}").format(row.get("idx") or "")
	# frappe.throw(
	# 	_("Dispensing Lot is required for Item {0} ({1}). Scan or select a lot on the line.").format(
	# 		row.item_code, label
	# 	)
	# )


def split_dispensing_lots(value):
	if not value:
		return []

	if "\n" in value:
		return [s.strip() for s in value.split("\n") if s.strip()]
	if "," in value:
		return [s.strip() for s in value.split(",") if s.strip()]

	return [value.strip()] if value.strip() else []


def get_pack_size_and_uom(item_code):
	"""Return (pack_size in dispensing UOM, dispensing_uom) for one physical pack."""
	item = frappe.get_cached_doc("Item", item_code)
	pack_size = flt(item.get("custom_pack_size"))

	if pack_size:
		dispensing_uom = _get_dispensing_uom_from_item(item)
		return pack_size, dispensing_uom

	stock_uom = item.stock_uom
	for row in item.get("uoms") or []:
		if row.uom == stock_uom:
			continue

		cf = flt(row.conversion_factor)
		if not cf:
			continue

		if cf >= 1:
			return cf, row.uom
		return flt(1 / cf), row.uom

	return 1, stock_uom


def _get_dispensing_uom_from_item(item):
	stock_uom = item.stock_uom
	for row in item.get("uoms") or []:
		if row.uom and row.uom != stock_uom:
			return row.uom
	return stock_uom


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
	"""Move an existing pack (full serial) to the target warehouse — no qty In/Out."""
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
		frappe.throw(
			_("Dispensing Lot not found for serial {0}. Receive the pack before transferring.").format(
				serial_no
			)
		)

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
	config = STOCK_DOC_CONFIG.get(doc.doctype)
	if not config:
		return

	for row in doc.get(config["items_field"]) or []:
		if not row.item_code:
			continue
		validate_row_has_dispensing_lot(row, row_label=_("row {0}").format(row.idx))


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
	"""Require lots on flagged items; block partial pack transfer."""
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
				frappe.throw(
					_("Dispensing Lot {0} was not found for Item {1} on row {2}.").format(
						serial, row.item_code, row.idx
					)
				)
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

		if _is_material_transfer_stock_entry(doc):
			for serial in serials:
				_transfer_dispensing_lot_on_material_transfer(doc, row, serial)
			continue

		pack_size, dispensing_uom = get_pack_size_and_uom(row.item_code)
		warehouse = get_warehouse_for_row(doc, row, config)

		gtin = row.get("custom_gstin") or frappe.db.get_value(
			"Item", row.item_code, "custom_gtin_number"
		)

		posting_date = doc.get("posting_date") or frappe.utils.today()

		for serial in serials:
			_create_dispensing_lot_if_missing(
				item=row.item_code,
				batch_no=row.batch_no,
				serial_no=serial,
				warehouse=warehouse,
				pack_size=pack_size,
				dispensing_uom=dispensing_uom,
				gtin=gtin,
				reference_doctype=doc.doctype,
				reference_name=doc.name,
				posting_date=posting_date,
			)


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
	pack_size,
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

	pack_size = flt(pack_size) or flt(lot.initial_qty) or 1

	lot.item = item
	lot.batch_no = batch_no
	if warehouse:
		lot.warehouse = warehouse
	lot.uom = dispensing_uom or lot.uom
	lot.initial_qty = pack_size
	if gtin:
		lot.gtin = gtin
	if serial_no and not lot.serial_no:
		lot.serial_no = serial_no

	lot.source_doctype = reference_doctype
	lot.source_document = reference_name

	in_qty = pack_size - flt(lot.remaining_qty)

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
	pack_size,
	dispensing_uom,
	gtin=None,
	reference_doctype=None,
	reference_name=None,
	posting_date=None,
):
	posting_date = posting_date or frappe.utils.today()
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
				pack_size,
				dispensing_uom,
				gtin,
				reference_doctype,
				reference_name,
				posting_date,
			)

		# Already active — refresh source link to this document
		lot.source_doctype = reference_doctype
		lot.source_document = reference_name
		if warehouse:
			lot.warehouse = warehouse
		lot.batch_no = batch_no
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
			"initial_qty": pack_size,
			"remaining_qty": pack_size,
			"status": "Active",
			"source_doctype": reference_doctype,
			"source_document": reference_name,
		}
	)
	lot.insert(ignore_permissions=True)
	return lot.name


def _lot_has_dispensing_uom_unit_sales(lot):
	"""True if this pack was already sold in dispensing UOM (tabs/units), not as a full pack."""
	stock_uom = lot.stock_uom
	dispensing_uom = lot.uom
	if not stock_uom or not dispensing_uom or stock_uom == dispensing_uom:
		return False

	for row in lot.transactions:
		if row.transaction_type != "Out" or row.reference_doctype != "Sales Invoice":
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
		if row.transaction_type == "Out" and row.reference_doctype == "Sales Invoice":
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


def apply_sales_invoice_to_dispensing_lot(item_row, reference_doctype, reference_name, posting_date, is_return=False):
	"""Post Out/In on each dispensing lot on this SI line (one pack per lot when multiple serials)."""
	lot_names = _resolve_dispensing_lot_names_from_si_row(item_row)
	if not lot_names:
		return

	multi_pack = _si_row_is_multi_pack_sale(item_row, lot_names)

	for lot_name in lot_names:
		if not frappe.db.exists("Dispensing Lot", lot_name):
			frappe.throw(_("Dispensing Lot {0} does not exist").format(lot_name))

		lot = frappe.get_doc("Dispensing Lot", lot_name)
		sale_row = _sale_row_for_lot(item_row, lot, multi_pack)
		issue_uom, issue_qty = compute_issue_from_sales_item(sale_row, lot)

		if not issue_qty:
			continue

		transaction_type = "In" if is_return else "Out"

		if _lot_has_reference_transaction(lot, reference_doctype, reference_name, transaction_type):
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
			remarks=_("Sales return {0}").format(reference_name)
			if is_return
			else _("Sales Invoice {0}").format(reference_name),
		)


def validate_sales_invoice_dispensing_lots(doc):
	if doc.get("is_return"):
		return

	for row in doc.items:
		if not row.item_code:
			continue

		lot_names = _resolve_dispensing_lot_names_from_si_row(row)

		# if item_requires_dispensing_lot(row.item_code) and not lot_names:
		# 	frappe.throw(
		# 		_("Dispensing Lot is required for Item {0} in row {1}.").format(
		# 			row.item_code, row.idx
		# 		)
		# 	)

		# if not lot_names:
		# 	continue

		multi_pack = _si_row_is_multi_pack_sale(row, lot_names)
		if multi_pack:
			lot_count = len(lot_names)
			if lot_count and flt(row.qty) != lot_count:
				frappe.throw(
					_(
						"Row {0}: quantity {1} must match the number of dispensing lots on the line ({2})."
					).format(row.idx, row.qty, lot_count)
				)

		for lot_name in lot_names:
			lot = frappe.get_doc("Dispensing Lot", lot_name)
			validate_dispensing_lot_for_sale(_sale_row_for_lot(row, lot, multi_pack), lot)


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

		for lot_name in lot_names:
			lot = frappe.get_doc("Dispensing Lot", lot_name)
			sale_row = _sale_row_for_lot(row, lot, multi_pack)
			issue_uom, issue_qty = compute_issue_from_sales_item(sale_row, lot)
			if not issue_qty:
				continue

			original_type = "In" if is_return else "Out"
			reverse_type = "Out" if is_return else "In"

			if not _lot_has_reference_transaction(lot, doc.doctype, doc.name, original_type):
				continue

			if _lot_has_reference_transaction(lot, doc.doctype, doc.name, reverse_type):
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
