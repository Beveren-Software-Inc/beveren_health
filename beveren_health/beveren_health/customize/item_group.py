# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

from beveren_health.beveren_health.customize.dispensing_lot import (
	get_pack_size_and_uom,
)
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

# @frappe.whitelist()
# def reverse_uom_conversions(item_group):
#     """
#     Reverse UOM conversions for all items in the item group
#     Changes from Unit/Nos-based to Pack-based
#     Handles: PACK↔Unit and PACK↔Nos
#     """
    
#     # Get all items in this item group
#     items = frappe.get_all("Item", 
#         filters={"item_group": item_group},
#         fields=["name"]
#     )
   
#     updated_items = []
#     errors = []
    
#     for item in items:
#         try:
#             item_doc = frappe.get_doc("Item", item.name)
            
#             # Check if item has UOM conversions
#             if not item_doc.uoms:
#                 continue
            
#             # First pass: Find the old PACK conversion factor
#             old_pack_conversion = None
#             for uom_row in item_doc.uoms:
#                 if uom_row.uom in ["PACK", "Pack"]:
#                     old_pack_conversion = uom_row.conversion_factor
#                     break
            
#             # If no PACK found or it's already 1, skip
#             if not old_pack_conversion or old_pack_conversion == 1:
#                 continue
            
#             conversion_updated = False
            
#             # Second pass: Update conversions
#             for uom_row in item_doc.uoms:
#                 if uom_row.uom in ["PACK", "Pack"]:
#                     # Set PACK as base (1)
#                     uom_row.conversion_factor = 1
#                     conversion_updated = True
                    
#                 elif uom_row.uom in ["Unit","UNITS", "UNIT", "Nos", "NOS", "nos"]:
#                     # Set to 1/old_pack_conversion
#                     # Old: PACK=30, Unit=1
#                     # New: PACK=1, Unit=1/30
#                     uom_row.conversion_factor = 1 / old_pack_conversion
#                     conversion_updated = True
            
#             if conversion_updated:
#                 item_doc.save()
#                 updated_items.append(item.name)
                
#         except Exception as e:
#             errors.append(f"{item.name}: {str(e)}")
    
#     return {
#         "success": True,
#         "updated_count": len(updated_items),
#         "updated_items": updated_items,
#         "errors": errors
#     }

def _run_clear_has_serial_no_for_item_group(item_group):
	"""Set has_serial_no = 0 on all items in this item group (db.set_value per item)."""
	items = frappe.get_all("Item", filters={"item_group": item_group}, pluck="name")

	if not items:
		return {
			"message": f"No items found in group {item_group}",
			"updated_count": 0,
			"errors": [],
		}

	updated_items = []
	errors = []

	for item_name in items:
		try:
			frappe.db.set_value("Item", item_name, "has_serial_no", 0, update_modified=False)
			updated_items.append(item_name)
		except Exception as e:
			errors.append(f"{item_name}: {str(e)}")
			frappe.log_error(
				title="Clear has_serial_no Error",
				message=f"Item {item_name} in group {item_group}: {e}",
			)

	frappe.db.commit()

	message = _("Cleared Has Serial No on {0} item(s) in group {1}.").format(
		len(updated_items), item_group
	)
	if errors:
		message += " " + _("{0} error(s).").format(len(errors))

	return {
		"message": message,
		"updated_count": len(updated_items),
		"updated_items": updated_items,
		"errors": errors,
	}


def _run_clear_has_serial_no_job(item_group):
	try:
		result = _run_clear_has_serial_no_for_item_group(item_group)
		_notify_clear_has_serial_no_done(item_group, result)
	except Exception as e:
		frappe.log_error(
			title="Clear has_serial_no Job Error",
			message=f"Item group {item_group}: {e}",
		)
		_notify_clear_has_serial_no_done(item_group, e)


def _notify_clear_has_serial_no_done(item_group, result):
	if result is None or isinstance(result, Exception):
		frappe.publish_realtime(
			"item_group_clear_serial_no_done",
			{
				"item_group": item_group,
				"error": True,
				"message": str(result) if result else _("Job failed."),
			},
		)
		return

	frappe.publish_realtime(
		"item_group_clear_serial_no_done",
		{
			"item_group": item_group,
			"message": result.get("message"),
			"result": result,
		},
	)


@frappe.whitelist()
def clear_has_serial_no_for_item_group(item_group):
	"""Queue background job to clear has_serial_no on all items in this item group."""
	if not item_group:
		frappe.throw(_("Item Group is required"))

	frappe.enqueue(
		method="beveren_health.beveren_health.customize.item_group._run_clear_has_serial_no_job",
		queue="long",
		timeout=3600,
		item_group=item_group,
		enqueue_after_commit=True,
		job_name=f"Clear has_serial_no: {item_group}",
	)
	return {
		"queued": True,
		"message": _(
			"Clearing Has Serial No for all items in {0} has started in the background. "
			"You will be notified when it completes."
		).format(item_group),
	}


