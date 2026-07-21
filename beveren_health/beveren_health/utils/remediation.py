# Copyright (c) 2026, Beveren Software
"""Prepared remediations for the Serene BRD sign-off items.

Every function runs in DRY-RUN by default: it reports exactly what it would
change and changes nothing. Pass ``apply=True`` to execute, once the change has
been signed off.

    from beveren_health.beveren_health.utils import remediation
    remediation.run_all()                 # dry run, safe
    remediation.fix_receivable_account(apply=True)

These cover the items on the 'Needs Sign-Off' sheet of the UAT workbook. They
are deliberately NOT wired to any hook or scheduler.
"""

from __future__ import annotations

import frappe
from frappe.utils import cint, flt

COMPANY = "Serene Psychiatry Hospital"


def _result(name: str, apply: bool, changes: list[str], blockers: list[str] | None = None) -> dict:
	return {
		"item": name,
		"mode": "APPLIED" if apply else "dry-run",
		"change_count": len(changes),
		"changes": changes,
		"blockers": blockers or [],
	}


# --------------------------------------------------------------------------- #
# ACC-016 - default receivable account points at a stock ledger
# --------------------------------------------------------------------------- #
def fix_receivable_account(apply: bool = False) -> dict:
	changes, blockers = [], []
	current = frappe.db.get_value("Company", COMPANY, "default_receivable_account")

	target = frappe.db.get_value(
		"Account",
		{"company": COMPANY, "is_group": 0, "name": ["like", "%PATIENT RECEIVABLE%"]},
		"name",
	)
	if not target:
		blockers.append("No 'PATIENT RECEIVABLE' ledger found - choose the Debtors ledger manually.")
		return _result("ACC-016", apply, changes, blockers)

	if current != target:
		changes.append(f"Company.default_receivable_account: {current!r} -> {target!r}")
		if apply:
			frappe.db.set_value("Company", COMPANY, "default_receivable_account", target)

	# the stock account should not be typed as Receivable
	if current and frappe.db.get_value("Account", current, "account_type") == "Receivable":
		root = frappe.db.get_value("Account", current, "root_type")
		if "STOCK" in (current or "").upper() or root == "Asset":
			changes.append(f"Clear account_type='Receivable' from {current!r} (a stock ledger)")
			if apply:
				frappe.db.set_value("Account", current, "account_type", "")

	# debtor children need account_type=Receivable to be usable
	for acc in frappe.get_all(
		"Account",
		filters={"company": COMPANY, "is_group": 0, "name": ["like", "%RECEIVABLE%"],
		         "account_type": ["in", ["", None]]},
		pluck="name",
	):
		changes.append(f"Set account_type='Receivable' on {acc!r}")
		if apply:
			frappe.db.set_value("Account", acc, "account_type", "Receivable")

	return _result("ACC-016", apply, changes, blockers)


# --------------------------------------------------------------------------- #
# ACC-064 - purchase tax rows posting to OUTPUT VAT
# --------------------------------------------------------------------------- #
def report_vat_misposting(apply: bool = False) -> dict:
	"""Reports only. The GL correction is a finance decision, never automatic."""
	output_vat = frappe.db.get_value(
		"Account", {"company": COMPANY, "name": ["like", "%OUTPUT VAT%"], "is_group": 0}, "name"
	)
	input_vat = frappe.db.get_value(
		"Account", {"company": COMPANY, "name": ["like", "%INPUT VAT%"], "is_group": 0}, "name"
	)
	changes, blockers = [], []
	if not output_vat:
		return _result("ACC-064", apply, changes, ["No OUTPUT VAT account found"])

	total = 0.0
	for child, parent_dt in (
		("Purchase Taxes and Charges", "Purchase Invoice"),
		("Purchase Taxes and Charges", "Purchase Order"),
		("Purchase Taxes and Charges", "Purchase Receipt"),
	):
		rows = frappe.db.sql(
			f"""SELECT t.parent, t.base_tax_amount, p.docstatus
			    FROM `tab{child}` t
			    JOIN `tab{parent_dt}` p ON p.name = t.parent
			    WHERE t.parenttype = %s AND t.account_head = %s""",
			(parent_dt, output_vat),
			as_dict=True,
		)
		submitted = [r for r in rows if cint(r.docstatus) == 1]
		amount = sum(flt(r.base_tax_amount) for r in submitted)
		total += amount
		if rows:
			changes.append(
				f"{parent_dt}: {len(rows)} tax row(s) point at OUTPUT VAT "
				f"({len(submitted)} submitted, {round(amount, 3)} BHD in the GL) "
				f"- should be {input_vat}"
			)

	blockers.append(
		f"Total {round(total, 3)} BHD already posted to the VAT liability from the purchase side. "
		"Correcting submitted documents requires an adjusting journal entry - a finance decision, "
		"so this function never writes."
	)
	return _result("ACC-064", apply, changes, blockers)


