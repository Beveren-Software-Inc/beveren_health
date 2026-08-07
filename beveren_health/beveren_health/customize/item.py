# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint

from beveren_health.beveren_health.customize.item_group import (
	_run_migrate_serials_for_item_codes,
)
from beveren_health.beveren_health.utils.barcode import DEFAULT_BARCODE_TYPE, generate_barcode_image


def on_update(doc, method):
	"""
	Generate barcode images for barcodes that don't have images when Item is saved.
	"""
	if not doc.barcodes:
		return

	for barcode_row in doc.barcodes:
		# Check if barcode has a value but no image
		if barcode_row.barcode and not barcode_row.custom_image:
			try:
				# Determine barcode type (default to EAN13)
				barcode_type = barcode_row.barcode_type or DEFAULT_BARCODE_TYPE
				
				# Generate barcode image
				image_path = generate_barcode_image(barcode_row.barcode, barcode_type)
				
				# Update the barcode row with the image
				barcode_row.custom_image = image_path
				
				frappe.msgprint(
					f"Generated barcode image for {barcode_row.barcode}",
					indicator="green",
					alert=True
				)
			except Exception as e:
				frappe.log_error(
					title="Barcode Image Generation Error",
					message=f"Error generating barcode image for {barcode_row.barcode}: {str(e)}"
				)


def _run_migrate_serials_to_dispensing_lots_for_item(item_code):
	"""Create Dispensing Lots from Serial Nos for a single item (pack size from UNIT UOM)."""
	if not frappe.db.exists("Item", item_code):
		frappe.throw(_("Item {0} not found").format(item_code))

	has_batch_no = cint(frappe.db.get_value("Item", item_code, "has_batch_no"))
	if not has_batch_no:
		frappe.throw(
			_(
				"Item {0} does not have Batch enabled. "
				"Dispensing Lots require a batch on each Serial No."
			).format(item_code)
		)

	serial_count = frappe.db.count("Serial No", {"item_code": item_code})
	if not serial_count:
		return {
			"message": _("No Serial Nos found for item {0}.").format(item_code),
			"created_count": 0,
			"skipped_count": 0,
			"error_count": 0,
			"errors": [],
		}

	return _run_migrate_serials_for_item_codes(
		[item_code], item_code, source_doctype="Item"
	)


def _run_migrate_serials_to_dispensing_lots_for_item_job(item_code):
	try:
		result = _run_migrate_serials_to_dispensing_lots_for_item(item_code)
		_notify_item_migrate_serials_done(item_code, result)
	except Exception as e:
		frappe.log_error(
			title="Migrate Serials to Dispensing Lot (Item)",
			message=f"Item {item_code}: {frappe.get_traceback()}",
		)
		_notify_item_migrate_serials_done(item_code, e)


def _notify_item_migrate_serials_done(item_code, result):
	if result is None or isinstance(result, Exception):
		frappe.publish_realtime(
			"item_migrate_serials_done",
			{
				"item_code": item_code,
				"error": True,
				"message": str(result) if result else _("Job failed."),
			},
		)
		return

	frappe.publish_realtime(
		"item_migrate_serials_done",
		{
			"item_code": item_code,
			"message": result.get("message"),
			"result": result,
		},
	)


@frappe.whitelist()
def migrate_serials_to_dispensing_lots_for_item(item_code):
	"""
	Queue background job: create Dispensing Lots from existing Serial Nos for this item.

	Uses serial number as the dispensing lot identity, batch from the Serial No,
	and pack size / UNIT conversion from the item. Does not alter Serial No records.
	"""
	if not item_code:
		frappe.throw(_("Item is required"))

	if not frappe.db.exists("Item", item_code):
		frappe.throw(_("Item {0} not found").format(item_code))

	has_batch_no = cint(frappe.db.get_value("Item", item_code, "has_batch_no"))
	if not has_batch_no:
		frappe.throw(
			_(
				"Item {0} does not have Batch enabled. "
				"Enable Has Batch No (and ensure Serial Nos have a batch) before migrating."
			).format(item_code)
		)

	serial_count = frappe.db.count("Serial No", {"item_code": item_code})
	if not serial_count:
		frappe.throw(_("No Serial Nos found for item {0}.").format(item_code))

	frappe.enqueue(
		method=(
			"beveren_health.beveren_health.customize.item."
			"_run_migrate_serials_to_dispensing_lots_for_item_job"
		),
		queue="long",
		timeout=2700,
		item_code=item_code,
		enqueue_after_commit=True,
		job_name=f"Migrate serials to DL: {item_code}",
	)
	return {
		"queued": True,
		"message": _(
			"Migration started for {0} ({1} Serial No(s)). "
			"Dispensing Lots will be created in the background with pack size from the item UOM. "
			"You will be notified when complete."
		).format(item_code, serial_count),
	}