def _dispensing_lot_exists_for_serial(serial_no):
	if not serial_no:
		return True
	if frappe.db.exists("Dispensing Lot", serial_no):
		return True
	return bool(frappe.db.get_value("Dispensing Lot", {"serial_no": serial_no}, "name"))


def _migrate_one_serial_to_dispensing_lot(serial_row, item_group):
	"""
	Create one Dispensing Lot from an ERPNext Serial No row (migration only — does not alter Serial No).
	"""
	serial_no = (serial_row.get("serial_no") or serial_row.get("name") or "").strip()
	if not serial_no:
		return "skipped", _("Missing serial number")

	if _dispensing_lot_exists_for_serial(serial_no):
		return "skipped_exists", serial_no

	item_code = serial_row.get("item_code")
	if not item_code:
		return "error", _("Serial {0}: no item").format(serial_no)

	batch_no = serial_row.get("batch_no")
	if not batch_no:
		return "error", _("Serial {0}: batch is required for Dispensing Lot").format(serial_no)

	pack_size, dispensing_uom = get_pack_size_and_uom(item_code)
	if not pack_size or pack_size <= 0:
		pack_size = 1

	gtin = serial_row.get("custom_gtin") or frappe.db.get_value(
		"Item", item_code, "custom_gtin_number"
	)

	warehouse = serial_row.get("warehouse")
	serial_status = (serial_row.get("status") or "Active").strip()

	if serial_status == "Delivered":
		remaining_qty = 0
		lot_status = "Delivered"
	elif serial_status in ("Inactive", "Expired"):
		remaining_qty = 0
		lot_status = "Inactive"
	else:
		remaining_qty = pack_size
		lot_status = "Active"

	lot = frappe.get_doc(
		{
			"doctype": "Dispensing Lot",
			"naming_series": "DL-.YYYY.-",
			"item": item_code,
			"batch_no": batch_no,
			"warehouse": warehouse,
			"serial_no": serial_no,
			"gtin": gtin,
			"uom": dispensing_uom,
			"initial_qty": pack_size,
			"remaining_qty": remaining_qty,
			"status": lot_status,
			"source_doctype": "Item Group",
			"source_document": item_group,
		}
	)
	lot.insert(ignore_permissions=True)

	# validate() recalculates remaining from transactions; fix Delivered/Inactive after insert
	if lot_status != "Active" or flt(remaining_qty) != flt(pack_size):
		frappe.db.set_value(
			"Dispensing Lot",
			lot.name,
			{"remaining_qty": remaining_qty, "status": lot_status},
			update_modified=False,
		)

	return "created", lot.name


def _run_migrate_serials_to_dispensing_lots(item_group):
	"""Create Dispensing Lot records from all Serial Nos for items in this item group."""
	item_codes = frappe.get_all(
		"Item", filters={"item_group": item_group}, pluck="name"
	)

	if not item_codes:
		return {
			"message": _("No items in group {0}").format(item_group),
			"created_count": 0,
			"skipped_count": 0,
			"errors": [],
		}

	serial_fields = ["name", "serial_no", "item_code", "batch_no", "warehouse", "status"]
	if frappe.db.has_column("Serial No", "custom_gtin"):
		serial_fields.append("custom_gtin")

	serials = frappe.get_all(
		"Serial No",
		filters={"item_code": ["in", item_codes]},
		fields=serial_fields,
		order_by="item_code asc, creation asc",
	)

	created = []
	skipped = []
	errors = []
	commit_every = 100

	for idx, serial_row in enumerate(serials, start=1):
		try:
			result_type, detail = _migrate_one_serial_to_dispensing_lot(serial_row, item_group)
			if result_type == "created":
				created.append(detail)
			elif result_type == "skipped_exists":
				skipped.append(detail)
			elif result_type == "skipped":
				skipped.append(detail)
			else:
				errors.append(detail if isinstance(detail, str) else str(detail))
		except Exception as e:
			label = serial_row.get("serial_no") or serial_row.get("name")
			errors.append(f"{label}: {e}")
			frappe.log_error(
				title="Serial to Dispensing Lot migration",
				message=f"Item group {item_group}, serial {label}: {frappe.get_traceback()}",
			)

		if idx % commit_every == 0:
			frappe.db.commit()

	frappe.db.commit()

	message = _(
		"Migrated Serial Nos to Dispensing Lot for {0}: {1} created, {2} skipped, {3} error(s)."
	).format(item_group, len(created), len(skipped), len(errors))

	return {
		"message": message,
		"created_count": len(created),
		"skipped_count": len(skipped),
		"error_count": len(errors),
		"errors": errors[:50],
	}


