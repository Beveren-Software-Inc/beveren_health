# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import frappe
from beveren_health.beveren_health.utils.barcode import (
	generate_barcode_image,
	generate_ean13_barcode,
)


def _run_generate_barcodes_for_item_group(item_group):
	"""
	Internal: Generate EAN13 barcodes and images for all items in the item group.
	Returns a dict with counts and message. Used by background job.
	"""
	items = frappe.get_all(
		"Item",
		filters={"item_group": item_group, "disabled": 0},
		fields=["name", "item_code", "item_name"],
	)

	if not items:
		return {"message": f"No active items found in group {item_group}", "generated_barcodes": 0, "generated_images": 0, "skipped_count": 0}

	generated_barcodes = 0
	generated_images = 0
	skipped_count = 0

	for item in items:
		item_doc = frappe.get_doc("Item", item.name)
		item_updated = False
		has_barcode_with_image = False
		has_barcode_without_image = False
		barcode_row_to_update = None

		if item_doc.barcodes:
			for barcode_row in item_doc.barcodes:
				if barcode_row.barcode:
					if barcode_row.custom_image:
						has_barcode_with_image = True
						break
					else:
						has_barcode_without_image = True
						barcode_row_to_update = barcode_row
						break

		if has_barcode_with_image:
			skipped_count += 1
			continue

		if has_barcode_without_image:
			try:
				barcode_type = barcode_row_to_update.barcode_type or "EAN13"
				image_path = generate_barcode_image(barcode_row_to_update.barcode, barcode_type)
				barcode_row_to_update.custom_image = image_path
				item_updated = True
				generated_images += 1
			except Exception as e:
				frappe.log_error(
					title="Barcode Image Generation Error",
					message=f"Error generating barcode image for {barcode_row_to_update.barcode} (item {item.item_code}): {str(e)}",
				)
		else:
			new_barcode = generate_ean13_barcode()
			existing = frappe.db.exists("Item Barcode", {"barcode": new_barcode})
			if existing:
				new_barcode = generate_ean13_barcode()
				existing = frappe.db.exists("Item Barcode", {"barcode": new_barcode})
				if existing:
					frappe.log_error(
						title="Barcode Conflict",
						message=f"Barcode {new_barcode} already exists for item {item.item_code}",
					)
					continue

			item_doc.append("barcodes", {"barcode": new_barcode, "barcode_type": "EAN13"})
			try:
				image_path = generate_barcode_image(new_barcode, "EAN13")
				item_doc.barcodes[-1].custom_image = image_path
				item_updated = True
				generated_barcodes += 1
				generated_images += 1
			except Exception as e:
				frappe.log_error(
					title="Barcode Image Generation Error",
					message=f"Error generating barcode image for {new_barcode} (item {item.item_code}): {str(e)}",
				)

		if item_updated:
			item_doc.save(ignore_permissions=True)

	message_parts = []
	if generated_barcodes > 0:
		message_parts.append(f"Generated {generated_barcodes} new barcodes")
	if generated_images > 0:
		message_parts.append(f"Generated {generated_images} barcode images")
	if skipped_count > 0:
		message_parts.append(f"Skipped {skipped_count} items that already have barcodes with images")
	message = ". ".join(message_parts) if message_parts else "No changes made."

	return {
		"message": message,
		"generated_barcodes": generated_barcodes,
		"generated_images": generated_images,
		"skipped_count": skipped_count,
	}


def _run_barcode_generation_job(item_group):
	"""Wrapper for background job: run generation then notify via realtime."""
	try:
		result = _run_generate_barcodes_for_item_group(item_group)
		_notify_barcode_generation_done(item_group, result)
	except Exception as e:
		frappe.log_error(
			title="Barcode Generation Error",
			message=f"Error generating barcodes for item group {item_group}: {str(e)}",
		)
		_notify_barcode_generation_done(item_group, e)


def _notify_barcode_generation_done(item_group, result):
	"""Publish realtime event so the client can show the result."""
	if result is None or isinstance(result, Exception):
		frappe.publish_realtime(
			"item_group_barcode_generation_done",
			{"item_group": item_group, "error": True, "message": str(result) if result else "Job failed."},
		)
		return
	frappe.publish_realtime(
		"item_group_barcode_generation_done",
		{"item_group": item_group, "message": result.get("message"), "result": result},
	)


@frappe.whitelist()
def generate_barcodes_for_item_group(item_group):
	"""
	Queue EAN13 barcode generation for all items in the item group as a background job.
	Returns immediately; result is sent via realtime when the job completes.
	"""
	if not item_group:
		frappe.throw("Item Group is required")

	frappe.enqueue(
		method="beveren_health.beveren_health.customize.item_group._run_barcode_generation_job",
		queue="default",
		timeout=3600,
		item_group=item_group,
		enqueue_after_commit=True,
	)
	return {
		"queued": True,
		"message": "Barcode generation has been started in the background. You will be notified when it completes.",
	}
