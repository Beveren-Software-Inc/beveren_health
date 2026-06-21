import frappe
from frappe.utils import add_days, flt
from dateutil.relativedelta import relativedelta


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
    doc.custom_total_experience = (
        f"{rd.years} years {rd.months} months and {rd.days} days"
    )


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
        doc.append("payables", {
            "component": label,
            "amount": flt(amount, 3),
            "account": payable_account,
            "reference_document_type": "Indemnity",
            "reference_document": indemnity.name,
            "status": "Unsettled",
            "paid_via_salary_slip": indemnity.pay_via_salary_slip,
        })

    if flt(indemnity.indemnity_before):
        upsert_payable(LABEL_BEFORE, indemnity.indemnity_before, indemnity.payable_account)

    if flt(indemnity.indemnity_after):
        upsert_payable(LABEL_AFTER, indemnity.indemnity_after, indemnity.payable_account)
