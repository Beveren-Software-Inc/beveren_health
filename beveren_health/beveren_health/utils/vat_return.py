# Copyright (c) 2026, Beveren Software
"""ACC-113 / ACC-117 - Bahrain VAT return preparation.

ERPNext's stock VAT Audit Report is hard-wired to South Africa and the UAE VAT
201 report is UAE-only, so neither can be used here. This module builds the
return from the company's own invoices and tax rows, laid out in the box
structure the NBR return form uses.

Boxes follow the NBR VAT Return form:

  Sales
    1  Standard rated sales
    2  Sales to registered customers in other GCC states
    3  Zero rated domestic sales
    4  Exports
    5  Exempt sales
  Purchases
    6  Standard rated domestic purchases
    7  Imports subject to VAT paid at customs
    8  Imports subject to VAT accounted for through reverse charge
    9  Zero rated purchases
    10 Exempt purchases
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, getdate

STANDARD_RATE = 10.0


def _company_abbr(company: str) -> str:
	return frappe.db.get_value("Company", company, "abbr") or ""


def _vat_accounts(company: str) -> dict:
	"""Resolve the output / input VAT ledgers for the company."""
	accounts = frappe.get_all(
		"Account",
		filters={"company": company, "is_group": 0},
		fields=["name", "root_type"],
	)
	output = [a.name for a in accounts if "OUTPUT VAT" in a.name.upper()]
	inputs = [a.name for a in accounts if "INPUT VAT" in a.name.upper()]
	return {"output": output, "input": inputs}


def _invoice_rows(doctype: str, company: str, from_date, to_date) -> list[dict]:
	party = "customer" if doctype == "Sales Invoice" else "supplier"
	return frappe.db.sql(
		f"""
		SELECT inv.name, inv.posting_date, inv.{party} AS party,
		       inv.base_net_total, inv.base_grand_total, inv.taxes_and_charges,
		       inv.tax_category, inv.currency
		FROM `tab{doctype}` inv
		WHERE inv.docstatus = 1
		  AND inv.company = %(company)s
		  AND inv.posting_date BETWEEN %(from_date)s AND %(to_date)s
		""",
		{"company": company, "from_date": from_date, "to_date": to_date},
		as_dict=True,
	)


def _tax_amount(doctype: str, invoice: str, accounts: list[str]) -> float:
	if not accounts:
		return 0.0

	is_sales = doctype == "Sales Invoice"
	child = "Sales Taxes and Charges" if is_sales else "Purchase Taxes and Charges"
	# add_deduct_tax exists only on the purchase side; sales taxes are always additive.
	columns = "account_head, base_tax_amount" + ("" if is_sales else ", add_deduct_tax")

	rows = frappe.db.sql(
		f"SELECT {columns} FROM `tab{child}` WHERE parent = %s",
		(invoice,),
		as_dict=True,
	)

	total = 0.0
	for row in rows:
		if row.account_head not in accounts:
			continue
		amount = flt(row.base_tax_amount)
		if not is_sales and (row.get("add_deduct_tax") or "Add") == "Deduct":
			amount = -amount
		total += amount
	return total


def _classify(template: str | None, tax_category: str | None) -> str:
	name = (template or "").lower()
	category = (tax_category or "").lower()

	if "reverse" in name or "reverse" in category:
		return "reverse_charge"
	if "exempt" in name or "exempt" in category:
		return "exempt"
	if "zero" in name or "zero" in category:
		return "zero_rated"
	if "export" in name or "export" in category:
		return "export"
	return "standard"


@frappe.whitelist()
def get_vat_return(
	from_date: str, to_date: str, company: str | None = None
) -> dict:
	"""Compute the NBR VAT return for a period."""
	company = company or frappe.defaults.get_user_default("Company")
	from_date, to_date = getdate(from_date), getdate(to_date)
	accounts = _vat_accounts(company)

	boxes = {
		"standard_sales": {"amount": 0.0, "vat": 0.0},
		"gcc_sales": {"amount": 0.0, "vat": 0.0},
		"zero_rated_sales": {"amount": 0.0, "vat": 0.0},
		"exports": {"amount": 0.0, "vat": 0.0},
		"exempt_sales": {"amount": 0.0, "vat": 0.0},
		"standard_purchases": {"amount": 0.0, "vat": 0.0},
		"imports_customs": {"amount": 0.0, "vat": 0.0},
		"imports_reverse_charge": {"amount": 0.0, "vat": 0.0},
		"zero_rated_purchases": {"amount": 0.0, "vat": 0.0},
		"exempt_purchases": {"amount": 0.0, "vat": 0.0},
	}

	sales_map = {
		"standard": "standard_sales",
		"zero_rated": "zero_rated_sales",
		"export": "exports",
		"exempt": "exempt_sales",
		"reverse_charge": "standard_sales",
	}
	purchase_map = {
		"standard": "standard_purchases",
		"zero_rated": "zero_rated_purchases",
		"export": "zero_rated_purchases",
		"exempt": "exempt_purchases",
		"reverse_charge": "imports_reverse_charge",
	}

	for row in _invoice_rows("Sales Invoice", company, from_date, to_date):
		box = sales_map[_classify(row.taxes_and_charges, row.tax_category)]
		boxes[box]["amount"] += flt(row.base_net_total)
		boxes[box]["vat"] += _tax_amount("Sales Invoice", row.name, accounts["output"])

	for row in _invoice_rows("Purchase Invoice", company, from_date, to_date):
		box = purchase_map[_classify(row.taxes_and_charges, row.tax_category)]
		boxes[box]["amount"] += flt(row.base_net_total)
		boxes[box]["vat"] += _tax_amount("Purchase Invoice", row.name, accounts["input"])

	total_sales = sum(b["amount"] for k, b in boxes.items() if "sales" in k or k == "exports")
	output_vat = sum(b["vat"] for k, b in boxes.items() if "sales" in k or k == "exports")
	total_purchases = sum(
		b["amount"] for k, b in boxes.items() if "purchase" in k or "imports" in k
	)
	input_vat = sum(b["vat"] for k, b in boxes.items() if "purchase" in k or "imports" in k)

	return {
		"company": company,
		"from_date": str(from_date),
		"to_date": str(to_date),
		"currency": frappe.db.get_value("Company", company, "default_currency"),
		"boxes": boxes,
		"totals": {
			"total_sales": round(total_sales, 3),
			"output_vat": round(output_vat, 3),
			"total_purchases": round(total_purchases, 3),
			"input_vat": round(input_vat, 3),
			"net_vat_due": round(output_vat - input_vat, 3),
		},
		"note": _(
			"Prepared from submitted invoices. Review before filing with the NBR."
		),
	}


@frappe.whitelist()
def get_vat_return_lines(from_date: str, to_date: str, company: str | None = None) -> list[dict]:
	"""Flat, NBR-form-ordered rows - what you type into the return."""
	data = get_vat_return(from_date, to_date, company)
	b = data["boxes"]
	layout = [
		(1, _("Standard rated sales"), b["standard_sales"]),
		(2, _("Sales to registered customers in other GCC states"), b["gcc_sales"]),
		(3, _("Zero rated domestic sales"), b["zero_rated_sales"]),
		(4, _("Exports"), b["exports"]),
		(5, _("Exempt sales"), b["exempt_sales"]),
		(6, _("Standard rated domestic purchases"), b["standard_purchases"]),
		(7, _("Imports subject to VAT paid at customs"), b["imports_customs"]),
		(8, _("Imports subject to VAT accounted for through reverse charge"),
		 b["imports_reverse_charge"]),
		(9, _("Zero rated purchases"), b["zero_rated_purchases"]),
		(10, _("Exempt purchases"), b["exempt_purchases"]),
	]
	rows = [
		{
			"box": box,
			"description": label,
			"amount": round(values["amount"], 3),
			"vat": round(values["vat"], 3),
		}
		for box, label, values in layout
	]
	rows.append(
		{
			"box": "",
			"description": _("Net VAT due (output less input)"),
			"amount": "",
			"vat": data["totals"]["net_vat_due"],
		}
	)
	return rows