def _run_migrate_serials_to_dispensing_lots_job(item_group):
	try:
		result = _run_migrate_serials_to_dispensing_lots(item_group)
		_notify_migrate_serials_done(item_group, result)
	except Exception as e:
		frappe.log_error(
			title="Migrate Serials to Dispensing Lot",
			message=f"Item group {item_group}: {frappe.get_traceback()}",
		)
		_notify_migrate_serials_done(item_group, e)


def _notify_migrate_serials_done(item_group, result):
	if result is None or isinstance(result, Exception):
		frappe.publish_realtime(
			"item_group_migrate_serials_done",
			{
				"item_group": item_group,
				"error": True,
				"message": str(result) if result else _("Job failed."),
			},
		)
		return

	frappe.publish_realtime(
		"item_group_migrate_serials_done",
		{
			"item_group": item_group,
			"message": result.get("message"),
			"result": result,
		},
	)


@frappe.whitelist()
def migrate_serials_to_dispensing_lots(item_group):
	"""Background job: create Dispensing Lots from Serial Nos for all items in the item group."""
	if not item_group:
		frappe.throw(_("Item Group is required"))

	frappe.enqueue(
		method="beveren_health.beveren_health.customize.item_group._run_migrate_serials_to_dispensing_lots_job",
		queue="long",
		timeout=2700,
		item_group=item_group,
		enqueue_after_commit=True,
		job_name=f"Migrate serials to DL: {item_group}",
	)
	return {
		"queued": True,
		"message": _(
			"Migration started for {0}. Serial Nos will be copied to Dispensing Lot in the background "
			"(up to 45 minutes). You will be notified when complete."
		).format(item_group),
	}


@frappe.whitelist()
def reverse_uom_conversions(item_group):
    """
    Enqueue UOM conversion reversal to run in background
    Returns immediately with job info
    """
    frappe.enqueue(
        method='beveren_health.beveren_health.customize.item_group.reverse_uom_conversions_background',
        queue='long',  # Use 'long' queue for time-consuming tasks
        timeout=1200,
        is_async=True,
        job_name=f'UOM Reversal: {item_group}',
        item_group=item_group
    )
    
    return {
        "success": True,
        "message": f"UOM conversion reversal started for {item_group}. You'll be notified when complete."
    }


def reverse_uom_conversions_background(item_group):
    """
    Background worker function - DO NOT call directly
    This runs in the background queue
    """
    
    # Get all items in this item group
    items = frappe.get_all("Item", 
        filters={"item_group": item_group},
        fields=["name"]
    )
   
    updated_items = []
    errors = []
    
    for item in items:
        try:
            item_doc = frappe.get_doc("Item", item.name)
            
            # Check if item has UOM conversions
            if not item_doc.uoms:
                continue
            
            # First pass: Find the old PACK conversion factor
            old_pack_conversion = None
            for uom_row in item_doc.uoms:
                if uom_row.uom in ["PACK", "Pack"]:
                    old_pack_conversion = uom_row.conversion_factor
                    break
            
            # If no PACK found or it's already 1, skip
            if not old_pack_conversion or old_pack_conversion == 1:
                continue
            
            conversion_updated = False
            
            # Second pass: Update conversions
            for uom_row in item_doc.uoms:
                if uom_row.uom in ["PACK", "Pack"]:
                    # Set PACK as base (1)
                    uom_row.conversion_factor = 1
                    conversion_updated = True
                    
                elif uom_row.uom in ["Unit","UNITS", "UNIT", "Nos", "NOS", "nos"]:
                    # Set to 1/old_pack_conversion
                    uom_row.conversion_factor = 1 / old_pack_conversion
                    conversion_updated = True
            
            if conversion_updated:
                item_doc.save()
                updated_items.append(item.name)
                
        except Exception as e:
            errors.append(f"{item.name}: {str(e)}")
            frappe.log_error(f"UOM Reversal Error for {item.name}", str(e))
    
    # Commit the transaction
    frappe.db.commit()
    
    # Send real-time notification
    frappe.publish_realtime(
        event='uom_reversal_complete',
        message={
            'item_group': item_group,
            'updated_count': len(updated_items),
            'error_count': len(errors)
        }
    )
    
    return {
        "success": True,
        "updated_count": len(updated_items),
        "updated_items": updated_items,
        "errors": errors
    }