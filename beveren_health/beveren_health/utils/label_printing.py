# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import formatdate


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

	return {"batch_no": batch_no, "expiry_date": expiry_date or None}
