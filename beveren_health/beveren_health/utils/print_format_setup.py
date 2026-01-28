# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import frappe


def create_medication_label_print_format():
	"""
	Create the Medication Label print format for Purchase Receipt.
	"""
	if frappe.db.exists("Print Format", "Medication Label"):
		return

	print_format = frappe.get_doc({
		"doctype": "Print Format",
		"name": "Medication Label",
		"print_format_type": "Jinja",
		"standard": "No",
		"doc_type": "Purchase Receipt",
		"html": """
{%- set item_row = None -%}
{%- set item_row_name = None -%}
{%- if frappe.form_dict and frappe.form_dict.item_row_name -%}
	{%- set item_row_name = frappe.form_dict.item_row_name -%}
{%- elif frappe.request and frappe.request.args and frappe.request.args.get("item_row_name") -%}
	{%- set item_row_name = frappe.request.args.get("item_row_name") -%}
{%- endif -%}
{%- if item_row_name -%}
	{%- for row in doc.items -%}
		{%- if row.name == item_row_name -%}
			{%- set item_row = row -%}
		{%- endif -%}
	{%- endfor -%}
{%- elif doc.items -%}
	{%- set item_row = doc.items[0] -%}
{%- endif -%}

{%- if item_row -%}
	{%- set item_code = item_row.item_code -%}
	{%- set item_doc = frappe.get_doc("Item", item_code) -%}
	{%- set barcode_image = None -%}
	{%- set barcode_value = None -%}
	{%- if item_doc.barcodes -%}
		{%- for barcode_row in item_doc.barcodes -%}
			{%- if barcode_row.custom_image -%}
				{%- set barcode_image = barcode_row.custom_image -%}
				{%- set barcode_value = barcode_row.barcode -%}
			{%- endif -%}
		{%- endfor -%}
	{%- endif -%}
	{%- set batch_expiry = None -%}
	{%- if item_row.batch_no -%}
		{%- set batch_doc = frappe.get_doc("Batch", item_row.batch_no) -%}
		{%- set batch_expiry = batch_doc.expiry_date -%}
	{%- endif -%}

<div class="medication-label" style="width: 2.299in; height: 1.5in; border: 1px solid #000; padding: 5px; font-family: Arial, sans-serif; box-sizing: border-box; overflow: hidden;">
	<div style="text-align: center; margin-bottom: 5px;">
		{% if barcode_image %}
		<img src="{{ barcode_image }}" alt="Barcode" style="max-width: 100%; height: 35px; margin-bottom: 2px; image-rendering: crisp-edges;">
		<div style="font-size: 8px; margin-top: -2px; font-family: monospace;">{{ barcode_value }}</div>
		{% endif %}
	</div>
	
	<div style="border-top: 1px solid #ccc; padding-top: 4px; margin-top: 4px;">
		<div style="font-weight: bold; font-size: 10px; margin-bottom: 2px; text-align: center; line-height: 1.1;">{{ item_row.item_name or item_code }}</div>
		<div style="font-size: 8px; margin-bottom: 1px; line-height: 1.1;">
			<span><strong>Strength:</strong> {{ item_doc.custom_strength or "N/A" }}</span>
		</div>
		<div style="font-size: 8px; margin-bottom: 1px; line-height: 1.1;">
			<span><strong>Form:</strong> {{ item_doc.custom_pharmaceutical_form or "N/A" }}</span>
		</div>
		<div style="font-size: 8px; margin-bottom: 1px; line-height: 1.1;">
			<span><strong>Price:</strong> {{ frappe.format(item_row.rate or item_doc.standard_rate or 0, {"fieldtype": "Currency"}) }}</span>
		</div>
		<div style="font-size: 8px; margin-bottom: 1px; line-height: 1.1;">
			<span><strong>Batch:</strong> {{ item_row.batch_no or "N/A" }}</span>
		</div>
		<div style="font-size: 8px; line-height: 1.1;">
			<span><strong>Expiry:</strong> {{ frappe.format(batch_expiry, {"fieldtype": "Date"}) if batch_expiry else "N/A" }}</span>
		</div>
	</div>
</div>
{% else %}
<div>No item selected for printing</div>
{% endif %}
		""",
		"css": """
.medication-label {
	page-break-inside: avoid;
	display: inline-block;
}
@page {
	size: 2.299in 1.5in;
	margin: 0;
}
		""",
		"disabled": 0
	})

	print_format.insert(ignore_permissions=True)
	frappe.db.commit()

	return print_format


@frappe.whitelist()
def setup_print_format():
	"""
	Setup function to create the print format.
	Can be called manually if needed.
	"""
	try:
		create_medication_label_print_format()
		frappe.msgprint("Medication Label print format created successfully")
	except Exception as e:
		frappe.log_error(
			title="Print Format Setup Error",
			message=f"Error creating print format: {str(e)}"
		)
		frappe.throw(f"Error creating print format: {str(e)}")
