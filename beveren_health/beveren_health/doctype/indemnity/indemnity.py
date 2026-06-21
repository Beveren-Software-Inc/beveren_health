import frappe
from frappe import _
from frappe.utils import flt, getdate
from frappe.utils.safe_exec import safe_eval
from dateutil.relativedelta import relativedelta

from erpnext.controllers.accounts_controller import AccountsController
from erpnext.accounts.general_ledger import make_gl_entries


class Indemnity(AccountsController):
    def validate(self):
        self._set_cutoff_date()
        self._set_default_accounts()
        self._validate_dates()
        self._validate_unique()
        if self.nationality == "Bahraini" and self.is_gosi_registered:
            self.base_salary = 0
            self.basic_salary = 0
            self.eligible_days_before = 0
            self.eligible_days_after = 0
            self.indemnity_before = 0
            self.indemnity_after = 0
            self.amount = 0
            self.status = "Draft" if self.docstatus == 0 else "Submitted"
            return
        self._compute_salaries()
        self._compute_indemnity()
        self.status = "Draft" if self.docstatus == 0 else "Submitted"

    def on_submit(self):
        self.status = "Submitted"
        self.db_set("status", "Submitted")
        if self.pay_via_salary_slip:
            self._create_additional_salary()
        else:
            self._validate_accounts()
            self._create_gl_entries()

    def on_cancel(self):
        self.status = "Cancelled"
        self.db_set("status", "Cancelled")
        if not self.pay_via_salary_slip:
            self._create_gl_entries(cancel=True)

    def _validate_unique(self):
        if not self.date_of_joining or not self.relieving_date:
            return
        existing = frappe.db.get_value(
            "Indemnity",
            {
                "employee": self.employee,
                "date_of_joining": self.date_of_joining,
                "relieving_date": self.relieving_date,
                "docstatus": ["!=", 2],
                "name": ["!=", self.name],
            },
            "name",
        )
        if existing:
            frappe.throw(
                _(
                    "An Indemnity document {0} already exists for employee {1} "
                    "for the same joining and relieving period."
                ).format(
                    frappe.bold(frappe.get_desk_link("Indemnity", existing)),
                    frappe.bold(self.employee),
                )
            )

    def _set_cutoff_date(self):
        cutoff = frappe.db.get_single_value("HR Settings", "custom_indemnity_cutoff_date")
        if cutoff:
            self.indemnity_cutoff_date = cutoff

    def _set_default_accounts(self):
        if not self.expense_account:
            self.expense_account = frappe.db.get_single_value(
                "HR Settings", "custom_indemnity_expense_account"
            )
        if not self.payable_account:
            self.payable_account = frappe.db.get_single_value(
                "HR Settings", "custom_indemnity_payable_account"
            )

    def _validate_dates(self):
        if not self.date_of_joining:
            frappe.throw(_("Date of Joining is required. Please ensure the Employee record has it set."))
        if not self.relieving_date:
            frappe.throw(_("Relieving Date is required. Please ensure the Employee record has it set."))
        if not self.indemnity_cutoff_date:
            frappe.throw(_("Indemnity Cutoff Date is not configured. Please set it in HR Settings."))

    def _compute_salaries(self):
        assignment = frappe.db.get_value(
            "Salary Structure Assignment",
            {"employee": self.employee, "docstatus": 1},
            ["salary_structure", "base"],
            order_by="from_date desc",
            as_dict=True,
        )
        if not assignment:
            frappe.throw(_("No active Salary Structure Assignment found for employee {0}.").format(self.employee))

        base = flt(assignment.base)
        self.base_salary = base

        structure = frappe.get_doc("Salary Structure", assignment.salary_structure)
        basic_salary = 0.0
        for earning in structure.earnings:
            component = frappe.get_doc("Salary Component", earning.salary_component)
            if not component.get("custom_is_basic_salary_"):
                continue
            amount = flt(earning.amount)
            if component.amount_based_on_formula and component.formula:
                context = {"doc": self, "flt": flt, "base": base}
                try:
                    amount = safe_eval(component.formula, context)
                except Exception as e:
                    frappe.throw(
                        _("Error evaluating formula for {0}: {1}").format(component.salary_component, e)
                    )
            basic_salary += amount

        if not basic_salary:
            frappe.throw(
                _("Basic Salary component not found or evaluates to zero in the Salary Structure.")
            )
        self.basic_salary = flt(basic_salary)

    def _compute_indemnity(self):
        cutoff_date = getdate(self.indemnity_cutoff_date)
        doj = getdate(self.date_of_joining)
        relieving = getdate(self.relieving_date)

        ir_base_before = flt(self.base_salary)
        ir_base_after = flt(self.base_salary) if self.consider_full_salary_after_cutoff_date else flt(self.basic_salary)

        def get_eligible_days(total_days):
            if total_days <= 0:
                return 0.0
            if total_days <= 1095:
                return total_days * 15.0 / 365
            return 45.0 + (total_days - 1095) * 30.0 / 365

        indemnity_before = 0.0
        indemnity_after = 0.0
        eligible_days_before = 0.0
        eligible_days_after = 0.0

        if doj < cutoff_date:
            import datetime
            seg1_end = cutoff_date - datetime.timedelta(days=1)
            seg1_days = (seg1_end - doj).days + 1
            total_days_full = (relieving - doj).days + 1

            eligible_days_before = get_eligible_days(seg1_days)
            eligible_days_after = get_eligible_days(total_days_full) - eligible_days_before

            indemnity_before = ir_base_before * 12 * eligible_days_before / 365
            indemnity_after = ir_base_after * 12 * eligible_days_after / 365
        else:
            total_days = (relieving - doj).days + 1
            eligible_days_after = get_eligible_days(total_days)
            indemnity_after = ir_base_after * 12 * eligible_days_after / 365

        self.eligible_days_before = flt(eligible_days_before, 3)
        self.eligible_days_after = flt(eligible_days_after, 3)
        self.indemnity_before = flt(indemnity_before, 3)
        self.indemnity_after = flt(indemnity_after, 3)
        self.amount = flt(indemnity_before + indemnity_after, 3)

    def _validate_accounts(self):
        if not self.expense_account:
            frappe.throw(_("Please set Expense Account before submitting."))
        if not self.payable_account:
            frappe.throw(_("Please set Payable Account before submitting."))

    def _create_gl_entries(self, cancel=False):
        gl_entries = []
        if self.amount:
            gl_entries.append(
                self.get_gl_dict(
                    {
                        "account": self.expense_account,
                        "debit": self.amount,
                        "debit_in_account_currency": self.amount,
                        "against": self.payable_account,
                        "cost_center": self.cost_center,
                    },
                    item=self,
                )
            )
            gl_entries.append(
                self.get_gl_dict(
                    {
                        "account": self.payable_account,
                        "credit": self.amount,
                        "credit_in_account_currency": self.amount,
                        "against": self.expense_account,
                        "party_type": "Employee",
                        "party": self.employee,
                        "against_voucher_type": self.doctype,
                        "against_voucher": self.name,
                        "cost_center": self.cost_center,
                    },
                    item=self,
                )
            )
        make_gl_entries(gl_entries, cancel)

    def _create_additional_salary(self):
        if not self.salary_component:
            frappe.throw(_("Please set Salary Component to pay via Salary Slip."))
        if not self.payroll_date:
            frappe.throw(_("Please set Payroll Date to pay via Salary Slip."))
        additional_salary = frappe.new_doc("Additional Salary")
        additional_salary.employee = self.employee
        additional_salary.salary_component = self.salary_component
        additional_salary.overwrite_salary_structure_amount = 0
        additional_salary.amount = self.amount
        additional_salary.payroll_date = self.payroll_date
        additional_salary.company = self.company
        additional_salary.ref_doctype = self.doctype
        additional_salary.ref_docname = self.name
        additional_salary.submit()
