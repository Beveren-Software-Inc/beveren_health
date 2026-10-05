import json

import frappe
from erpnext import is_perpetual_inventory_enabled
from frappe import _
from frappe.utils import cint, flt

from beveren_health.beveren_health.customize.dispensing_lot import (
	item_requires_dispensing_lot,
	split_dispensing_lots,
)


def _is_opening_stock_reconciliation(purpose):
	"""Match ERPNext Stock Reconciliation.validate_expense_account opening-entry rules."""
	if purpose == "Opening Stock":
		return True
	return not frappe.db.sql("select name from `tabStock Ledger Entry` limit 1")


def _resolve_difference_account(purpose, company):
	"""Pick a valid Difference Account (same logic as desk set_expense_account)."""
	from erpnext.stock.doctype.stock_reconciliation.stock_reconciliation import (
		get_difference_account,
	)

	if _is_opening_stock_reconciliation(purpose):
		account = get_difference_account("Opening Stock", company)
		if account:
			return account
		return frappe.db.get_value(
			"Account",
			{
				"company": company,
				"is_group": 0,
				"report_type": "Balance Sheet",
				"disabled": 0,
			},
			"name",
			order_by="name asc",
		)

	account = get_difference_account("Stock Reconciliation", company)
	if account:
		return account
	return frappe.db.get_value("Company", company, "stock_adjustment_account")


def _expense_account_valid_for_purpose(purpose, account):
	if not account:
		return False
	if _is_opening_stock_reconciliation(purpose):
		return frappe.db.get_value("Account", account, "report_type") != "Profit and Loss"
	return True


def _apply_stock_reconciliation_defaults(sr, base_scanner=None):
	"""Set accounts/cost center so insert passes validation; user can edit on the form."""
	if not sr.cost_center:
		sr.cost_center = (base_scanner and base_scanner.cost_center) or frappe.db.get_value(
			"Company", sr.company, "cost_center"
		)

	if (
		base_scanner
		and base_scanner.expense_account
		and _expense_account_valid_for_purpose(sr.purpose, base_scanner.expense_account)
	):
		sr.expense_account = base_scanner.expense_account
	else:
		sr.expense_account = _resolve_difference_account(sr.purpose, sr.company)


@frappe.whitelist()
def get_eligible_stock_scanners(company=None):
	"""Submitted scanners not yet used in a Stock Reconciliation (draft or submitted)."""
	filters = {
		"docstatus": 1,
		"stock_recon_created": 0,
		"stock_reconciliation": ["is", "not set"],
	}
	if company:
		filters["company"] = company

	return frappe.get_all(
		"Stock Scanner",
		filters=filters,
		fields=["name", "company", "set_warehouse", "posting_date", "owner"],
		order_by="posting_date desc, creation desc",
	)


