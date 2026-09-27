import frappe
from dateutil.relativedelta import relativedelta
from frappe import _
from frappe.utils import add_days, flt, getdate, nowdate

# Healthcare Settings flag that turns the outstanding-balance recovery on/off.
OUTSTANDING_BALANCE_FLAG = "add_outstanding_balance_to_full_and_final_settlement"

# Healthcare Settings link to the Salary Component the outstanding balance is
# booked with. It has to be a Deduction component: Additional Salary refuses a
# negative amount ("Amount should not be less than zero"), so a Deduction is how
# HRMS expresses a negative additional salary - pay taken back from the employee
# instead of paid out to them.
OUTSTANDING_BALANCE_SALARY_COMPONENT = "outstanding_balance_salary_component"

# Label of the auto-generated deduction row. It is written to
# Full and Final Outstanding Statement.component, which the FFS Summary print
# format shows as the description of the deduction, and it doubles as the marker
# used to find (and refresh) the row on every save instead of duplicating it.
OUTSTANDING_BALANCE_LABEL = "Outstanding Sales Invoice"

# Reference document of the auto-generated deduction row: the Additional Salary
# the balance is booked as. The settlement Journal Entry needs the Employee as
# party on a Receivable account, and HRMS only tags it when a receivable row
# references an "Employee Advance" (FullandFinalStatement.create_journal_entry),
# so tag_outstanding_balance_employee_party below tags the row's credit line.
OUTSTANDING_BALANCE_REFERENCE_TYPE = "Additional Salary"


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
	_populate_outstanding_sales_invoices(doc)


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
		indemnity.consider_full_salary_after_cutoff_date = doc.custom_consider_full_salary_after_cutoff_date
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


def _populate_outstanding_sales_invoices(doc):
	"""Recover the employee's outstanding Sales Invoices from the settlement.

	Only runs when ``Healthcare Settings.add_outstanding_balance_to_full_and_final_settlement``
	is ticked. The employee is linked to the invoices either directly
	(``Sales Invoice.custom_employee``) or through their customer record
	(``Customer.custom_employee``). Whatever is still owing is booked as a Deduction
	Additional Salary (``HR-ADS-...``) and pushed to the receivables table of the
	statement (``Full and Final Outstanding Statement``), which is what makes it a
	deduction: the FFS Summary prints receivables as negative amounts, HRMS folds
	them into ``total_receivable_amount`` and credits them against the employee
	when the settlement Journal Entry is created.

	Both the Additional Salary and the row are rebuilt on every save, so the amount
	always tracks the current outstanding balance and is never duplicated.
	"""
	if doc.docstatus != 0 or not doc.employee:
		return

	if not frappe.db.get_single_value("Healthcare Settings", OUTSTANDING_BALANCE_FLAG):
		return

	# Drop the row generated by a previous save before recomputing it. The Additional
	# Salary it references is refreshed below instead of being created a second time.
	previous_reference = next(
		(
			row.reference_document
			for row in (doc.receivables or [])
			if row.component == OUTSTANDING_BALANCE_LABEL
			and row.reference_document_type == OUTSTANDING_BALANCE_REFERENCE_TYPE
		),
		None,
	)

	doc.receivables = [row for row in (doc.receivables or []) if row.component != OUTSTANDING_BALANCE_LABEL]

	invoices = _get_outstanding_sales_invoices(doc.employee, doc.company)
	total = flt(sum(flt(invoice.outstanding_amount) for invoice in invoices), 3)

	if total and invoices:
		doc.append(
			"receivables",
			{
				"component": OUTSTANDING_BALANCE_LABEL,
				"amount": total,
				"account": _get_outstanding_receivable_account(invoices, doc),
				"reference_document_type": OUTSTANDING_BALANCE_REFERENCE_TYPE,
				"reference_document": _get_or_create_outstanding_additional_salary(
					doc, invoices, total, previous_reference
				),
				"status": "Unsettled",
				"remark": _describe_outstanding_invoices(invoices),
			},
		)

	# before_save runs after the controller's validate, so the totals computed
	# there have to be recomputed for the deduction to be reflected.
	doc.set_totals()


