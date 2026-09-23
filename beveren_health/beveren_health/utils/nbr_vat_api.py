import json

import frappe
from frappe.utils import flt, today


@frappe.whitelist()
def get_vat_return_summary(company, from_date, to_date, tax_id=None):
	# Fetch sales and purchase invoice data
	sales_items = get_sales_items(company, from_date, to_date, tax_id)
	purchase_items = get_purchase_items(company, from_date, to_date, tax_id)

	# Build summary rows structure
	rows = {
		"1a": {"desc": "Standard Rated Sales at 10%", "amount": 0.0, "vat": 0.0, "count": 0},
		"1b": {"desc": "Standard Rated Sales at 5%", "amount": 0.0, "vat": 0.0, "count": 0},
		"2": {
			"desc": "Sales to Registered VAT Payers in Other GCC States",
			"amount": 0.0,
			"vat": 0.0,
			"count": 0,
		},
		"3": {
			"desc": "Sales Subject to Domestic Reverse Charge Mechanism",
			"amount": 0.0,
			"vat": 0.0,
			"count": 0,
		},
		"4": {"desc": "Zero-Rated Domestic Sales", "amount": 0.0, "vat": 0.0, "count": 0},
		"5": {"desc": "Exports", "amount": 0.0, "vat": 0.0, "count": 0},
		"6": {"desc": "Exempt Sales", "amount": 0.0, "vat": 0.0, "count": 0},
		"7": {"desc": "Total Sales", "amount": 0.0, "vat": 0.0, "count": 0},
		"8a": {"desc": "Standard Rated Domestic Purchases at 10%", "amount": 0.0, "vat": 0.0, "count": 0},
		"8b": {"desc": "Standard Rated Domestic Purchases at 5%", "amount": 0.0, "vat": 0.0, "count": 0},
		"9a": {
			"desc": "Imports Subject to VAT Paid at Customs at 10%",
			"amount": 0.0,
			"vat": 0.0,
			"count": 0,
		},
		"9b": {"desc": "Imports Subject to VAT Paid at Customs at 5%", "amount": 0.0, "vat": 0.0, "count": 0},
		"10": {"desc": "Imports Subject to Deferral at Customs", "amount": 0.0, "vat": 0.0, "count": 0},
		"11a": {
			"desc": "Imports Subject to VAT Accounted for Through Reverse Charge Mechanism at 10%",
			"amount": 0.0,
			"vat": 0.0,
			"count": 0,
		},
		"11b": {
			"desc": "Imports Subject to VAT Accounted for Through Reverse Charge Mechanism at 5%",
			"amount": 0.0,
			"vat": 0.0,
			"count": 0,
		},
		"12": {
			"desc": "Purchases Subject to Domestic Reverse Charge Mechanism",
			"amount": 0.0,
			"vat": 0.0,
			"count": 0,
		},
		"13": {
			"desc": "Purchases from Non-Registered Suppliers, Zero-Rated/Exempt Purchases",
			"amount": 0.0,
			"vat": 0.0,
			"count": 0,
		},
		"14": {"desc": "Total Purchases", "amount": 0.0, "vat": 0.0, "count": 0},
	}

	# Keep track of unique document names for each row
	row_docs = {k: set() for k in rows.keys()}

	# Populate sales rows
	for item in sales_items:
		row_id = classify_sales_item(item)
		if row_id and row_id in rows:
			rows[row_id]["amount"] += flt(item.base_net_amount)
			rows[row_id]["vat"] += flt(item.vat_amount)
			row_docs[row_id].add(item.parent)

	# Populate purchase rows
	for item in purchase_items:
		row_id = classify_purchase_item(item)
		if row_id and row_id in rows:
			rows[row_id]["amount"] += flt(item.base_net_amount)
			rows[row_id]["vat"] += flt(item.vat_amount)
			row_docs[row_id].add(item.parent)

			# If this is an RCM purchase, we also report the liability (Output VAT) on the Sales side!
			if item.get("custom_reverse_charge_applicable"):
				vat_cat = item.custom_bahrain_vat_category
				sales_row_id = "1b" if vat_cat == "Standard 5%" else "1a"

				rows[sales_row_id]["amount"] += flt(item.base_net_amount)
				rows[sales_row_id]["vat"] += flt(item.vat_amount)
				row_docs[sales_row_id].add(item.parent)

	# Set adjustments to 0.0 and compute counts
	for r_id in rows:
		rows[r_id]["adjustment"] = 0.0
		rows[r_id]["count"] = len(row_docs[r_id])

	# Sales Totals (Row 7)
	sales_rows = ["1a", "1b", "2", "3", "4", "5", "6"]
	rows["7"]["amount"] = sum(rows[r]["amount"] for r in sales_rows)
	rows["7"]["vat"] = sum(rows[r]["vat"] for r in sales_rows)

	total_sales_docs = set()
	for r in sales_rows:
		total_sales_docs.update(row_docs[r])
	rows["7"]["count"] = len(total_sales_docs)

	# Purchase Totals (Row 14)
	purchase_rows = ["8a", "8b", "9a", "9b", "10", "11a", "11b", "12", "13"]
	rows["14"]["amount"] = sum(rows[r]["amount"] for r in purchase_rows)
	rows["14"]["vat"] = sum(rows[r]["vat"] for r in purchase_rows)

	total_purch_docs = set()
	for r in purchase_rows:
		total_purch_docs.update(row_docs[r])
	rows["14"]["count"] = len(total_purch_docs)

	# Net VAT Calculations (Rows 15-18)
	row_15_vat = rows["7"]["vat"] - rows["14"]["vat"]
	row_18_vat = row_15_vat

	summary = {
		"rows": rows,
		"row_15_vat": row_15_vat,
		"row_16_correction_amount": 0.0,
		"row_17_credit_carried_forward": 0.0,
		"row_18_vat": row_18_vat,
		"unclassified_count": len(
			get_unclassified_sales_items(sales_items) + get_unclassified_purchase_items(purchase_items)
		),
	}
	return summary