# --------------------------------------------------------------------------- #
# ACC-069/070/071/132/133/139/140 - fixed asset depreciation
# --------------------------------------------------------------------------- #
def fix_asset_accounts(apply: bool = False) -> dict:
	changes, blockers = [], []

	accum = frappe.db.get_value(
		"Account",
		{"company": COMPANY, "is_group": 0, "name": ["like", "%ACCUMULATED DEP%"]}, "name")
	dep_expense = frappe.db.get_value(
		"Account",
		{"company": COMPANY, "is_group": 0, "name": ["like", "%DEPRECIATION%"],
		 "root_type": "Expense"}, "name")

	if not accum:
		blockers.append("No 'ACCUMULATED DEPRECIATION' ledger exists - it must be created first.")
	if not dep_expense:
		blockers.append("No depreciation expense ledger exists - it must be created first.")
	if blockers:
		return _result("ACC-069/070/071/132/133/139/140", apply, changes, blockers)

	for row in frappe.get_all(
		"Asset Category Account",
		filters={"company": COMPANY},
		fields=["name", "parent", "accumulated_depreciation_account", "depreciation_expense_account"],
	):
		if not row.accumulated_depreciation_account:
			changes.append(f"{row.parent}: accumulated_depreciation_account -> {accum}")
			if apply:
				frappe.db.set_value("Asset Category Account", row.name,
				                    "accumulated_depreciation_account", accum)
		if not row.depreciation_expense_account:
			changes.append(f"{row.parent}: depreciation_expense_account -> {dep_expense}")
			if apply:
				frappe.db.set_value("Asset Category Account", row.name,
				                    "depreciation_expense_account", dep_expense)

	draft = frappe.db.count("Asset", {"docstatus": 0})
	blockers.append(
		f"{draft} Assets remain in Draft with calculate_depreciation=0. Enabling depreciation and "
		"submitting them generates a large volume of GL entries and is left as a separate, "
		"explicit step."
	)
	return _result("ACC-069/070/071/132/133/139/140", apply, changes, blockers)


# --------------------------------------------------------------------------- #
# HR-058 / HR-059 / HR-068 - payroll and expense-claim accounts
# --------------------------------------------------------------------------- #
def fix_payroll_accounts(apply: bool = False) -> dict:
	changes, blockers = [], []

	payable = frappe.db.get_value(
		"Account", {"company": COMPANY, "is_group": 0, "name": ["like", "%SALAR%PAYABLE%"]}, "name"
	) or frappe.db.get_value(
		"Account", {"company": COMPANY, "is_group": 0, "root_type": "Liability",
		            "name": ["like", "%PAYABLE%"]}, "name")

	if payable and not frappe.db.get_value("Company", COMPANY, "default_payroll_payable_account"):
		changes.append(f"Company.default_payroll_payable_account -> {payable}")
		if apply:
			frappe.db.set_value("Company", COMPANY, "default_payroll_payable_account", payable)
	elif not payable:
		blockers.append("No salary/payroll payable ledger found - finance must nominate one.")

	unmapped = []
	for comp in frappe.get_all("Salary Component", fields=["name", "type"]):
		if frappe.db.exists("Salary Component Account",
		                    {"parent": comp.name, "company": COMPANY}):
			continue
		unmapped.append(comp.name)
	if unmapped:
		blockers.append(
			f"{len(unmapped)} Salary Component(s) have no account mapping: "
			f"{', '.join(unmapped[:8])}{'...' if len(unmapped) > 8 else ''}. "
			"Each must be mapped to its expense account - a finance decision, not a default."
		)

	if not frappe.db.get_value("Company", COMPANY, "default_expense_claim_payable_account"):
		blockers.append("Company.default_expense_claim_payable_account is blank (HR-068).")

	return _result("HR-058/059/068", apply, changes, blockers)