def _get_or_create_outstanding_additional_salary(doc, invoices, total, reference=None):
	"""Book the outstanding balance as a Deduction Additional Salary, return its name.

	The statement deducts the balance, while the Additional Salary is the document
	Payroll and HR follow the deduction up with - the balance comes off the
	employee's pay instead of being paid out to them. It is created as a Draft, like
	a manually entered additional salary: nothing is deducted until HR/Accounts
	submits it, so the statement stays the only document that moves the ledger.

	Validation is skipped on purpose. At relieving time the employee may already be
	marked Left and have no submitted Salary Structure Assignment, which HRMS'
	Additional Salary validation rejects, so the payroll date is clamped to the
	employment period by hand instead - the same way
	``beveren_health.scripts.create_fnf_from_xlsx`` raises these documents.

	A document created by an earlier save is refreshed rather than duplicated. Once
	it has been submitted it belongs to Payroll/Accounts and is left untouched; a new
	draft is raised for the current balance instead.
	"""
	salary_component = _get_outstanding_balance_salary_component()
	if not salary_component:
		return None

	payroll_date = _get_outstanding_balance_payroll_date(doc)
	remarks = _describe_outstanding_invoices(invoices)

	if reference and frappe.db.exists("Additional Salary", reference):
		employee, docstatus = frappe.db.get_value("Additional Salary", reference, ["employee", "docstatus"])
		if employee == doc.employee and docstatus == 0:
			additional_salary = frappe.get_doc("Additional Salary", reference)
			additional_salary.salary_component = salary_component
			additional_salary.amount = total
			additional_salary.payroll_date = payroll_date
			_set_outstanding_balance_remarks(additional_salary, remarks)
			additional_salary.flags.ignore_validate = True
			additional_salary.save(ignore_permissions=True)
			return additional_salary.name

	additional_salary = frappe.new_doc("Additional Salary")
	additional_salary.employee = doc.employee
	additional_salary.company = doc.company
	additional_salary.currency = frappe.db.get_value("Company", doc.company, "default_currency")
	additional_salary.salary_component = salary_component
	# Set explicitly, as the fetched component type is only applied when link
	# validation runs (which is skipped below while the statement is new).
	additional_salary.type = frappe.db.get_value("Salary Component", salary_component, "type")
	additional_salary.amount = total
	additional_salary.payroll_date = payroll_date
	additional_salary.is_recurring = 0
	additional_salary.overwrite_salary_structure_amount = 0
	additional_salary.ref_doctype = doc.doctype
	additional_salary.ref_docname = doc.name
	_set_outstanding_balance_remarks(additional_salary, remarks)
	additional_salary.flags.ignore_permissions = True
	additional_salary.flags.ignore_validate = True
	if not frappe.db.exists(doc.doctype, doc.name):
		# This runs before a new statement is written, so its name is not in the
		# database yet and the reference above would fail link validation.
		additional_salary.flags.ignore_links = True
	additional_salary.insert()

	return additional_salary.name


def _get_outstanding_balance_salary_component():
	"""Deduction Salary Component the outstanding balance is booked with.

	Configured on Healthcare Settings next to the flag, the same way Doctor
	Commission Payroll reads its component. Without it nothing can be booked, so the
	statement keeps a plain deduction row (no reference document) and HR is told why.
	"""
	component = frappe.db.get_single_value("Healthcare Settings", OUTSTANDING_BALANCE_SALARY_COMPONENT)
	component_type = frappe.db.get_value("Salary Component", component, "type") if component else None

	if not component or not component_type:
		frappe.msgprint(
			_(
				"Set {0} in Healthcare Settings to book the outstanding Sales Invoice balance as an "
				"Additional Salary. The statement was saved with the balance as a plain deduction."
			).format(frappe.bold(_("Outstanding Balance Salary Component"))),
			title=_("Outstanding Balance"),
			indicator="orange",
		)
		return None

	if component_type != "Deduction":
		frappe.msgprint(
			_(
				"{0} is not a Deduction Salary Component, so the outstanding balance will be paid out "
				"to the employee instead of being recovered from the settlement. Set a Deduction "
				"component in {1}."
			).format(frappe.bold(component), frappe.bold(_("Outstanding Balance Salary Component"))),
			title=_("Outstanding Balance"),
			indicator="red",
		)

	return component


