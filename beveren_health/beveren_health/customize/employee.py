import frappe
from frappe import _
from frappe.utils import date_diff

# Document names (Employee Document.document_name) tracked by the checks below.
CPR_DOCUMENT_NAME = "CPR"
NHRA_DOCUMENT_NAME = "NHRA"

# Licensed designations that must have an NHRA document on file.
NHRA_MANDATORY_DESIGNATIONS = (
	"NURSE",
	"DOCTOR",
	"GP DOCTOR",
	"CONSULTANT",
	"HEAD NURSE",
	"LAB TECHNICIAN",
)


def calculate_years_of_service(doc):
	if doc.relieving_date and doc.date_of_joining:
		days = date_diff(doc.relieving_date, doc.date_of_joining)
		years = int(days / 365)
		doc.custom_years_of_service = years


def get_employee_label(doc):
	"""Return a readable employee reference for warning messages."""
	return doc.get("employee_name") or doc.get("name") or _("this employee")


def get_document_rows(doc, document_name):
	"""Return the Documents child rows matching document_name (trimmed, case-insensitive)."""
	wanted = (document_name or "").strip().upper()
	return [
		row
		for row in (doc.get("custom_documents") or [])
		if (row.document_name or "").strip().upper() == wanted
	]


def has_cpr_document(doc):
	"""Return True when the employee's Documents table has a CPR row."""
	return bool(get_document_rows(doc, CPR_DOCUMENT_NAME))


def warn_if_cpr_document_missing(doc):
	"""Warn (without blocking) when the employee has no CPR document row.

	CPR is tracked as a row of the Documents child table (custom_documents ->
	Employee Document) whose Document Name is "CPR". This is only a warning:
	the employee is always saved.
	"""
	if has_cpr_document(doc):
		return

	frappe.msgprint(
		_("Employee {0} does not have a CPR document. Please add it in the Documents table.").format(
			frappe.bold(get_employee_label(doc))
		),
		title=_("CPR Document Missing"),
		indicator="orange",
	)


def warn_if_nhra_document_missing(doc):
	"""Warn (without blocking) when the NHRA document is missing or has no expiry date.

	NHRA is tracked as a row of the Documents child table (custom_documents ->
	Employee Document) whose Document Name is "NHRA". It is required when the
	employee holds a licensed designation (Nurse, Doctor, GP Doctor, Consultant,
	Head Nurse, Lab Technician). When an NHRA row has been added it must always
	carry an expiry date, whatever the designation. Warnings never block saving.
	"""
	employee = get_employee_label(doc)
	designation = (doc.get("designation") or "").strip()
	nhra_rows = get_document_rows(doc, NHRA_DOCUMENT_NAME)

	if not nhra_rows:
		if designation.upper() in NHRA_MANDATORY_DESIGNATIONS:
			frappe.msgprint(
				_(
					"Employee {0} ({1}) does not have an NHRA document. "
					"Please add NHRA in the Documents table with its expiry date."
				).format(frappe.bold(employee), frappe.bold(designation)),
				title=_("NHRA Document Missing"),
				indicator="orange",
			)
		return

	if any(not row.document_expiry_date for row in nhra_rows):
		frappe.msgprint(
			_(
				"NHRA document of employee {0} does not have an expiry date. "
				"Please set the Document Expiry Date."
			).format(frappe.bold(employee)),
			title=_("NHRA Expiry Date Missing"),
			indicator="orange",
		)


def before_save(doc, method):
	calculate_years_of_service(doc)
	warn_if_cpr_document_missing(doc)
	warn_if_nhra_document_missing(doc)