@frappe.whitelist()
def create_stock_reconciliation_from_scanners(scanner_names: list | str):
	if isinstance(scanner_names, str):
		scanner_names = json.loads(scanner_names)

	if not scanner_names:
		frappe.throw(_("Select at least one Stock Scanner."))

	scanners = []
	for name in scanner_names:
		doc = frappe.get_doc("Stock Scanner", name)
		if doc.docstatus != 1:
			frappe.throw(
				_("Stock Scanner {0} must be submitted before creating Stock Reconciliation.").format(name)
			)
		if doc.stock_recon_created:
			frappe.throw(
				_("Stock Scanner {0} is already included in a submitted Stock Reconciliation.").format(name)
			)
		if doc.get("stock_reconciliation"):
			frappe.throw(
				_(
					"Stock Scanner {0} is already linked to draft Stock Reconciliation {1}. "
					"Submit or delete that document first."
				).format(name, doc.stock_reconciliation)
			)
		scanners.append(doc)

	companies = {s.company for s in scanners}
	if len(companies) > 1:
		frappe.throw(_("All selected Stock Scanners must belong to the same Company."))

	warehouses = {s.set_warehouse for s in scanners if s.set_warehouse}
	if len(warehouses) > 1:
		frappe.throw(_("All selected Stock Scanners must use the same Default Warehouse."))

	merged = {}
	for scanner in scanners:
		default_wh = scanner.set_warehouse
		for row in scanner.items:
			if not row.item_code:
				continue

			warehouse = row.warehouse or default_wh
			if not warehouse:
				frappe.throw(
					_("Set Default Warehouse on Stock Scanner {0} or warehouse on each line.").format(
						scanner.name
					)
				)

			key = (row.item_code, row.batch_no or "", warehouse)
			lots = split_dispensing_lots(row.get("serial_no") or "")
			valuation_rate = flt(row.valuation_rate)

			if key not in merged:
				merged[key] = {
					"item_code": row.item_code,
					"item_name": row.item_name,
					"batch_no": row.batch_no,
					"warehouse": warehouse,
					"lots": list(lots),
					"qty": flt(row.qty),
					"valuation_rate": valuation_rate,
					"stock_uom": row.stock_uom,
					"gtin": row.get("gtin"),
					"manufacturing_date": row.get("manufacturing_date"),
					"expiry_date": row.get("expiry_date"),
					"stock_scanners": [scanner.name],
				}
			else:
				entry = merged[key]
				for lot in lots:
					if lot and lot not in entry["lots"]:
						entry["lots"].append(lot)
				entry["qty"] = flt(entry.get("qty")) + flt(row.qty)
				if not entry.get("valuation_rate") and valuation_rate:
					entry["valuation_rate"] = valuation_rate
				if not entry.get("gtin") and row.get("gtin"):
					entry["gtin"] = row.get("gtin")
				if not entry.get("manufacturing_date") and row.get("manufacturing_date"):
					entry["manufacturing_date"] = row.get("manufacturing_date")
				if not entry.get("expiry_date") and row.get("expiry_date"):
					entry["expiry_date"] = row.get("expiry_date")
				if scanner.name not in entry["stock_scanners"]:
					entry["stock_scanners"].append(scanner.name)

	if not merged:
		frappe.throw(_("No item lines found on the selected Stock Scanner(s)."))

	base = scanners[0]
	sr = frappe.new_doc("Stock Reconciliation")
	sr.company = base.company
	sr.purpose = base.purpose or "Stock Reconciliation"
	sr.posting_date = base.posting_date
	sr.posting_time = base.posting_time
	if base.set_warehouse:
		sr.set_warehouse = base.set_warehouse

	_apply_stock_reconciliation_defaults(sr, base_scanner=base)

	if is_perpetual_inventory_enabled(sr.company) and not sr.expense_account:
		frappe.throw(
			_(
				"Could not resolve a Difference Account for {0}. "
				"For Opening Stock, set up a Temporary (Balance Sheet) account for the company, "
				"or set Purpose to Stock Reconciliation on the Stock Scanner."
			).format(sr.company)
		)

	for _key, entry in merged.items():
		qty = flt(entry.get("qty"))
		if not qty:
			qty = len(entry["lots"]) if entry["lots"] else 1
		valuation_rate = flt(entry.get("valuation_rate"))
		amount = qty * valuation_rate
		dispensing_lot = "\n".join(entry["lots"])

		item_row = {
			"item_code": entry["item_code"],
			"item_name": entry["item_name"],
			"warehouse": entry["warehouse"],
			"batch_no": entry["batch_no"] or None,
			"qty": qty,
			"valuation_rate": valuation_rate,
			"amount": amount,
			"stock_uom": entry["stock_uom"],
			"use_serial_batch_fields": 1,
			"allow_zero_valuation_rate": 1,
			"custom_dispensing_lot": dispensing_lot,
		}
		if frappe.db.has_column("Stock Reconciliation Item", "custom_stock_scanner"):
			item_row["custom_stock_scanner"] = ", ".join(entry.get("stock_scanners") or [])
		if entry.get("gtin"):
			item_row["custom_gstin"] = entry["gtin"]
		if entry.get("manufacturing_date"):
			item_row["custom_manufacturing_date"] = entry["manufacturing_date"]
		if entry.get("expiry_date"):
			item_row["custom_expiry_date"] = entry["expiry_date"]

		sr.append("items", item_row)

	sr.insert()
	frappe.db.commit()

	for scanner in scanners:
		if frappe.db.has_column("Stock Scanner", "stock_reconciliation"):
			frappe.db.set_value(
				"Stock Scanner",
				scanner.name,
				{"stock_reconciliation": sr.name},
				update_modified=True,
			)

	return sr.name