# --------------------------------------------------------------------------- #
# HR-021 - default shift, the root cause of the payroll block
# --------------------------------------------------------------------------- #
def fix_default_shifts(apply: bool = False, shift_type: str | None = None) -> dict:
	changes, blockers = [], []

	shift_type = shift_type or frappe.db.get_value(
		"Shift Type", {"enable_auto_attendance": 1}, "name"
	) or frappe.db.get_value("Shift Type", {}, "name")
	if not shift_type:
		return _result("HR-021", apply, changes, ["No Shift Type exists."])

	targets = frappe.get_all(
		"Employee",
		filters={"status": "Active", "default_shift": ["in", [None, ""]]},
		fields=["name", "employee_name"],
	)
	changes.append(
		f"Set default_shift='{shift_type}' on {len(targets)} active employee(s) with none"
	)
	if apply:
		for emp in targets:
			frappe.db.set_value("Employee", emp.name, "default_shift", shift_type,
			                    update_modified=False)

	checkins = frappe.db.count("Employee Checkin")
	attendance = frappe.db.count("Attendance")
	blockers.append(
		f"After applying, re-run attendance processing: {checkins} Employee Checkins currently "
		f"produce only {attendance} Attendance records. Shift assignment alone does not "
		"backfill history."
	)
	return _result("HR-021", apply, changes, blockers)


# --------------------------------------------------------------------------- #
# HR-146 - indemnity cutoff date
# --------------------------------------------------------------------------- #
def fix_indemnity_cutoff(apply: bool = False, target: str = "2024-04-01") -> dict:
	changes = []
	current = frappe.db.get_single_value("HR Settings", "custom_indemnity_cutoff_date")
	if str(current) != target:
		changes.append(f"HR Settings.custom_indemnity_cutoff_date: {current} -> {target} (BRD)")
		if apply:
			frappe.db.set_single_value("HR Settings", "custom_indemnity_cutoff_date", target)
	return _result("HR-146", apply, changes)


# --------------------------------------------------------------------------- #
# PHA-045 / PHA-052 / WF-024 - discount caps
# --------------------------------------------------------------------------- #
def fix_discount_caps(apply: bool = False, max_percent: float = 20.0) -> dict:
	"""Report the discount cap; deliberately does not create a second one.

	A cap already exists and is enforced on every Sales Invoice - POS included -
	by healthcare.api.discount_authorisation, driven by Healthcare Settings
	.discount_approval_threshold_percent. Populating POS Profile
	.custom_max_discount_percent as well would mean two caps on the same action,
	failing with two different messages depending on which validation ran first.
	So this reports the single source of truth instead of duplicating it.
	"""
	enabled = frappe.db.get_single_value("Healthcare Settings", "require_discount_approval")
	threshold = flt(
		frappe.db.get_single_value("Healthcare Settings", "discount_approval_threshold_percent")
	)
	unset = [
		p.name
		for p in frappe.get_all("POS Profile", fields=["name", "custom_max_discount_percent"])
		if not flt(p.custom_max_discount_percent)
	]

	blockers = []
	if not enabled:
		blockers.append(
			"Healthcare Settings.require_discount_approval is off - the cap is not enforced. "
			"Enable it rather than setting per-profile caps."
		)
	elif threshold != max_percent:
		blockers.append(
			f"Live cap is {threshold}%, not the {max_percent}% requested here. "
			f"Change Healthcare Settings.discount_approval_threshold_percent to move it."
		)
	if unset:
		blockers.append(
			f"{len(unset)} POS Profile(s) have custom_max_discount_percent unset. Left unset "
			f"on purpose - the healthcare cap already covers POS invoices."
		)

	return _result("PHA-045/052 + WF-024", apply, [], blockers)


# --------------------------------------------------------------------------- #
# PHA-033 / PHA-068 - batch and expiry enforcement
# --------------------------------------------------------------------------- #
def fix_batch_expiry(apply: bool = False) -> dict:
	changes, blockers = [], []

	no_expiry = frappe.get_all(
		"Item",
		filters={"has_batch_no": 1, "has_expiry_date": 0, "disabled": 0},
		pluck="name",
	)
	changes.append(f"Set has_expiry_date=1 on {len(no_expiry)} batched item(s) missing it")
	if apply:
		for item in no_expiry:
			frappe.db.set_value("Item", item, "has_expiry_date", 1, update_modified=False)

	unbatched = frappe.db.count(
		"Item", {"has_batch_no": 0, "disabled": 0, "is_stock_item": 1}
	)
	blockers.append(
		f"{unbatched} stock items have no batch tracking at all. Turning it on retrospectively "
		"breaks existing stock ledgers, so each must be reviewed for whether it is a medicine - "
		"this function does not touch them."
	)
	return _result("PHA-033/068", apply, changes, blockers)


# --------------------------------------------------------------------------- #
def run_all(apply: bool = False) -> list[dict]:
	"""Run every prepared remediation. Dry-run unless apply=True."""
	return [
		fix_receivable_account(apply),
		report_vat_misposting(apply),
		fix_asset_accounts(apply),
		fix_payroll_accounts(apply),
		fix_default_shifts(apply),
		fix_indemnity_cutoff(apply),
		fix_discount_caps(apply),
		fix_batch_expiry(apply),
	]
