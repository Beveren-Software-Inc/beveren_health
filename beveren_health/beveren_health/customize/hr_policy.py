# Copyright (c) 2026, Beveren Software
"""HR-107 - share HR policy documents with employees and track acknowledgement."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now_datetime


def _target_employees(policy) -> list[dict]:
	filters = {"status": "Active"}
	if policy.company:
		filters["company"] = policy.company
	if not policy.applies_to_all:
		if policy.department:
			filters["department"] = policy.department
		if policy.designation:
			filters["designation"] = policy.designation
	return frappe.get_all("Employee", filters=filters, fields=["name", "employee_name", "user_id"])


def distribute_policy(doc, method=None) -> None:
	"""HR Policy Document `on_update` - fan out acknowledgement rows when published."""
	if not doc.is_published:
		return

	employees = _target_employees(doc)
	created = 0

	for emp in employees:
		if frappe.db.exists(
			"HR Policy Acknowledgement", {"policy": doc.name, "employee": emp.name}
		):
			continue

		frappe.get_doc(
			{
				"doctype": "HR Policy Acknowledgement",
				"policy": doc.name,
				"employee": emp.name,
				"status": "Pending" if doc.requires_acknowledgement else "Acknowledged",
				"acknowledged_on": None if doc.requires_acknowledgement else now_datetime(),
			}
		).insert(ignore_permissions=True)
		created += 1

		if emp.user_id and frappe.db.exists("User", emp.user_id):
			frappe.get_doc(
				{
					"doctype": "Notification Log",
					"for_user": emp.user_id,
					"type": "Alert",
					"document_type": "HR Policy Document",
					"document_name": doc.name,
					"subject": _("New HR policy: {0}").format(doc.policy_title),
					"email_content": _(
						"{0} (version {1}) is effective from {2}. Please read and acknowledge it."
					).format(doc.policy_title, doc.version or "1.0", doc.effective_date),
				}
			).insert(ignore_permissions=True)

	if created:
		doc.add_comment("Info", _("Policy shared with {0} employee(s).").format(created))


@frappe.whitelist()
def my_policies() -> list[dict]:
	"""Policies visible to the logged-in employee, with acknowledgement state."""
	employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	if not employee:
		return []

	rows = frappe.get_all(
		"HR Policy Acknowledgement",
		filters={"employee": employee},
		fields=["name", "policy", "status", "acknowledged_on"],
	)
	for row in rows:
		policy = frappe.db.get_value(
			"HR Policy Document",
			row.policy,
			["policy_title", "policy_category", "version", "effective_date",
			 "policy_document", "summary", "acknowledgement_deadline"],
			as_dict=True,
		)
		row.update(policy or {})
	return rows


@frappe.whitelist()
def acknowledge_policy(acknowledgement: str, remarks: str | None = None) -> dict:
	"""Employee confirms they have read a policy."""
	doc = frappe.get_doc("HR Policy Acknowledgement", acknowledgement)

	employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	if doc.employee != employee and "HR Manager" not in frappe.get_roles():
		frappe.throw(_("You can only acknowledge your own policies."), frappe.PermissionError)

	doc.status = "Acknowledged"
	doc.acknowledged_on = now_datetime()
	if remarks:
		doc.remarks = remarks
	doc.save(ignore_permissions=True)

	return {"status": doc.status, "acknowledged_on": str(doc.acknowledged_on)}


@frappe.whitelist()
def policy_compliance(policy: str | None = None) -> dict:
	"""HR view: who has and has not acknowledged."""
	filters = {"policy": policy} if policy else {}
	rows = frappe.get_all(
		"HR Policy Acknowledgement",
		filters=filters,
		fields=["policy", "employee", "employee_name", "status", "acknowledged_on"],
		limit_page_length=0,
	)
	acknowledged = [r for r in rows if r.status == "Acknowledged"]
	return {
		"total": len(rows),
		"acknowledged": len(acknowledged),
		"pending": len(rows) - len(acknowledged),
		"rows": rows,
	}
