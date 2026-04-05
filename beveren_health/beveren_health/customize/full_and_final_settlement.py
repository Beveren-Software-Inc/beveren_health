import frappe
from frappe.utils import add_days, flt
from dateutil.relativedelta import relativedelta
from datetime import date
from frappe.utils.safe_exec import safe_eval

def before_save(self, method):
    # --- Calculate total experience ---
    relieving_date = add_days(self.relieving_date, 1)
    rd = relativedelta(relieving_date, self.date_of_joining)
    years, months, days = rd.years, rd.months, rd.days
    self.custom_total_experience = f"{years} years {months} months and {days} days"

    cutoff_date = date(2024, 4, 1)

    # --- Fetch active Salary Structure Assignment ---
    assignment = frappe.db.get_value(
        "Salary Structure Assignment",
        {"employee": self.employee, "docstatus": 1},
        ["salary_structure", "from_date", "base"],
        order_by="from_date desc",
        as_dict=True
    )
    if not assignment:
        frappe.throw("No Active Salary Structure Assignment")

    structure = frappe.get_doc("Salary Structure", assignment.salary_structure)
    base = assignment.base

    ir_base_before_cutoff_date = 0
    ir_base_after_cutoff_date = 0

    # --- Evaluate each earning component ---
    for earning in structure.earnings:
        component = frappe.get_doc("Salary Component", earning.salary_component)

        # Prepare context for formula
        context = {
            "doc": self,
            "flt": flt,
            "base": base
        }

        # Calculate component amount
        amount = earning.amount
        if component.amount_based_on_formula and component.formula:
            try:
                amount = safe_eval(component.formula, context)
            except Exception as e:
                frappe.throw(f"Error evaluating formula for {component.salary_component}: {e}")

        # Add to IR base based on whether it's basic or not
        if component.custom_is_basic_salary_:
            ir_base_before_cutoff_date += amount
        else:
            ir_base_after_cutoff_date += amount

    # --- Determine final IR base ---
    if self.date_of_joining < cutoff_date:
        ir_base = ir_base_before_cutoff_date + ir_base_after_cutoff_date
    else:
        ir_base = ir_base_after_cutoff_date

    self.custom_ir_base = ir_base

    # --- Calculate total months worked ---
    total_months = (self.relieving_date.year - self.date_of_joining.year) * 12 + \
                   (self.relieving_date.month - self.date_of_joining.month) + 1

    # --- Calculate indemnity ---
    if years <= 3:
        indemnity = ir_base * total_months / 24
    else:
        indemnity = (ir_base * 3 / 2) + (ir_base * (total_months - 3) / 24)

    self.custom_indemnity_reward = flt(indemnity, 2)