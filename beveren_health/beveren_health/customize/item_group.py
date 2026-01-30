# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import frappe
from beveren_health.beveren_health.utils.barcode import (
	generate_barcode_image,
	generate_ean13_barcode,
)


@frappe.whitelist()
def generate_barcodes_for_item_group(item_group):
	"""
	Generate EAN13 barcodes and images for all items in the given item group.
	- If item has barcode but no image → generate image for existing barcode
	- If item has no barcode → generate barcode AND image
	- If item has barcode with image → skip
	"""
	try:
		# Get all items in this group
		items = frappe.get_all(
			"Item",
			filters={"item_group": item_group, "disabled": 0},
			fields=["name", "item_code", "item_name"]
		)

		if not items:
			frappe.msgprint(f"No active items found in group {item_group}")
			return

		generated_barcodes = 0
		generated_images = 0
		skipped_count = 0

		for item in items:
			item_doc = frappe.get_doc("Item", item.name)
			item_updated = False
			
			# Check if item has barcodes
			has_barcode_with_image = False
			has_barcode_without_image = False
			barcode_row_to_update = None
			
			if item_doc.barcodes:
				for barcode_row in item_doc.barcodes:
					if barcode_row.barcode:
						if barcode_row.custom_image:
							# Item has barcode with image - skip
							has_barcode_with_image = True
							break
						else:
							# Item has barcode but no image - generate image
							has_barcode_without_image = True
							barcode_row_to_update = barcode_row
							break

			if has_barcode_with_image:
				# Item already has barcode with image - skip
				skipped_count += 1
				continue

			if has_barcode_without_image:
				# Item has barcode but no image - generate image
				try:
					barcode_type = barcode_row_to_update.barcode_type or "EAN13"
					image_path = generate_barcode_image(barcode_row_to_update.barcode, barcode_type)
					barcode_row_to_update.custom_image = image_path
					item_updated = True
					generated_images += 1
				except Exception as e:
					frappe.log_error(
						title="Barcode Image Generation Error",
						message=f"Error generating barcode image for {barcode_row_to_update.barcode} (item {item.item_code}): {str(e)}"
					)
			else:
				# Item has no barcode - generate barcode and image
				# Generate new EAN13 barcode
				new_barcode = generate_ean13_barcode()
				
				# Check if barcode already exists
				existing = frappe.db.exists("Item Barcode", {"barcode": new_barcode})
				if existing:
					# Try again with a new barcode
					new_barcode = generate_ean13_barcode()
					existing = frappe.db.exists("Item Barcode", {"barcode": new_barcode})
					if existing:
						frappe.log_error(
							title="Barcode Conflict",
							message=f"Barcode {new_barcode} already exists for item {item.item_code}"
						)
						continue

				# Add barcode to item
				item_doc.append("barcodes", {
					"barcode": new_barcode,
					"barcode_type": "EAN13"
				})

				# Generate barcode image
				try:
					image_path = generate_barcode_image(new_barcode, "EAN13")
					item_doc.barcodes[-1].custom_image = image_path
					item_updated = True
					generated_barcodes += 1
					generated_images += 1
				except Exception as e:
					frappe.log_error(
						title="Barcode Image Generation Error",
						message=f"Error generating barcode image for {new_barcode} (item {item.item_code}): {str(e)}"
					)

			# Save item if updated
			if item_updated:
				item_doc.save(ignore_permissions=True)

		# Prepare message
		message_parts = []
		if generated_barcodes > 0:
			message_parts.append(f"Generated {generated_barcodes} new barcodes")
		if generated_images > 0:
			message_parts.append(f"Generated {generated_images} barcode images")
		if skipped_count > 0:
			message_parts.append(f"Skipped {skipped_count} items that already have barcodes with images")
		
		message = ". ".join(message_parts) if message_parts else "No changes made."
		
		frappe.msgprint(
			message,
			indicator="green",
			alert=True
		)

	except Exception as e:
		frappe.log_error(
			title="Barcode Generation Error",
			message=f"Error generating barcodes for item group {item_group}: {str(e)}"
		)
		frappe.throw(f"Error generating barcodes: {str(e)}")
