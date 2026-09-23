# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

"""Timesheet: keep the row level Patient in sync with the header Patient.

``Timesheet.custom_patient`` is the patient the whole sheet is logged against;
``Timesheet Detail.custom_patient`` (time_logs) repeats it so that reports and
the portal can read the patient straight off the row. The desk form fills the
rows on the client (public/js/timesheet.js) - this hook covers documents created
through the API, data import or any other server side script.
"""

from __future__ import annotations

import frappe


def set_patient_on_time_logs(doc, method: str | None = None) -> None:
	"""``validate`` hook for Timesheet (see hooks.py)."""
	patient = doc.get("custom_patient")
	if not patient:
		return

	if not frappe.get_meta("Timesheet Detail").has_field("custom_patient"):
		return

	for row in doc.get("time_logs") or []:
		# Never overwrite a patient deliberately picked on a single row.
		if not row.get("custom_patient"):
			row.custom_patient = patient
