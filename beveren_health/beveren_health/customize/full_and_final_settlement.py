import frappe
from frappe.utils import add_days, flt
from dateutil.relativedelta import relativedelta
from datetime import date
from frappe.utils.safe_exec import safe_eval


# def before_save(self, method):
#     relieving_date = add_days(self.relieving_date, 1)
#     rd = relativedelta(relieving_date, self.date_of_joining)
#     years, months, days = rd.years, rd.months, rd.days
#     self.custom_total_experience = f"{years} years {months} months and {days} days"
#     cutoff_date = date(2024, 3, 1)
#     assignment = frappe.db.get_value(
#         "Salary Structure Assignment",
#         {"employee": self.employee, "docstatus": 1},
#         ["salary_structure", "from_date", "base"],
#         order_by="from_date desc",
#         as_dict=True
#     )
#     if not assignment:
#         frappe.throw("No Active Salary Structure Assignment")
#     structure = frappe.get_doc("Salary Structure", assignment.salary_structure)
#     base = assignment.base
#     if self.custom_consider_full_salary:
#         ir_base_seg1 = base
#         ir_base_seg2 = base
#     else:
#         ir_base_before_cutoff_date = 0
#         ir_base_after_cutoff_date = 0
#         for earning in structure.earnings:
#             component = frappe.get_doc("Salary Component", earning.salary_component)
#             context = {
#                 "doc": self,
#                 "flt": flt,
#                 "base": base
#             }
#             amount = earning.amount
#             if component.amount_based_on_formula and component.formula:
#                 try:
#                     amount = safe_eval(component.formula, context)
#                 except Exception as e:
#                     frappe.throw(f"Error evaluating formula for {component.salary_component}: {e}")

#             if component.custom_is_basic_salary_:
#                 ir_base_after_cutoff_date += amount
#             else:
#                 ir_base_before_cutoff_date += amount
#             ir_base_seg1 = ir_base_before_cutoff_date + ir_base_after_cutoff_date
#             ir_base_seg2 = ir_base_after_cutoff_date
#     def get_eligible_days(total_days):
#         if total_days <= 0:
#             return 0
#         if total_days <= 1095:
#             return total_days * 15 / 365
#         else:
#             return 45 + ((total_days - 1095) * 30 / 365)
#     if self.date_of_joining < cutoff_date:
#         seg1_end  = date(2024, 2, 29)
#         seg1_days = (seg1_end - self.date_of_joining).days + 1
#         total_days_full    = (self.relieving_date - self.date_of_joining).days + 1
#         eligible_days_seg1 = get_eligible_days(seg1_days)
#         eligible_days_seg2 = get_eligible_days(total_days_full) - get_eligible_days(seg1_days)
#         indemnity = (ir_base_seg1 * 12 * eligible_days_seg1 / 365) + \
#                     (ir_base_seg2 * 12 * eligible_days_seg2 / 365)
#     else:
#         total_days    = (self.relieving_date - self.date_of_joining).days + 1
#         eligible_days = get_eligible_days(total_days)
#         indemnity     = ir_base_seg2 * 12 * eligible_days / 365
#     if not indemnity:
#         return
#     found = False
#     for row in self.payables:
#         if row.component == "Indemnity Reward":
#             row.amount = flt(indemnity, 3)
#             row.status = "Settled"
#             found = True
#             break
#     if not found:
#         self.append("payables", {
#             "component": "Indemnity Reward",
#             "amount": flt(indemnity, 3),
#             "status": "Settled"
#         })



# def before_save(self, method):

#     relieving_date = add_days(self.relieving_date, 1)
#     rd = relativedelta(relieving_date, self.date_of_joining)
#     years, months, days = rd.years, rd.months, rd.days
#     self.custom_total_experience = f"{years} years {months} months and {days} days"

#     cutoff_date = date(2024, 3, 1)
#     assignment = frappe.db.get_value(
#         "Salary Structure Assignment",
#         {"employee": self.employee, "docstatus": 1},
#         ["salary_structure", "from_date", "base"],
#         order_by="from_date desc",
#         as_dict=True
#     )
#     if not assignment:
#         frappe.throw("No Active Salary Structure Assignment")

#     structure = frappe.get_doc("Salary Structure", assignment.salary_structure)
#     base = assignment.base

#     basic_salary = 0
#     for earning in structure.earnings:
#         component = frappe.get_doc("Salary Component", earning.salary_component)
#         if not component.custom_is_basic_salary_:
#             continue
#         amount = earning.amount
#         if component.amount_based_on_formula and component.formula:
#             context = {"doc": self, "flt": flt, "base": base}
#             try:
#                 amount = safe_eval(component.formula, context)
#             except Exception as e:
#                 frappe.throw(f"Error evaluating formula for {component.salary_component}: {e}")
#         basic_salary += amount
#     if not basic_salary:
#         frappe.throw("Basic Salary component not found or evaluates to zero in the Salary Structure.")
#     self.custom_basic_salary = basic_salary or 0

#     def get_eligible_days(total_days):
#         if total_days <= 0:
#             return 0
#         if total_days <= 1095:
#             return total_days * 15 / 365
#         else:
#             return 45 + ((total_days - 1095) * 30 / 365)