def mark_stock_scanners_on_reconciliation_submit(doc, method=None):
	"""Tick Stock Recon Created only after Stock Reconciliation is submitted."""
	if not frappe.db.has_column("Stock Scanner", "stock_reconciliation"):
		return

	for scanner_name in frappe.get_all(
		"Stock Scanner",
		filters={"stock_reconciliation": doc.name},
		pluck="name",
	):
		frappe.db.set_value(
			"Stock Scanner",
			scanner_name,
			{"stock_recon_created": 1},
			update_modified=True,
		)


def release_stock_scanners_from_reconciliation(doc, method=None):
	"""Clear scanner link when Stock Reconciliation is cancelled or deleted."""
	if not frappe.db.has_column("Stock Scanner", "stock_reconciliation"):
		return

	for scanner_name in frappe.get_all(
		"Stock Scanner",
		filters={"stock_reconciliation": doc.name},
		pluck="name",
	):
		frappe.db.set_value(
			"Stock Scanner",
			scanner_name,
			{"stock_recon_created": 0, "stock_reconciliation": None},
			update_modified=True,
		)


def _get_stock_scanner_for_validation(name: str):
	if not name:
		frappe.throw(_("Stock Scanner is required."))
	if not frappe.db.exists("Stock Scanner", name):
		frappe.throw(_("Stock Scanner {0} not found.").format(name))
	doc = frappe.get_doc("Stock Scanner", name)
	frappe.has_permission("Stock Scanner", "read", doc=doc, throw=True)
	return doc


def _missing_row_payload(row):
	return {
		"idx": row.idx,
		"item_code": row.item_code,
		"item_name": row.item_name or "",
		"warehouse": row.warehouse or "",
		"qty": row.qty,
		"batch_no": row.batch_no or "",
	}


@frappe.whitelist()
def validate_missing_batches(name: str):
	"""List Stock Scanner lines whose Item requires a batch but batch_no is empty."""
	doc = _get_stock_scanner_for_validation(name)
	missing = []

	for row in doc.get("items") or []:
		if not row.item_code:
			continue
		if not cint(frappe.db.get_value("Item", row.item_code, "has_batch_no") or 0):
			continue
		if (row.batch_no or "").strip():
			continue
		missing.append(_missing_row_payload(row))

	return {
		"ok": not missing,
		"count": len(missing),
		"rows": missing,
		"message": (
			_("All batch items have a Batch No.")
			if not missing
			else _("Found {0} line(s) that need a Batch No.").format(len(missing))
		),
	}


@frappe.whitelist()
def validate_missing_dispensing_lots(name: str):
	"""List Stock Scanner lines whose Item requires a dispensing lot but serial_no is empty."""
	doc = _get_stock_scanner_for_validation(name)
	missing = []

	for row in doc.get("items") or []:
		if not row.item_code:
			continue
		if not item_requires_dispensing_lot(row.item_code):
			continue
		if split_dispensing_lots(row.get("serial_no") or ""):
			continue
		missing.append(_missing_row_payload(row))

	return {
		"ok": not missing,
		"count": len(missing),
		"rows": missing,
		"message": (
			_("All dispensing items have a Dispensing Lot.")
			if not missing
			else _("Found {0} line(s) that need a Dispensing Lot.").format(len(missing))
		),
	}


@frappe.whitelist()
def validate_batch_item_mismatch(name: str):
	"""List Stock Scanner lines where Batch No does not belong to the line Item."""
	doc = _get_stock_scanner_for_validation(name)
	mismatched = []

	for row in doc.get("items") or []:
		if not row.item_code or not (row.batch_no or "").strip():
			continue

		batch_item = frappe.db.get_value("Batch", row.batch_no, "item")
		if not batch_item:
			mismatched.append(
				{
					**_missing_row_payload(row),
					"batch_item": "",
					"reason": _("Batch not found"),
				}
			)
			continue

		if batch_item == row.item_code:
			continue

		mismatched.append(
			{
				**_missing_row_payload(row),
				"batch_item": batch_item,
				"reason": _("Batch belongs to another item"),
			}
		)

	return {
		"ok": not mismatched,
		"count": len(mismatched),
		"rows": mismatched,
		"message": (
			_("All batches belong to their line items.")
			if not mismatched
			else _("Found {0} line(s) where Batch does not belong to the Item.").format(len(mismatched))
		),
	}
