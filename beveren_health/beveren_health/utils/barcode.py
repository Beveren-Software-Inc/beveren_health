# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import frappe
from frappe.utils.file_manager import save_file
import os
import re


def sanitize_filename(filename):
	"""
	Remove special characters and replace spaces with underscores.
	"""
	filename = re.sub(r'[^\w\s.-]', '', str(filename))
	filename = filename.replace(" ", "_")
	return filename


def generate_barcode_image(barcode_value, barcode_type="EAN13"):
	"""
	Generate a barcode image for the given barcode value.
	Returns the file URL for the saved image.
	"""
	try:
		# Import barcode library
		from barcode import EAN13, Code128, get_barcode_class
		from barcode.writer import ImageWriter
	except ImportError:
		frappe.throw(
			"Please install barcode library: pip install python-barcode[images]"
		)

	try:
		# Get barcode class based on type
		if barcode_type == "EAN13":
			barcode_class = EAN13
		elif barcode_type == "Code128":
			barcode_class = Code128
		else:
			# Try to get the barcode class dynamically
			barcode_class = get_barcode_class(barcode_type)
			if not barcode_class:
				frappe.throw(f"Unsupported barcode type: {barcode_type}")

		# Sanitize filename
		sanitized_filename = sanitize_filename(barcode_value)
		
		# Get site path for temporary file storage
		file_path = frappe.get_site_path(f"private/files/{sanitized_filename}.png")
		
		# Ensure directory exists
		dirname = os.path.dirname(file_path)
		os.makedirs(dirname, exist_ok=True)

		# Create barcode instance
		barcode_instance = barcode_class(str(barcode_value), writer=ImageWriter())
		
		# Save barcode image (remove .png extension as save() adds it)
		try:
			barcode_instance.save(file_path.replace(".png", ""), options={
				'format': 'PNG',
				'write_text': True,
				'quiet_zone': 2.0,
				'module_width': 0.3,
				'module_height': 15.0,
			})
		except Exception:
			# Fallback to default save if options are not supported
			barcode_instance.save(file_path.replace(".png", ""))

		# Read the saved file and save it using Frappe's file manager
		with open(file_path, "rb") as f:
			file_doc = save_file(
				f"{sanitized_filename}.png",
				f.read(),
				"Item Barcode",
				barcode_value,
				is_private=1
			)
		
		# Return the file URL
		return file_doc.file_url

	except Exception as e:
		frappe.log_error(
			title="Barcode Generation Error",
			message=f"Error generating barcode for {barcode_value}: {str(e)}"
		)
		frappe.throw(f"Error generating barcode: {str(e)}")


def generate_ean13_barcode():
	"""
	Generate a new EAN13 barcode number.
	Returns a 13-digit EAN13 barcode.
	"""
	import random

	# EAN13 structure: 1-3 digits (country code), 4-12 digits (manufacturer + product), 13th digit (check)
	# Use a random 12-digit number and calculate check digit
	# Try up to 10 times to find a unique barcode
	for _ in range(10):
		base_number = str(random.randint(100000000000, 999999999999))

		# Calculate EAN13 check digit
		check_digit = calculate_ean13_check_digit(base_number)
		barcode = base_number + str(check_digit)

		# Check if barcode already exists
		if not frappe.db.exists("Item Barcode", {"barcode": barcode}):
			return barcode

	# If all attempts failed, raise an error
	frappe.throw("Unable to generate unique EAN13 barcode after multiple attempts")


def calculate_ean13_check_digit(number):
	"""
	Calculate the check digit for EAN13 barcode.
	"""
	total = 0
	for i, digit in enumerate(number):
		multiplier = 3 if i % 2 == 1 else 1
		total += int(digit) * multiplier

	check_digit = (10 - (total % 10)) % 10
	return check_digit