@frappe.whitelist()
def get_category_breakup(row_id, company, from_date, to_date, tax_id=None):
	sales_items = get_sales_items(company, from_date, to_date, tax_id)
	purchase_items = get_purchase_items(company, from_date, to_date, tax_id)

	b2b_amount = 0.0
	b2b_vat = 0.0
	b2c_amount = 0.0
	b2c_vat = 0.0

	if row_id in ["1a", "1b", "2", "3", "4", "5", "6"]:
		for item in sales_items:
			if classify_sales_item(item) == row_id:
				is_b2b = item.vat_category in ["Registered (Domestic)", "GCC Registered"]
				if is_b2b:
					b2b_amount += flt(item.base_net_amount)
					b2b_vat += flt(item.vat_amount)
				else:
					b2c_amount += flt(item.base_net_amount)
					b2c_vat += flt(item.vat_amount)
		# Add RCM purchases to Row 1a / 1b
		if row_id in ["1a", "1b"]:
			for item in purchase_items:
				if item.get("custom_reverse_charge_applicable"):
					vat_cat = item.custom_bahrain_vat_category
					sales_row_id = "1b" if vat_cat == "Standard 5%" else "1a"
					if sales_row_id == row_id:
						is_b2b = item.vat_category in ["Registered (Domestic)", "GCC Registered"]
						if is_b2b:
							b2b_amount += flt(item.base_net_amount)
							b2b_vat += flt(item.vat_amount)
						else:
							b2c_amount += flt(item.base_net_amount)
							b2c_vat += flt(item.vat_amount)
	elif row_id in ["8a", "8b", "9a", "9b", "10", "11a", "11b", "12", "13"]:
		for item in purchase_items:
			if classify_purchase_item(item) == row_id:
				is_b2b = item.vat_category in ["Registered (Domestic)", "GCC Registered"]
				if is_b2b:
					b2b_amount += flt(item.base_net_amount)
					b2b_vat += flt(item.vat_amount)
				else:
					b2c_amount += flt(item.base_net_amount)
					b2c_vat += flt(item.vat_amount)

	return {"b2b_amount": b2b_amount, "b2b_vat": b2b_vat, "b2c_amount": b2c_amount, "b2c_vat": b2c_vat}


