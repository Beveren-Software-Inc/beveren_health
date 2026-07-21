# Copyright (c) 2026, Beveren Software
"""ACC-181 - apply the correct price list based on patient admission status.

An inpatient is billed from the IP Selling price list, an outpatient from OP
Selling. The lists were created for ACC-179/180; this picks the right one
automatically instead of relying on the user.
"""

from __future__ import annotations

import frappe

OP_PRICE_LIST = "OP Selling"
IP_PRICE_LIST = "IP Selling"


def _enabled() -> bool:
	return bool(
		frappe.db.get_single_value("Healthcare Settings", "auto_apply_patient_price_list")
	)


def _is_inpatient(patient: str) -> bool:
	if not patient:
		return False
	status = frappe.db.get_value("Patient", patient, "inpatient_status")
	if status == "Admitted":
		return True
	return bool(
		frappe.db.exists(
			"Inpatient Admission", {"patient": patient, "status": "Admitted"}
		)
	)


def set_price_list_for_patient(doc, method=None) -> None:
	"""`validate` hook for Sales Order / Sales Invoice / Quotation."""
	if not _enabled():
		return

	patient = doc.get("patient")
	if not patient:
		return

	# Never override a price list the user picked deliberately.
	if doc.get("selling_price_list") not in (None, "", OP_PRICE_LIST, IP_PRICE_LIST,
	                                         "Standard Selling"):
		return

	target = IP_PRICE_LIST if _is_inpatient(patient) else OP_PRICE_LIST
	if not frappe.db.exists("Price List", target):
		return

	if doc.get("selling_price_list") != target:
		doc.selling_price_list = target


@frappe.whitelist()
def get_price_list_for_patient(patient: str) -> str:
	"""Helper for the POS / SPA so the UI can show the right list up front."""
	return IP_PRICE_LIST if _is_inpatient(patient) else OP_PRICE_LIST
