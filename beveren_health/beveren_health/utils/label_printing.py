# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt, formatdate


def _item_name_line(item_doc, batch_uom=None):
	"""Build: Item Name + Concentration (custom_strength) + Pharmaceutical Form + UOM (batch uom) + No of Pack (custom_number_of_pack)."""
	uom = (batch_uom or item_doc.get("stock_uom") or "").strip()
	parts = [
		(item_doc.item_name or item_doc.name or "").strip(),
		(getattr(item_doc, "custom_strength", None) or "").strip(),
		(getattr(item_doc, "custom_pharmaceutical_form", None) or "").strip(),
		uom,
		(getattr(item_doc, "custom_number_of_pack", None) or "").strip(),
	]
	return " ".join(p for p in parts if p) or "N/A"


@frappe.whitelist()
def get_label_data_for_batch(batch_name):
	"""
	Get all data needed to print a label for a Batch.
	Label order: Barcode Image, Barcode Number, Item Code, Item Name line, Standard Selling Price, Batch Number, Expiry Date.
	"""
	if not batch_name or not frappe.db.exists("Batch", batch_name):
		return None

	batch_doc = frappe.get_doc("Batch", batch_name)
	item_code = batch_doc.item
	item_doc = frappe.get_doc("Item", item_code)

	# Get barcode for THIS SPECIFIC BATCH
	barcode_image = None
	barcode_value = None
	
	if item_doc.barcodes:
		for row in item_doc.barcodes:
			
			# Check if this barcode row is linked to our batch
			if getattr(row, "custom_batch", None) == batch_name:
				barcode_image = getattr(row, "custom_image", None)
				barcode_value = getattr(row, "barcode", None) or ""
				break

	# Item Standard Selling Price (standard_rate)
	standard_rate = flt(item_doc.get("standard_rate") or 0)
	company = frappe.get_all("Company", fields=["name", "default_currency"], limit=1)
	currency = company[0].get("default_currency") if company else "USD"
	standard_selling_price = frappe.format_value(
		standard_rate, {"fieldtype": "Currency", "options": currency}
	)

	expiry_date = batch_doc.expiry_date
	if expiry_date:
		expiry_date = formatdate(expiry_date)
	else:
		expiry_date = "N/A"

	return {
		"item_code": item_code,
		"item_name_line": _item_name_line(item_doc, batch_doc.get("uom")),
		"barcode_image": barcode_image,
		"barcode_value": barcode_value or "",
		"standard_selling_price": standard_selling_price,
		"batch_no": batch_name,
		"expiry_date": expiry_date,
	}
# def get_label_data_for_batch(batch_name):
# 	"""
# 	Get all data needed to print a label for a Batch.
# 	Label order: Barcode Image, Barcode Number, Item Code, Item Name line, Standard Selling Price, Batch Number, Expiry Date.
# 	"""
# 	if not batch_name or not frappe.db.exists("Batch", batch_name):
# 		return None

# 	batch_doc = frappe.get_doc("Batch", batch_name)
# 	item_code = batch_doc.item
# 	item_doc = frappe.get_doc("Item", item_code)

# 	barcode_image = None
# 	barcode_value = None
# 	if item_doc.barcodes:
# 		for row in item_doc.barcodes:
# 			if getattr(row, "custom_image", None):
# 				barcode_image = row.custom_image
# 				barcode_value = getattr(row, "barcode", None) or ""
# 				break

# 	# Item Standard Selling Price (standard_rate)
# 	standard_rate = flt(item_doc.get("standard_rate") or 0)
# 	company = frappe.get_all("Company", fields=["name", "default_currency"], limit=1)
# 	currency = company[0].get("default_currency") if company else "USD"
# 	standard_selling_price = frappe.format_value(
# 		standard_rate, {"fieldtype": "Currency", "options": currency}
# 	)

# 	expiry_date = batch_doc.expiry_date
# 	if expiry_date:
# 		expiry_date = formatdate(expiry_date)
# 	else:
# 		expiry_date = "N/A"

# 	return {
# 		"item_code": item_code,
# 		"item_name_line": _item_name_line(item_doc, batch_doc.get("uom")),
# 		"barcode_image": barcode_image,
# 		"barcode_value": barcode_value or "",
# 		"standard_selling_price": standard_selling_price,
# 		"batch_no": batch_name,
# 		"expiry_date": expiry_date,
# 	}


@frappe.whitelist()
def get_batch_and_expiry_from_bundle(serial_and_batch_bundle):
	"""
	Get batch_no and expiry_date from a Serial and Batch Bundle.
	Returns the first batch in the bundle (for label printing when item row has no batch_no field).
	"""
	if not serial_and_batch_bundle or not frappe.db.exists("Serial and Batch Bundle", serial_and_batch_bundle):
		return {"batch_no": None, "expiry_date": None}

	try:
		from erpnext.stock.serial_batch_bundle import get_batch_nos
	except ImportError:
		return {"batch_no": None, "expiry_date": None}

	batches = get_batch_nos(serial_and_batch_bundle)
	if not batches:
		return {"batch_no": None, "expiry_date": None}

	batch_no = next(iter(batches.keys()), None)
	if not batch_no:
		return {"batch_no": None, "expiry_date": None}

	expiry_date = frappe.db.get_value("Batch", batch_no, "expiry_date")
	if expiry_date:
		expiry_date = formatdate(expiry_date)
	uom = frappe.db.get_value("Batch", batch_no, "uom")

	return {"batch_no": batch_no, "expiry_date": expiry_date or None, "uom": uom}
