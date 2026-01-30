# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import frappe
from datetime import date
from frappe.utils import getdate, add_months, flt
from frappe.model.document import Document


class LessTimeCompensation(Document):
    
	def before_save(doc):
		total_less_time = 0.0
		total_overtime = 0.0
		for row in doc.less_time_compensation_details:
			total_less_time += row.less_time_duration or 0.0
			total_overtime += row.overtime_duration or 0.0

			doc.total_less_time_duration = total_less_time
			doc.total_overtime_duration = total_overtime
			doc.uncompensated_duration = total_less_time - total_overtime

	def on_submit(doc):
		doc.create_additional_salary()

	def create_additional_salary(doc):
		salary_component = doc.salary_component
		precision = frappe.db.get_single_value("System Settings", "currency_precision") or 2
		total_amount = doc.uncompensated_duration * doc.hourly_rate
		payroll_date = date(getdate(doc.to_date).year, getdate(doc.to_date).month + 1, 28)
		if total_amount > 0:
			additional_salary = frappe.get_doc(
				{
					"doctype": "Additional Salary",
					"company": doc.company,
					"employee": doc.employee,
					"salary_component": salary_component,
					"amount": flt(total_amount, precision),
					"payroll_date": payroll_date,
					"overwrite_salary_structure_amount": 0,
					"ref_doctype": "Less Time Compensation",
					"ref_docname": doc.name,
				}
			)
			additional_salary.submit()


@frappe.whitelist()
def get_compensation_data(from_date, to_date, employee):
    result = []
    prev_month_date = add_months(getdate(from_date), -1)
    lt_start_date = prev_month_date.replace(day=21)
    lt_end_date = getdate(to_date).replace(day=20)
    # Less Time Entries
    less_time_entries = frappe.get_all(
        "Less Time Entry",
        filters={
            "employee": employee,
            "start_date": ["between", [lt_start_date, lt_end_date]],
            "docstatus": 1
        },
        fields=["name", "start_date", "end_date", "total_less_time_duration"]
    )

    for d in less_time_entries:
        result.append({
            "reference_doctype": "Less Time Entry",
            "reference_name": d.name,
            "from_date": d.start_date,
            "to_date": d.end_date,
            "less_time_duration": float(d.total_less_time_duration or 0),
            "overtime_duration": 0.0
        })

    # Overtime Slips
    overtime_slips = frappe.get_all(
        "Overtime Slip",
        filters={
            "employee": employee,
            "start_date": ["between", [from_date, to_date]],
            "docstatus": 1
        },
        fields=["name", "start_date", "end_date", "total_overtime_duration"]
    )

    for d in overtime_slips:
        result.append({
            "reference_doctype": "Overtime Slip",
            "reference_name": d.name,
            "from_date": d.start_date,
            "to_date": d.end_date,
            "less_time_duration": 0.0,
            "overtime_duration": float(d.total_overtime_duration or 0)
        })

    # Sort by from_date if you want
    result.sort(key=lambda x: x["from_date"])
    print(result)
    return result