@frappe.whitelist()
def get_invoice_list(row_id, category, company, from_date, to_date, tax_id=None):
	sales_items = get_sales_items(company, from_date, to_date, tax_id)
	purchase_items = get_purchase_items(company, from_date, to_date, tax_id)

	invoices = {}

	# category is either 'B2B' or 'B2C'
	if row_id in ["1a", "1b", "2", "3", "4", "5", "6"]:
		for item in sales_items:
			if classify_sales_item(item) == row_id:
				is_b2b = item.vat_category in ["Registered (Domestic)", "GCC Registered"]
				match = (category == "B2B" and is_b2b) or (category == "B2C" and not is_b2b)
				if match:
					key = item.parent
					if key not in invoices:
						invoices[key] = {
							"invoice_no": item.parent,
							"party": item.customer_name or item.customer,
							"date": item.posting_date,
							"taxable_value": 0.0,
							"vat_amount": 0.0,
							"doctype": "Sales Invoice",
						}
					invoices[key]["taxable_value"] += flt(item.base_net_amount)
					invoices[key]["vat_amount"] += flt(item.vat_amount)
		# Add RCM purchases to Row 1a / 1b
		if row_id in ["1a", "1b"]:
			for item in purchase_items:
				if item.get("custom_reverse_charge_applicable"):
					vat_cat = item.custom_bahrain_vat_category
					sales_row_id = "1b" if vat_cat == "Standard 5%" else "1a"
					if sales_row_id == row_id:
						is_b2b = item.vat_category in ["Registered (Domestic)", "GCC Registered"]
						match = (category == "B2B" and is_b2b) or (category == "B2C" and not is_b2b)
						if match:
							key = item.parent
							if key not in invoices:
								invoices[key] = {
									"invoice_no": item.parent,
									"party": item.supplier_name or item.supplier,
									"date": item.posting_date,
									"taxable_value": 0.0,
									"vat_amount": 0.0,
									"doctype": "Purchase Invoice",
								}
							invoices[key]["taxable_value"] += flt(item.base_net_amount)
							invoices[key]["vat_amount"] += flt(item.vat_amount)
	elif row_id in ["8a", "8b", "9a", "9b", "10", "11a", "11b", "12", "13"]:
		for item in purchase_items:
			if classify_purchase_item(item) == row_id:
				is_b2b = item.vat_category in ["Registered (Domestic)", "GCC Registered"]
				match = (category == "B2B" and is_b2b) or (category == "B2C" and not is_b2b)
				if match:
					key = item.parent
					if key not in invoices:
						invoices[key] = {
							"invoice_no": item.parent,
							"party": item.supplier_name or item.supplier,
							"date": item.posting_date,
							"taxable_value": 0.0,
							"vat_amount": 0.0,
							"doctype": "Purchase Invoice",
						}
					invoices[key]["taxable_value"] += flt(item.base_net_amount)
					invoices[key]["vat_amount"] += flt(item.vat_amount)

	return list(invoices.values())


@frappe.whitelist()
def get_unclassified_items(company, from_date, to_date, tax_id=None):
	sales_items = get_sales_items(company, from_date, to_date, tax_id)
	purchase_items = get_purchase_items(company, from_date, to_date, tax_id)

	unclassified = []
	for item in sales_items:
		if not classify_sales_item(item):
			unclassified.append(
				{
					"document": item.parent,
					"item_code": item.item_code,
					"reason": "Unmapped supply type or missing Item Tax Template categorization",
					"doctype": "Sales Invoice",
				}
			)

	for item in purchase_items:
		if not classify_purchase_item(item):
			unclassified.append(
				{
					"document": item.parent,
					"item_code": item.item_code,
					"reason": "Unclassified purchase transaction parameters",
					"doctype": "Purchase Invoice",
				}
			)

	# GCC warning check: GCC customers marked registered but missing TRN
	gcc_warnings = frappe.db.sql(
		"""
		SELECT name, customer_name, tax_id as vat_registration_number
		FROM `tabCustomer`
		WHERE tax_category = 'GCC Registered'
		  AND (tax_id IS NULL OR tax_id = '')
	""",
		as_dict=True,
	)

	for w in gcc_warnings:
		unclassified.append(
			{
				"document": w.name,
				"item_code": "-",
				"reason": f"GCC customer '{w.customer_name}' is marked GCC Registered but lacks a VAT No. (Tax ID)",
				"doctype": "Customer",
			}
		)

	return unclassified


