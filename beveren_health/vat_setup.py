from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from beveren_health.constants import VAT_CATEGORY_OPTIONS, BAHRAIN_VAT_CATEGORY_OPTIONS

M = "Beveren Health"

def ensure_nbr_vat_fields():
	fields = {
		"Company": [
			{"fieldname": "custom_vat_settings_tab", "label": "VAT Settings", "fieldtype": "Tab Break", "insert_after": "dashboard_tab", "module": M},
			{"fieldname": "custom_vat_accounts", "label": "VAT Accounts Configurations", "fieldtype": "Table", "options": "VAT Account Configuration", "insert_after": "custom_vat_settings_tab", "module": M},
		],
		"Address": [
			{"fieldname": "tax_id", "label": "VAT No.", "fieldtype": "Data", "insert_after": "tax_category", "module": M},
		],
		"Sales Invoice": [
			{"fieldname": "custom_vat_category", "label": "VAT Category", "fieldtype": "Select", "options": VAT_CATEGORY_OPTIONS, "insert_after": "customer_address", "module": M},
		],
		"Purchase Invoice": [
			{"fieldname": "custom_reverse_charge_applicable", "label": "Reverse Charge Applicable", "fieldtype": "Check", "default": 0, "insert_after": "apply_tds", "module": M},
			{"fieldname": "custom_vat_category", "label": "VAT Category", "fieldtype": "Select", "options": VAT_CATEGORY_OPTIONS, "insert_after": "supplier_address", "module": M},
		],
		"Item Tax Template": [
			{"fieldname": "custom_bahrain_vat_category", "label": "VAT Category", "fieldtype": "Select", "options": BAHRAIN_VAT_CATEGORY_OPTIONS, "insert_after": "title", "module": M},
		],
	}
	create_custom_fields(fields, update=True, ignore_validate=True)
