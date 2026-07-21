# Copyright (c) 2026, Beveren Software
"""HR-154 / HR-155 / HR-156 - patient-visit allowances on the overtime slip.

Serene pays a fixed allowance per patient-related trip on top of overtime:

  * bring the patient in from home        10 BD
  * went, but the patient did not come     5 BD
  * home visit to see a patient            5 BD (HOD approved)

Rates live on the slip so they can be overridden per case; the total is computed
on validate. Kept separate from customize/overtime_slip.py so the existing
OvertimeSlip class override stays untouched.
"""

from __future__ import annotations

import frappe
from frappe.utils import flt

DEFAULT_RATES = {
	"custom_home_visit_rate": 5.0,
	"custom_bring_patient_rate": 10.0,
	"custom_bring_patient_no_show_rate": 5.0,
}


def validate(doc, method=None) -> None:
	"""Overtime Slip `validate` hook."""
	if not doc.meta.has_field("custom_patient_visit_allowance"):
		return

	for field, default in DEFAULT_RATES.items():
		if not flt(doc.get(field)):
			doc.set(field, default)

	doc.custom_patient_visit_allowance = (
		flt(doc.get("custom_home_visit_count")) * flt(doc.get("custom_home_visit_rate"))
		+ flt(doc.get("custom_bring_patients_count")) * flt(doc.get("custom_bring_patient_rate"))
		+ flt(doc.get("custom_bring_patients_no_show_count"))
		* flt(doc.get("custom_bring_patient_no_show_rate"))
	)


@frappe.whitelist()
def get_patient_visit_allowance(overtime_slip: str) -> float:
	doc = frappe.get_doc("Overtime Slip", overtime_slip)
	validate(doc)
	return flt(doc.custom_patient_visit_allowance)
