# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import frappe
from beveren_health.beveren_health.utils.barcode import generate_barcode_image


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
				barcode_type = barcode_row.barcode_type or "EAN13"
				
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
