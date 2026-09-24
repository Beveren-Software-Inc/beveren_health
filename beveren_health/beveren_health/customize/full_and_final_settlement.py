import frappe
from dateutil.relativedelta import relativedelta
from frappe import _
from frappe.utils import add_days, flt, nowdate


@frappe.whitelist()
def get_reference_doctypes(doctype, txt, searchfield, start, page_len, filters):
	"""Search function for reference_document_type in FnF payables/receivables.
	Includes HR/Payroll/Loan Management module doctypes plus Indemnity only from Beveren Health.
	"""
	return frappe.db.sql(
		"""
        SELECT name FROM `tabDocType`
        WHERE (
            (module IN %(modules)s AND istable = 0 AND issingle = 0)
            OR name = 'Indemnity'
        )
        AND name LIKE %(txt)s
        ORDER BY name
        LIMIT %(page_len)s OFFSET %(start)s
        """,
		{
			"modules": ["HR", "Payroll", "Loan Management"],
			"txt": f"%{txt}%",
			"page_len": int(page_len),
			"start": int(start),
		},
	)


def before_save(doc, method):
	_set_total_experience(doc)
	_populate_indemnity_payables(doc)


def _set_total_experience(doc):
	relieving_date = add_days(doc.relieving_date, 1)
	rd = relativedelta(relieving_date, doc.date_of_joining)
	doc.custom_total_experience = f"{rd.years} years {rd.months} months and {rd.days} days"


def _populate_indemnity_payables(doc):
	if not doc.custom_indemnity:
		return

	indemnity = frappe.get_doc("Indemnity", doc.custom_indemnity)

	LABEL_BEFORE = "Indemnity Reward (Before Cut-Off Date)"
	LABEL_AFTER = "Indemnity Reward (After Cut-Off Date)"

	def upsert_payable(label, amount, payable_account):
		for row in doc.payables:
			if row.component == label:
				row.amount = flt(amount, 3)
				row.account = payable_account or row.account
				row.reference_document_type = "Indemnity"
				row.reference_document = indemnity.name
				return
		doc.append(
			"payables",
			{
				"component": label,
				"amount": flt(amount, 3),
				"account": payable_account,
				"reference_document_type": "Indemnity",
				"reference_document": indemnity.name,
				"status": "Unsettled",
				"paid_via_salary_slip": indemnity.pay_via_salary_slip,
			},
		)

	if flt(indemnity.indemnity_before):
		upsert_payable(LABEL_BEFORE, indemnity.indemnity_before, indemnity.payable_account)

	if flt(indemnity.indemnity_after):
		upsert_payable(LABEL_AFTER, indemnity.indemnity_after, indemnity.payable_account)

	# before_save runs after the controller's validate, so the totals computed
	doc.set_totals()


@frappe.whitelist()
def create_indemnity(fnf: str) -> str:
	"""Create (or re-link) the Indemnity for a draft Full and Final Statement.

	The Indemnity computes its own figures from the employee's Salary Structure
	Assignment and the HR Settings cutoff date, so only the identifying fields
	are supplied here. Saving the statement afterwards lets before_save push the
	computed amounts into the payables table.
	"""
	doc = frappe.get_doc("Full and Final Statement", fnf)
	doc.check_permission("write")

	if doc.docstatus != 0:
		frappe.throw(_("Indemnity can only be generated from a draft Full and Final Statement."))

	if doc.custom_indemnity:
		frappe.throw(
			_("Indemnity {0} is already linked to this statement.").format(
				frappe.bold(frappe.get_desk_link("Indemnity", doc.custom_indemnity))
			)
		)

	# Indemnity refuses duplicates for the same joining/relieving period, so an
	# existing one for this employee is linked instead of creating a second.
	indemnity_name = frappe.db.get_value(
		"Indemnity",
		{
			"employee": doc.employee,
			"date_of_joining": doc.date_of_joining,
			"relieving_date": doc.relieving_date,
			"docstatus": ["!=", 2],
		},
		"name",
	)

	if not indemnity_name:
		indemnity = frappe.new_doc("Indemnity")
		indemnity.employee = doc.employee
		indemnity.company = doc.company
		indemnity.posting_date = doc.transaction_date or nowdate()
		indemnity.consider_full_salary_after_cutoff_date = (
			doc.custom_consider_full_salary_after_cutoff_date
		)
		indemnity.cost_center = _get_cost_center(doc)
		indemnity.insert()
		indemnity_name = indemnity.name

	doc.custom_indemnity = indemnity_name
	doc.save()

	return indemnity_name


def _get_cost_center(doc):
	cost_center = frappe.db.get_value("Employee", doc.employee, "payroll_cost_center")
	if not cost_center:
		cost_center = frappe.db.get_value("Company", doc.company, "cost_center")
	if not cost_center:
		frappe.throw(
			_(
				"No Cost Center found for employee {0}. Set a Payroll Cost Center on the "
				"Employee or a default Cost Center on the Company."
			).format(frappe.bold(doc.employee))
		)
	return cost_center