def get_sales_items(company, from_date, to_date, tax_id=None):
	vat_output = get_company_vat_accounts(company, "VAT Output")
	abbr = frappe.db.get_value("Company", company, "abbr") or "BS"
	if not vat_output:
		vat_output = [f"VAT Output - {abbr}"]

	query = """
		SELECT
			sii.parent, sii.name, sii.item_code, MAX(sii.base_net_amount) as base_net_amount,
			si.posting_date, si.customer, si.customer_name,
			si.custom_vat_category as vat_category,
			itt.custom_bahrain_vat_category,
			MAX(sii.base_net_amount) * IFNULL(MAX(ittd.tax_rate), 0) / 100 as vat_amount,
			addr.country
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON sii.parent = si.name
		LEFT JOIN `tabAddress` addr ON si.customer_address = addr.name
		LEFT JOIN `tabItem Tax Template` itt ON sii.item_tax_template = itt.name
		LEFT JOIN `tabItem Tax Template Detail` ittd ON ittd.parent = itt.name AND ittd.tax_type IN %(vat_output)s

		LEFT JOIN `tabAddress` comp_addr ON si.company_address = comp_addr.name
		WHERE si.company = %(company)s
		  AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
		  AND si.docstatus = 1
	"""
	params = {"company": company, "from_date": from_date, "to_date": to_date, "vat_output": vat_output}
	if tax_id:
		query += " AND (comp_addr.tax_id = %(tax_id)s OR (si.company_address IS NULL AND (SELECT tax_id FROM `tabCompany` WHERE name = si.company) = %(tax_id)s))"
		params["tax_id"] = tax_id

	query += " GROUP BY sii.name"
	return frappe.db.sql(query, params, as_dict=True)


