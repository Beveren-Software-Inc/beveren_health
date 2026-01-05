import frappe
from frappe import _
from frappe.utils import flt, getdate, add_days
from dateutil.relativedelta import relativedelta
from datetime import date
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip

def before_save(self, method):
    ss = SalarySlip()
    relieving_date = add_days(self.relieving_date, 1)
    rd = relativedelta(relieving_date, self.date_of_joining)
    years, months, days = rd.years, rd.months, rd.days
    self.custom_total_experience = "{years} years {months} months and {days} days".format(
        years=years, months=months, days=days)
    cutoff_date = date(2024, 4, 1)
    assignment = frappe.db.get_value(
        "Salary Structure Assignment",
        {
            "employee": self.employee,
            "docstatus": 1
        },
        ["salary_structure", "from_date", "base"],
        order_by="from_date desc",
        as_dict=True
    )
    if not assignment:
        frappe.throw("No Active Salary Structure Assignment")
    
    structure = frappe.get_doc("Salary Structure", assignment.salary_structure)
    
    ir_base_before_cutoff_date = 0
    ir_base_after_cutoff_date = 0
    base = assignment.base
    for earning in structure.earnings:
        component = frappe.get_doc("Salary Component", earning.salary_component)
        if component.custom_is_basic_salary_:
            if component.amount_based_on_formula:
                ir_base_before_cutoff_date += ss.eval_condition_and_formula(self, "earnings", component.formula)
            else:
                ir_base_before_cutoff_date += earning.amount
        else:
            if component.amount_based_on_formula:
                ir_base_after_cutoff_date += ss.eval_condition_and_formula(self, "earnings", component.formula)
                ir_base_after_cutoff_date += earning.amount
            
    if self.date_of_joining < cutoff_date:
        ir_base = ir_base_before_cutoff_date + ir_base_after_cutoff_date
    else:
        ir_base = ir_base_after_cutoff_date

    self.custom_ir_base = ir_base
    
    total_months = (self.relieving_date.year - self.date_of_joining.year) * 12 + (self.relieving_date.month - self.date_of_joining.month) + 1

    if years <= 3:
        indemnity = ir_base * total_months / 24
    else:
        indemnity = (ir_base * 3 / 2) + (ir_base * (total_months - 3) / 24)

    self.custom_indemnity_reward = indemnity