#     # --- Calculate indemnity split by cutoff ---
#     indemnity_before = 0.0
#     indemnity_after  = 0.0

#     if self.date_of_joining < cutoff_date:
#         seg1_end  = date(2024, 2, 29)
#         seg1_days = (seg1_end - self.date_of_joining).days + 1
#         seg2_start = cutoff_date
#         seg2_days  = (self.relieving_date - seg2_start).days + 1
#         total_days_full = (self.relieving_date - self.date_of_joining).days + 1
#         eligible_days_seg1 = get_eligible_days(seg1_days)
#         eligible_days_seg2 = get_eligible_days(total_days_full) - get_eligible_days(seg1_days)
#         indemnity_before = basic_salary * 12 * eligible_days_seg1 / 365
#         indemnity_after  = basic_salary * 12 * eligible_days_seg2 / 365
#     else:
#         total_days    = (self.relieving_date - self.date_of_joining).days + 1
#         eligible_days = get_eligible_days(total_days)
#         indemnity_after = basic_salary * 12 * eligible_days / 365
#     LABEL_BEFORE = "Indemnity Reward (Before Cut-Off Date)"
#     LABEL_AFTER  = "Indemnity Reward (After Cut-Off Date)"

#     # --- Update or append each indemnity row ---
#     def upsert_payable(label, amount):
#         """Update existing row if found, otherwise append a new one."""
#         for row in self.payables:
#             if row.component == label:
#                 row.amount = flt(amount, 3)
#                 row.status = "Settled"
#                 return
#         self.append("payables", {
#             "component": label,
#             "amount":    flt(amount, 3),
#             "status":    "Settled"
#         })

#     if indemnity_before:
#         upsert_payable(LABEL_BEFORE, indemnity_before)

#     if indemnity_after:
#         upsert_payable(LABEL_AFTER, indemnity_after)

def before_save(self, method):

    relieving_date = add_days(self.relieving_date, 1)
    rd = relativedelta(relieving_date, self.date_of_joining)
    years, months, days = rd.years, rd.months, rd.days
    self.custom_total_experience = f"{years} years {months} months and {days} days"

    cutoff_date = date(2024, 3, 1)
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
    
    self.custom_base_salary = base
    
    # --- Compute basic salary from structure ---
    basic_salary = 0.0
    for earning in structure.earnings:
        component = frappe.get_doc("Salary Component", earning.salary_component)
        if not component.custom_is_basic_salary_:
            continue
        amount = earning.amount
        if component.amount_based_on_formula and component.formula:
            context = {"doc": self, "flt": flt, "base": base}
            try:
                amount = safe_eval(component.formula, context)
            except Exception as e:
                frappe.throw(f"Error evaluating formula for {component.salary_component}: {e}")
        basic_salary += amount

    if not basic_salary:
        frappe.throw("Basic Salary component not found or evaluates to zero in the Salary Structure.")

    self.custom_basic_salary = basic_salary

    # Seg-1 (before cutoff) → always base (full salary)
    ir_base_before = base

    # Seg-2 (after cutoff) → checkbox decides between base or basic
    ir_base_after = base if self.custom_consider_full_salary_after_cutoff_date else basic_salary

    # --- Eligible days calculator (UAE Labour Law) ---
    def get_eligible_days(total_days):
        if total_days <= 0:
            return 0
        if total_days <= 1095:
            return total_days * 15 / 365
        else:
            return 45 + ((total_days - 1095) * 30 / 365)

    # --- Calculate indemnity split by cutoff ---
    indemnity_before = 0.0
    indemnity_after  = 0.0

    if self.date_of_joining < cutoff_date:
        seg1_end        = date(2024, 2, 29)
        seg1_days       = (seg1_end - self.date_of_joining).days + 1
        total_days_full = (self.relieving_date - self.date_of_joining).days + 1

        eligible_days_seg1 = get_eligible_days(seg1_days)
        eligible_days_seg2 = get_eligible_days(total_days_full) - get_eligible_days(seg1_days)

        indemnity_before = ir_base_before * 12 * eligible_days_seg1 / 365
        indemnity_after  = ir_base_after  * 12 * eligible_days_seg2 / 365
    else:
        # Joined on/after cutoff — no "before" segment
        total_days    = (self.relieving_date - self.date_of_joining).days + 1
        eligible_days = get_eligible_days(total_days)
        indemnity_after = ir_base_after * 12 * eligible_days / 365

    LABEL_BEFORE = "Indemnity Reward (Before Cut-Off Date)"
    LABEL_AFTER  = "Indemnity Reward (After Cut-Off Date)"

    def upsert_payable(label, amount):
        for row in self.payables:
            if row.component == label:
                row.amount = flt(amount, 3)
                row.status = "Settled"
                return
        self.append("payables", {
            "component": label,
            "amount":    flt(amount, 3),
            "status":    "Settled"
        })

    if indemnity_before:
        upsert_payable(LABEL_BEFORE, indemnity_before)

    if indemnity_after:
        upsert_payable(LABEL_AFTER, indemnity_after)
    