def get_purchase_items(company, from_date, to_date, tax_id=None):
	rcm_input = get_company_vat_accounts(company, "RCM Input")
	rcm_output = get_company_vat_accounts(company, "RCM Output")
	vat_input = get_company_vat_accounts(company, "VAT Input")
	vat_output = get_company_vat_accounts(company, "VAT Output")

	abbr = frappe.db.get_value("Company", company, "abbr") or "BS"

	if not rcm_input:
		rcm_input = [f"VAT Input RCM - {abbr}"]
	if not rcm_output:
		rcm_output = [f"VAT Output RCM - {abbr}"]
	if not vat_input:
		vat_input = [f"VAT Input - {abbr}"]
	if not vat_output:
		vat_output = [f"VAT Output - {abbr}"]

	query = """
		SELECT
			pii.parent, pii.name, pii.item_code, MAX(pii.base_net_amount) as base_net_amount,
			pi.posting_date, pi.supplier, pi.supplier_name,
			pi.custom_vat_category as vat_category, pi.custom_reverse_charge_applicable,
			itt.custom_bahrain_vat_category,
			SUM(CASE
				WHEN pi.custom_reverse_charge_applicable = 1 AND pt.account_head IN %(rcm_input)s THEN iwtd.amount
				WHEN pi.custom_reverse_charge_applicable = 0 AND pt.account_head IN %(vat_input)s THEN iwtd.amount
				ELSE 0
			END) as vat_amount,
			SUM(CASE
				WHEN pi.custom_reverse_charge_applicable = 1 AND pt.account_head IN %(rcm_output)s THEN iwtd.amount
				WHEN pi.custom_reverse_charge_applicable = 0 AND pt.account_head IN %(vat_output)s THEN iwtd.amount
				ELSE 0
			END) as output_vat_amount,
			addr.country
		FROM `tabPurchase Invoice Item` pii
		INNER JOIN `tabPurchase Invoice` pi ON pii.parent = pi.name
		LEFT JOIN `tabAddress` addr ON pi.supplier_address = addr.name
		LEFT JOIN `tabItem Tax Template` itt ON pii.item_tax_template = itt.name
		LEFT JOIN `tabItem Wise Tax Detail` iwtd ON iwtd.parent = pi.name AND iwtd.item_row = pii.name
		LEFT JOIN `tabPurchase Taxes and Charges` pt ON iwtd.tax_row = pt.name
		LEFT JOIN `tabAddress` comp_addr ON pi.billing_address = comp_addr.name
		WHERE pi.company = %(company)s
		  AND pi.posting_date BETWEEN %(from_date)s AND %(to_date)s
		  AND pi.docstatus = 1
	"""
	params = {
		"company": company,
		"from_date": from_date,
		"to_date": to_date,
		"rcm_input": rcm_input,
		"rcm_output": rcm_output,
		"vat_input": vat_input,
		"vat_output": vat_output,
	}
	if tax_id:
		query += " AND (comp_addr.tax_id = %(tax_id)s OR (pi.billing_address IS NULL AND (SELECT tax_id FROM `tabCompany` WHERE name = pi.company) = %(tax_id)s))"
		params["tax_id"] = tax_id

	query += " GROUP BY pii.name"
	return frappe.db.sql(query, params, as_dict=True)


# Categorization Logic
def classify_sales_item(item):
	# Derive supply type from country
	country = item.get("country") or "Bahrain"
	if country == "Bahrain":
		supply_type = "Domestic"
	elif country in ["Saudi Arabia", "United Arab Emirates", "Oman", "Qatar", "Kuwait"]:
		supply_type = "GCC"
	else:
		supply_type = "Export"

	vat_cat = item.custom_bahrain_vat_category

	# Row 6: Exempt sales
	if vat_cat == "Exempt":
		return "6"

	# Row 5: Exports
	if supply_type == "Export":
		return "5"

	# Row 2: Sales to registered VAT payers in other GCC states
	if supply_type == "GCC" and item.vat_category == "GCC Registered":
		return "2"

	# Row 4: Zero rated domestic sales
	if vat_cat == "Zero-Rated" and supply_type == "Domestic":
		return "4"
	if supply_type == "GCC" and item.vat_category == "GCC Unregistered":
		return "4"

	# Row 3: Sales subject to domestic reverse charge mechanism
	if item.get("custom_reverse_charge_applicable") and supply_type == "Domestic":
		return "3"

	# Row 1(a) & 1(b): Standard rated sales
	if supply_type == "Domestic":
		if vat_cat == "Standard 10%":
			return "1a"
		elif vat_cat == "Standard 5%":
			return "1b"

	return None


def classify_purchase_item(item):
	# Derive supply type from country
	country = item.get("country") or "Bahrain"
	if country == "Bahrain":
		supply_type = "Domestic"
	elif country in ["Saudi Arabia", "United Arab Emirates", "Oman", "Qatar", "Kuwait"]:
		supply_type = "GCC"
	else:
		supply_type = "Import"

	vat_cat = item.custom_bahrain_vat_category

	# Row 12 & 11: Reverse charge mechanism
	if item.get("custom_reverse_charge_applicable"):
		if supply_type == "Domestic":
			return "12"
		else:
			rate = 10
			if vat_cat == "Standard 5%":
				rate = 5
			return "11a" if rate == 10 else "11b"

	# Standard rated imports (VAT paid at customs)
	if supply_type == "Import":
		if vat_cat == "Standard 10%":
			return "9a"
		elif vat_cat == "Standard 5%":
			return "9b"
		elif vat_cat in ["Zero-Rated", "Exempt"]:
			return "13"

	# Row 13: Purchases from non-registered / zero-rated / exempt
	if item.vat_category in ["Unregistered (Domestic)", "GCC Unregistered"] or vat_cat in [
		"Zero-Rated",
		"Exempt",
	]:
		return "13"

	# Row 8(a) & 8(b): Standard rated domestic purchases
	if supply_type == "Domestic":
		if vat_cat == "Standard 10%":
			return "8a"
		elif vat_cat == "Standard 5%":
			return "8b"

	return None