def _get_outstanding_balance_payroll_date(doc):
	"""Payroll date of the Additional Salary: the statement's date, kept inside the
	employee's employment period (HRMS rejects a payroll date after the relieving
	date or before the joining date).
	"""
	payroll_date = getdate(doc.transaction_date or nowdate())

	if doc.relieving_date and payroll_date > getdate(doc.relieving_date):
		payroll_date = getdate(doc.relieving_date)

	if doc.date_of_joining and payroll_date < getdate(doc.date_of_joining):
		payroll_date = getdate(doc.date_of_joining)

	return payroll_date


def _set_outstanding_balance_remarks(additional_salary, remarks):
	"""The invoice breakdown has no standard field on Additional Salary, so it goes to
	the Remarks field the HR team reads - where the site has one.
	"""
	if frappe.get_meta("Additional Salary").has_field("custom_remarks"):
		additional_salary.custom_remarks = remarks


def tag_outstanding_balance_employee_party(jv, doc):
	"""Tag the Employee as party on the Journal Entry line of the outstanding balance.

	HRMS (FullandFinalStatement.create_journal_entry) tags the settlement Journal
	Entry with the Employee only when a receivable row references an Employee
	Advance, but a Receivable account cannot be posted to without a party and this row
	references an Additional Salary. Its credit line is tagged here, so the statement
	can still be settled through HRMS' "Create Journal Entry" button.
	"""
	receivable_rows = [row for row in doc.receivables if flt(row.amount) > 0]
	if not any(row.reference_document_type == OUTSTANDING_BALANCE_REFERENCE_TYPE for row in receivable_rows):
		return jv

	# HRMS appends the receivable lines in row order and with the same precision, so
	# tracking the last matched row identifies its line without touching the others.
	precision = frappe.get_precision("Journal Entry Account", "debit_in_account_currency")
	row_index = 0

	for line in jv.accounts:
		if row_index == len(receivable_rows):
			break

		row = receivable_rows[row_index]
		if line.account != row.account or flt(line.credit_in_account_currency, precision) != flt(
			row.amount, precision
		):
			continue

		row_index += 1

		if row.reference_document_type == OUTSTANDING_BALANCE_REFERENCE_TYPE and not line.party_type:
			line.party_type = "Employee"
			line.party = doc.employee

	return jv


def _get_outstanding_sales_invoices(employee, company=None):
	"""Return submitted Sales Invoices with a balance that belong to the employee.

	Invoices are matched either directly (``Sales Invoice.custom_employee``) or
	through the customer they were raised for (``Customer.custom_employee``), as
	both links identify the same employee.
	"""
	or_filters = {}

	if frappe.db.has_column("Sales Invoice", "custom_employee"):
		or_filters["custom_employee"] = employee

	if frappe.db.has_column("Customer", "custom_employee"):
		customers = frappe.get_all("Customer", filters={"custom_employee": employee}, pluck="name")
		if customers:
			or_filters["customer"] = ["in", customers]

	if not or_filters:
		return []

	filters = {"docstatus": 1, "outstanding_amount": [">", 0]}
	if company:
		filters["company"] = company

	return frappe.get_all(
		"Sales Invoice",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "customer", "outstanding_amount", "debit_to", "posting_date"],
		order_by="posting_date asc",
	)


def _get_outstanding_receivable_account(invoices, doc):
	"""Account credited when recovering the balance (the invoice receivable account).

	The statement carries a single receivable row for all invoices, so the
	account of the first invoice is used - invoices of one company normally share
	the same receivable account - falling back to the company's default.
	"""
	for invoice in invoices:
		if invoice.debit_to:
			return invoice.debit_to
	return frappe.db.get_value("Company", doc.company, "default_receivable_account")


def _describe_outstanding_invoices(invoices, limit=10):
	"""Invoice wise breakdown written to the row's remark (and to the Journal Entry)."""
	preview = ", ".join(
		"{0} ({1}): {2}".format(invoice.name, invoice.customer, flt(invoice.outstanding_amount, 3))
		for invoice in invoices[:limit]
	)
	if len(invoices) > limit:
		preview = _("{0} and {1} more").format(preview, len(invoices) - limit)

	return _("Outstanding Sales Invoice balance recovered from final settlement: {0}").format(preview)
