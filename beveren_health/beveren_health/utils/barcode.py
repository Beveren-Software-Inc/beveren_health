# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import frappe
from frappe.utils.file_manager import save_file
import os
import re

# ERPNext Item Barcode allowed value (not "EAN13")
DEFAULT_BARCODE_TYPE = "EAN-13"

BARCODE_IMAGE_OPTIONS = {
	"format": "PNG",
	"write_text": True,
	"quiet_zone": 2.0,
	"module_width": 0.3,
	"module_height": 15.0,
	"font_size": 10,
	"text_distance": 5,
	"dpi": 300,
}


def sanitize_filename(filename):
	"""Remove special characters and replace spaces with underscores."""
	filename = re.sub(r"[^\w\s.-]", "", str(filename))
	return filename.replace(" ", "_")


def generate_barcode_image(barcode_value, barcode_type=DEFAULT_BARCODE_TYPE):
	"""Generate a barcode image for the given barcode value. Returns the file URL."""
	try:
		from barcode import EAN13, Code128, get_barcode_class
		from barcode.writer import ImageWriter
	except ImportError:
		frappe.throw("Please install barcode library: pip install python-barcode[images]")

	try:
		if barcode_type in ("EAN13", "EAN-13", "EAN"):
			barcode_class = EAN13
		elif barcode_type == "Code128":
			barcode_class = Code128
		else:
			barcode_class = get_barcode_class(barcode_type)
			if not barcode_class:
				frappe.throw(f"Unsupported barcode type: {barcode_type}")

		sanitized_filename = sanitize_filename(barcode_value)
		file_path = frappe.get_site_path(f"private/files/{sanitized_filename}.png")
		os.makedirs(os.path.dirname(file_path), exist_ok=True)

		barcode_instance = barcode_class(str(barcode_value), writer=ImageWriter())
		base_path = file_path.replace(".png", "")
		try:
			barcode_instance.save(base_path, options=BARCODE_IMAGE_OPTIONS)
		except TypeError:
			barcode_instance.save(
				base_path,
				options={
					"format": "PNG",
					"write_text": True,
					"quiet_zone": 2.0,
					"module_width": 0.3,
					"module_height": 15.0,
				},
			)

		with open(file_path, "rb") as f:
			file_doc = save_file(
				f"{sanitized_filename}.png",
				f.read(),
				"Item Barcode",
				barcode_value,
				is_private=1,
			)

		return file_doc.file_url

	except Exception as e:
		frappe.log_error(
			title="Barcode Generation Error",
			message=f"Error generating barcode for {barcode_value}: {str(e)}",
		)
		frappe.throw(f"Error generating barcode: {str(e)}")


def generate_ean13_barcode():
	"""Generate a new EAN-13 barcode number."""
	import random

	for _ in range(10):
		base_number = str(random.randint(100000000000, 999999999999))
		check_digit = calculate_ean13_check_digit(base_number)
		barcode = base_number + str(check_digit)
		if not frappe.db.exists("Item Barcode", {"barcode": barcode}):
			return barcode

	frappe.throw("Unable to generate unique EAN13 barcode after multiple attempts")


def calculate_ean13_check_digit(number):
	"""Calculate the check digit for EAN13 barcode."""
	total = 0
	for i, digit in enumerate(number):
		multiplier = 3 if i % 2 == 1 else 1
		total += int(digit) * multiplier
	return (10 - (total % 10)) % 10
