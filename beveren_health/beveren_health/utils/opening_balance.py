# Copyright (c) 2026, Beveren Software
"""ACC-084..087 - opening balance migration.

The site went live without an opening-balance migration: the only opening GL
entries came from Stock Reconciliation, so GL accounts, customers, suppliers and
bank accounts all start from zero.

This module provides the import path:

  1. `get_template(kind)` - the column layout to fill in
  2. `validate_rows(kind, rows)` - dry-run check before anything is posted
  3. `create_opening_entry(kind, rows, posting_date)` - posts one Journal Entry
     of type "Opening Entry" against Temporary Opening

Nothing is posted until the data is supplied and validated, so this is safe to
install ahead of the figures.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import flt, getdate

TEMPLATES = {
	"gl": ["account", "debit", "credit", "cost_center", "remarks"],
	"customer": ["customer", "debit", "credit", "due_date", "remarks"],
	"supplier": ["supplier", "debit", "credit", "due_date", "remarks"],
	"bank": ["account", "debit", "credit", "remarks"],
}

PARTY_TYPE = {"customer": "Customer", "supplier": "Supplier"}


@frappe.whitelist()
def get_template(kind: str) -> dict:
	"""Column layout for an opening-balance import."""
	if kind not in TEMPLATES:
		frappe.throw(_("Unknown opening balance type {0}").format(kind))
	return {
		"kind": kind,
		"columns": TEMPLATES[kind],
		"note": _(
			"Enter one row per {0}. Use debit for balances the company owns or is owed, "
			"credit for balances it owes. Debits and credits must balance overall."
		).format(kind),
	}


def _temporary_opening(company: str) -> str:
	account = frappe.db.get_value(
		"Account",
		{"company": company, "account_type": "Temporary", "is_group": 0},
		"name",
	)
	if not account:
		frappe.throw(
			_("No Temporary account found for {0}. Create one (account type 'Temporary') "
			  "before importing opening balances.").format(company)
		)
	return account


def _as_rows(rows) -> list[dict]:
	if isinstance(rows, str):
		rows = json.loads(rows)
	return rows or []


@frappe.whitelist()
def validate_rows(kind: str, rows, company: str | None = None) -> dict:
	"""Dry run - report problems without posting anything."""
	company = company or frappe.defaults.get_user_default("Company")
	rows = _as_rows(rows)
	if kind not in TEMPLATES:
		frappe.throw(_("Unknown opening balance type {0}").format(kind))

	errors: list[str] = []
	total_debit = total_credit = 0.0

	for idx, row in enumerate(rows, start=1):
		debit, credit = flt(row.get("debit")), flt(row.get("credit"))
		total_debit += debit
		total_credit += credit

		if debit and credit:
			errors.append(_("Row {0}: set either debit or credit, not both.").format(idx))
		if not debit and not credit:
			errors.append(_("Row {0}: debit and credit are both zero.").format(idx))

		if kind in ("gl", "bank"):
			account = row.get("account")
			if not account:
				errors.append(_("Row {0}: account is required.").format(idx))
			elif not frappe.db.exists("Account", account):
				errors.append(_("Row {0}: account {1} does not exist.").format(idx, account))
			elif frappe.db.get_value("Account", account, "is_group"):
				errors.append(_("Row {0}: {1} is a group account.").format(idx, account))
		else:
			party_type = PARTY_TYPE[kind]
			party = row.get(kind)
			if not party:
				errors.append(_("Row {0}: {1} is required.").format(idx, kind))
			elif not frappe.db.exists(party_type, party):
				errors.append(
					_("Row {0}: {1} {2} does not exist.").format(idx, party_type, party)
				)

	difference = round(total_debit - total_credit, 2)
	if difference:
		errors.append(
			_("Total debit {0} does not equal total credit {1} (difference {2}).").format(
				round(total_debit, 2), round(total_credit, 2), difference
			)
		)

	return {
		"kind": kind,
		"row_count": len(rows),
		"total_debit": round(total_debit, 3),
		"total_credit": round(total_credit, 3),
		"difference": difference,
		"errors": errors,
		"ok": not errors,
	}


@frappe.whitelist()
def create_opening_entry(
	kind: str,
	rows,
	posting_date: str,
	company: str | None = None,
	submit: int = 0,
) -> dict:
	"""Post the opening balances as a single Opening Entry journal."""
	company = company or frappe.defaults.get_user_default("Company")
	rows = _as_rows(rows)

	check = validate_rows(kind, rows, company)
	if not check["ok"]:
		frappe.throw(
			_("Opening balances are not valid:<br>{0}").format("<br>".join(check["errors"]))
		)

	temporary = _temporary_opening(company)
	receivable = frappe.db.get_value("Company", company, "default_receivable_account")
	payable = frappe.db.get_value("Company", company, "default_payable_account")

	je = frappe.new_doc("Journal Entry")
	je.voucher_type = "Opening Entry"
	je.company = company
	je.posting_date = getdate(posting_date)
	je.is_opening = "Yes"
	je.user_remark = _("Opening balances - {0}").format(kind)

	balancing = 0.0
	for row in rows:
		debit, credit = flt(row.get("debit")), flt(row.get("credit"))
		line = {
			"debit_in_account_currency": debit,
			"credit_in_account_currency": credit,
			"cost_center": row.get("cost_center"),
			"user_remark": row.get("remarks"),
		}

		if kind in ("gl", "bank"):
			line["account"] = row.get("account")
		else:
			party_type = PARTY_TYPE[kind]
			line["account"] = receivable if kind == "customer" else payable
			line["party_type"] = party_type
			line["party"] = row.get(kind)
			if row.get("due_date"):
				line["due_date"] = getdate(row["due_date"])

		if not line["account"]:
			frappe.throw(
				_("No default {0} account set on the company.").format(
					"receivable" if kind == "customer" else "payable"
				)
			)

		je.append("accounts", line)
		balancing += credit - debit

	# Square the entry off against Temporary Opening.
	if round(balancing, 2):
		je.append(
			{
				"account": temporary,
				"debit_in_account_currency": balancing if balancing > 0 else 0,
				"credit_in_account_currency": -balancing if balancing < 0 else 0,
			}
		)

	je.insert(ignore_permissions=True)
	if int(submit or 0):
		je.submit()

	return {
		"journal_entry": je.name,
		"docstatus": je.docstatus,
		"rows": len(rows),
		"temporary_account": temporary,
	}


@frappe.whitelist()
def opening_balance_status(company: str | None = None) -> dict:
	"""Has an opening-balance migration been done yet?"""
	company = company or frappe.defaults.get_user_default("Company")

	opening_gl = frappe.db.count("GL Entry", {"company": company, "is_opening": "Yes"})
	opening_je = frappe.get_all(
		"Journal Entry",
		filters={"company": company, "is_opening": "Yes", "docstatus": 1},
		fields=["name", "posting_date", "voucher_type", "total_debit"],
	)

	return {
		"company": company,
		"opening_gl_entries": opening_gl,
		"opening_journal_entries": opening_je,
		"migrated": bool(opening_je),
	}