def get_unclassified_sales_items(sales_items):
	return [item for item in sales_items if not classify_sales_item(item)]


def get_unclassified_purchase_items(purchase_items):
	return [item for item in purchase_items if not classify_purchase_item(item)]


@frappe.whitelist()
def get_all_contributing_invoices(company, from_date, to_date, tax_id=None):
	sales_items = get_sales_items(company, from_date, to_date, tax_id)
	purchase_items = get_purchase_items(company, from_date, to_date, tax_id)

	invoices = {}

	# Sales Invoice items
	for item in sales_items:
		row_id = classify_sales_item(item)
		if row_id:
			key = ("Sales Invoice", item.parent)
			if key not in invoices:
				invoices[key] = {
					"invoice_no": item.parent,
					"doctype": "Sales Invoice",
					"party": item.customer_name or item.customer,
					"date": item.posting_date,
					"taxable_value": 0.0,
					"vat_amount": 0.0,
					"box": row_id,
				}
			invoices[key]["taxable_value"] += flt(item.base_net_amount)
			invoices[key]["vat_amount"] += flt(item.vat_amount)

	# Purchase Invoice items
	for item in purchase_items:
		row_id = classify_purchase_item(item)
		if row_id:
			key = ("Purchase Invoice", item.parent)
			if key not in invoices:
				invoices[key] = {
					"invoice_no": item.parent,
					"doctype": "Purchase Invoice",
					"party": item.supplier_name or item.supplier,
					"date": item.posting_date,
					"taxable_value": 0.0,
					"vat_amount": 0.0,
					"box": row_id,
				}
			invoices[key]["taxable_value"] += flt(item.base_net_amount)
			invoices[key]["vat_amount"] += flt(item.vat_amount)

	return sorted(list(invoices.values()), key=lambda x: x["date"])


