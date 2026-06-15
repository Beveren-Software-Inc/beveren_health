# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import frappe
from beveren_health.beveren_health.utils.barcode import (
	DEFAULT_BARCODE_TYPE,
	generate_barcode_image,
	generate_ean13_barcode,
)


@frappe.whitelist()
def generate_barcode_for_item(item_code):
	"""
	Generate EAN13 barcode and image for a single item.
	- If item has barcode but no image → generate image for existing barcode
	- If item has no barcode → generate barcode AND image
	- If item has barcode with image → skip (return message)
	"""
	if not item_code:
		frappe.throw("Item Code is required")

	item_doc = frappe.get_doc("Item", item_code)
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
		return {"success": True, "message": "Item already has a barcode with image."}

	if has_barcode_without_image:
		try:
			barcode_type = barcode_row_to_update.barcode_type or DEFAULT_BARCODE_TYPE
			image_path = generate_barcode_image(barcode_row_to_update.barcode, barcode_type)
			barcode_row_to_update.custom_image = image_path
			item_doc.save(ignore_permissions=True)
			return {"success": True, "message": "Generated barcode image for existing barcode."}
		except Exception as e:
			frappe.log_error(
				title="Barcode Image Generation Error",
				message=f"Error generating barcode image (item {item_code}): {str(e)}",
			)
			frappe.throw(str(e))

	new_barcode = generate_ean13_barcode()
	if frappe.db.exists("Item Barcode", {"barcode": new_barcode}):
		new_barcode = generate_ean13_barcode()
		if frappe.db.exists("Item Barcode", {"barcode": new_barcode}):
			frappe.throw("Could not generate a unique barcode. Please try again.")

	item_doc.append("barcodes", {"barcode": new_barcode, "barcode_type": DEFAULT_BARCODE_TYPE})
	try:
		image_path = generate_barcode_image(new_barcode, DEFAULT_BARCODE_TYPE)
		item_doc.barcodes[-1].custom_image = image_path
		item_doc.save(ignore_permissions=True)
		return {"success": True, "message": "Generated barcode and image."}
	except Exception as e:
		frappe.log_error(
			title="Barcode Image Generation Error",
			message=f"Error generating barcode image (item {item_code}): {str(e)}",
		)
		frappe.throw(str(e))