@frappe.whitelist()
def download_vat_excel(company, from_date, to_date, tax_id=None):
	summary = get_vat_return_summary(company, from_date, to_date, tax_id)
	rows = summary["rows"]

	from io import BytesIO

	import openpyxl
	from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

	wb = openpyxl.Workbook()
	ws = wb.active
	ws.title = "VAT Return Form NBR"

	# Make grid lines visible
	ws.views.sheetView[0].showGridLines = True

	# Title Block
	ws.merge_cells("A1:D1")
	ws["A1"] = "VAT Return Form NBR"
	ws["A1"].font = Font(name="Calibri", size=16, bold=True)
	ws["A1"].alignment = Alignment(horizontal="center", vertical="center")

	ws.merge_cells("A2:D2")
	ws["A2"] = f"For the period from {from_date} to {to_date}"
	ws["A2"].font = Font(name="Calibri", size=11, italic=True)
	ws["A2"].alignment = Alignment(horizontal="center", vertical="center")

	ws.row_dimensions[1].height = 30
	ws.row_dimensions[2].height = 20

	# Headers (Row 4 and 5)
	ws.merge_cells("A4:A5")
	ws["A4"] = "Description"

	ws.merge_cells("B4:B5")
	ws["B4"] = "Amount"

	ws.merge_cells("C4:C5")
	ws["C4"] = "Adjustment/\nApportionment"

	ws.merge_cells("D4:D5")
	ws["D4"] = "VAT Amount"

	header_fill = PatternFill(start_color="E5E7EB", end_color="E5E7EB", fill_type="solid")
	header_font = Font(name="Calibri", size=11, bold=True)
	center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

	thin_border = Border(
		left=Side(style="thin", color="B0B0B0"),
		right=Side(style="thin", color="B0B0B0"),
		top=Side(style="thin", color="B0B0B0"),
		bottom=Side(style="thin", color="B0B0B0"),
	)

	# Apply styling to header block
	for r in range(4, 6):
		for c in range(1, 5):
			cell = ws.cell(row=r, column=c)
			cell.font = header_font
			cell.fill = header_fill
			cell.alignment = center_align
			cell.border = thin_border

	ws.row_dimensions[4].height = 20
	ws.row_dimensions[5].height = 20

	row_configs = [
		("Section", None, "VAT on Sales", True, True),
		("Data", "1a", "1(a). Standard rated sales at 10%", False, False),
		("Data", "1b", "1(b). Standard rated sales at 5%", False, False),
		("Data", "2", "2. Sales to registered VAT payers in other GCC states", False, False),
		("Data", "3", "3. Sales subject to domestic reverse charge mechanism", False, False),
		("Data", "4", "4. Zero rated domestic sales", False, False),
		("Data", "5", "5. Exports", False, False),
		("Data", "6", "6. Exempt sales", False, False),
		("Total", "7", "7. Total sales", True, False),
		("Section", None, "VAT on Purchases", True, True),
		("Data", "8a", "8(a). Standard rated domestic purchases at 10%", False, False),
		("Data", "8b", "8(b). Standard rated domestic purchases at 5%", False, False),
		("Data", "9a", "9(a). Imports subject to VAT paid at customs at 10%", False, False),
		("Data", "9b", "9(b). Imports subject to VAT paid at customs at 5%", False, False),
		("Data", "10", "10. Imports subject to deferral at customs", False, False),
		(
			"Data",
			"11a",
			"11(a). Imports subject to VAT accounted for through reverse charge mechanism at 10%",
			False,
			False,
		),
		(
			"Data",
			"11b",
			"11(b). Imports subject to VAT accounted for through reverse charge mechanism at 5%",
			False,
			False,
		),
		("Data", "12", "12. Purchases subject to domestic reverse charge mechanism", False, False),
		(
			"Data",
			"13",
			"13. Purchases from non-registered suppliers, zero rated/exempt purchases",
			False,
			False,
		),
		("Total", "14", "14. Total purchases", True, False),
		("Section", None, "Net VAT Due", True, True),
		("NetData", "15", "15. Total VAT due for current period", False, False),
		("NetData", "16", "16. Corrections from previous period (between BHD \u00b15,000)", False, False),
		("NetData", "17", "17. VAT credit carried forward from previous period(s)", False, False),
		("NetData", "18", "18. Net VAT due (or reclaimed)", True, True),
	]

	current_row = 6
	for row_type, key, label, is_bold, has_fill in row_configs:
		if row_type == "Section":
			ws.cell(row=current_row, column=1, value=label)
			ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=4)

			section_fill = PatternFill(start_color="D1D5DB", end_color="D1D5DB", fill_type="solid")
			section_font = Font(name="Calibri", size=11, bold=True)

			for c in range(1, 5):
				cell = ws.cell(row=current_row, column=c)
				cell.fill = section_fill
				cell.font = section_font
				cell.border = thin_border
			ws.row_dimensions[current_row].height = 24

		elif row_type in ("Data", "Total"):
			r_data = rows[key]
			ws.cell(row=current_row, column=1, value=label)
			ws.cell(row=current_row, column=2, value=flt(r_data.get("amount", 0.0)))
			ws.cell(row=current_row, column=3, value=flt(r_data.get("adjustment", 0.0)))
			ws.cell(row=current_row, column=4, value=flt(r_data.get("vat", 0.0)))

			cell_font = Font(name="Calibri", size=11, bold=is_bold)
			ws.cell(row=current_row, column=1).alignment = Alignment(horizontal="left", vertical="center")
			ws.cell(row=current_row, column=1).font = cell_font
			ws.cell(row=current_row, column=1).border = thin_border

			for c in range(2, 5):
				cell = ws.cell(row=current_row, column=c)
				cell.font = cell_font
				cell.border = thin_border
				cell.number_format = "#,##0.000"
				cell.alignment = Alignment(horizontal="right", vertical="center")

			ws.row_dimensions[current_row].height = 20

		elif row_type == "NetData":
			ws.cell(row=current_row, column=1, value=label)
			ws.cell(row=current_row, column=2, value="")
			ws.cell(row=current_row, column=3, value="")

			val = 0.0
			if key == "15":
				val = flt(summary["row_15_vat"])
			elif key == "16":
				val = flt(summary["row_16_correction_amount"])
			elif key == "17":
				val = flt(summary["row_17_credit_carried_forward"])
			elif key == "18":
				val = flt(summary["row_18_vat"])

			ws.cell(row=current_row, column=4, value=val)

			cell_font = Font(name="Calibri", size=11, bold=is_bold)
			ws.cell(row=current_row, column=1).alignment = Alignment(horizontal="left", vertical="center")
			ws.cell(row=current_row, column=1).font = cell_font
			ws.cell(row=current_row, column=1).border = thin_border

			for c in range(2, 5):
				cell = ws.cell(row=current_row, column=c)
				cell.font = cell_font
				cell.border = thin_border
				if c == 4:
					cell.number_format = "#,##0.000"
					cell.alignment = Alignment(horizontal="right", vertical="center")
				else:
					cell.alignment = Alignment(horizontal="center", vertical="center")

			if has_fill:
				net_fill = PatternFill(start_color="EBF8FF", end_color="EBF8FF", fill_type="solid")
				for c in range(1, 5):
					ws.cell(row=current_row, column=c).fill = net_fill

			ws.row_dimensions[current_row].height = 20

		current_row += 1

	# Auto-adjust column widths
	ws.column_dimensions["A"].width = 85
	ws.column_dimensions["B"].width = 20
	ws.column_dimensions["C"].width = 25
	ws.column_dimensions["D"].width = 20

	out_buf = BytesIO()
	wb.save(out_buf)
	out_buf.seek(0)

	# Return xlsx download response
	frappe.response["filename"] = f"Bahrain_VAT_Return_{company}_{from_date}_to_{to_date}.xlsx"
	frappe.response["filecontent"] = out_buf.getvalue()
	frappe.response["type"] = "download"


@frappe.whitelist()
def get_company_vat_number(company):
	# 1. Search for Address linked to the Company
	addr_name = frappe.db.get_value(
		"Dynamic Link", {"parenttype": "Address", "link_doctype": "Company", "link_name": company}, "parent"
	)
	if addr_name:
		tax_id = frappe.db.get_value("Address", addr_name, "tax_id")
		if tax_id:
			return tax_id

	# 2. Fallback to Company's tax_id field
	return frappe.db.get_value("Company", company, "tax_id") or ""


@frappe.whitelist()
def get_company_vat_numbers(company):
	# Get all unique tax_ids from Address linked to this Company
	addresses = frappe.db.sql(
		"""
		SELECT DISTINCT addr.tax_id FROM `tabAddress` addr
		INNER JOIN `tabDynamic Link` link ON link.parent = addr.name
		WHERE link.link_doctype = 'Company' AND link.link_name = %s
		  AND addr.tax_id IS NOT NULL AND addr.tax_id != ''
	""",
		(company,),
		as_dict=True,
	)

	vat_numbers = [a.tax_id for a in addresses]

	# Also add Company's own tax_id if not already in the list
	comp_tax_id = frappe.db.get_value("Company", company, "tax_id")
	if comp_tax_id and comp_tax_id not in vat_numbers:
		vat_numbers.append(comp_tax_id)

	return vat_numbers


def get_company_vat_accounts(company, vat_type):
	accounts = frappe.get_all(
		"VAT Account Configuration",
		filters={"parent": company, "parenttype": "Company", "vat_type": vat_type},
		pluck="vat_account",
	)
	return [a for a in accounts if a]
