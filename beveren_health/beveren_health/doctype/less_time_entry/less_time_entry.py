# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import frappe
from frappe import _, bold
from frappe.model.document import Document
from frappe.utils.data import format_time, get_link_to_form, getdate
from frappe.utils import cstr, flt, add_months, getdate
from datetime import date
from calendar import monthrange
from hrms.payroll.doctype.payroll_entry.payroll_entry import get_start_end_dates
from hrms.payroll.doctype.salary_structure_assignment.salary_structure_assignment import (
    get_assigned_salary_structure,
)


class LessTimeEntry(Document):
    def validate(self):
        if not (self.start_date or self.end_date):
            self.get_frequency_and_dates()
            
        if self.start_date > self.end_date:
            frappe.throw(_("Start date cannot be greater than end date"))
        
        self.validate_overlap()
        
    def validate_overlap(self):
        less_time_entry = frappe.db.get_all(
            "Less Time Entry",
            filters={
                "docstatus": ("!=", 2),
                "employee": self.employee,
                "end_date": (">=", self.start_date),
                "start_date": ("<=", self.end_date),
                "name": ("!=", self.name),
            },
        )
        if len(less_time_entry):
            form_link = get_link_to_form("Less Time Entry", less_time_entry[0].name)
            msg = _("Less Time Entry:{0} has been created between {1} and {2}").format(
                bold(form_link), bold(self.start_date), bold(self.end_date)
            )
            frappe.throw(msg)
    
    # def on_submit(self):
        # if self.is_less_time_deductible_:
            # self.process_less_time_slip()

    #old one
    # def cadforlte(doc):
    #     doc = frappe.get_doc("Less Time Entry", doc)
    #     if doc.docstatus == 1:
    #         if doc.is_less_time_deductible_:
    #             # if doc.total_overtime_duration <= 0:
    #             #     doc.flags.ignore_mandatory = True
    #             # name, total = doc.fetch_less_time_total(doc.employee, doc.start_date, doc.end_date)
    #             # if name:
    #             #     doc.custom_reference_document = name
    #             # if total:
    #             #     doc.custom_total_less_time_duration = total
    #             #     doc.custom_total_over_time_duration = doc.total_overtime_duration
    #             #     doc.total_overtime_duration = doc.custom_total_over_time_duration - doc.custom_total_less_time_duration
    #             doc.process_less_time_slip()
    
    #new one
    def cadforlte(doc, overtime_slip_name=None):
        doc = frappe.get_doc("Less Time Entry", doc)
        if doc.docstatus == 1:
            if doc.is_less_time_deductible_:
                if overtime_slip_name:
                    frappe.db.set_value(
                        "Less Time Entry", doc.name,
                        "custom_overtime_slip_reference", overtime_slip_name
                    )
                    doc.reload()
                doc.process_less_time_slip()


    @frappe.whitelist()
    def get_frequency_and_dates(self):
        date = self.posting_date
        salary_structure = get_assigned_salary_structure(self.employee, date)
        if salary_structure:
            payroll_frequency = frappe.db.get_value("Salary Structure", salary_structure, "payroll_frequency")
            date_details = get_start_end_dates(
                payroll_frequency, date, frappe.db.get_value("Employee", self.employee, "company")
            )
            start_date = date_details.start_date
            end_date = date_details.end_date
            prev_month_date = add_months(start_date, -1)
            self.start_date = prev_month_date.replace(day=21)
            self.end_date = end_date.replace(day=20)
        else:
            frappe.throw(
                _("Salary Structure not assigned for employee {0} for date {1}").format(
                    self.employee, self.start_date
                )
            )

    @frappe.whitelist()
    def get_emp_and_lesstime_details(self):
        records = self.get_attendance_records()
        if len(records):
            self.create_lesstime_details_row_for_attendance(records)
        if len(self.less_time_details):
            total_less_time_duration = 0.0
            for detail in self.less_time_details:
                if detail.less_time_duration is not None:
                    total_less_time_duration += detail.less_time_duration
            self.total_less_time_duration = total_less_time_duration
        self.save()

    def get_attendance_records(self):
        records = []
        if self.start_date and self.end_date:
            records = frappe.get_all(
                "Attendance",
                fields=[
                    "name",
                    "attendance_date",
                    "custom_less_time_type",
                    "custom_actual_lesstime_duration",
                    "standard_working_hours",
                ],
                filters={
                    "employee": self.employee,
                    "docstatus": 1,
                    "attendance_date": ("between", [getdate(self.start_date), getdate(self.end_date)]),
                    "status": "Present",
                    "custom_less_time_type": ["!=", ""],
                },
            )
            if not len(records):
                frappe.throw(
                    _("No attendance records found for employee {0} between {1} and {2}").format(
                        self.employee, self.start_date, self.end_date
                    )
                )
        return records
    def create_lesstime_details_row_for_attendance(self, records):
        self.less_time_details = []
        lesstime_type_cache = {}

        for record in records:
            less_time_duration = record.custom_actual_lesstime_duration or 0.0
            if less_time_duration > 0:
                self.append(
                    "less_time_details",
                    {
                        "reference_document": record.name,
                        "date": record.attendance_date,
                        "less_time_type": record.custom_less_time_type,
                        "less_time_duration": less_time_duration,
                        "standard_working_hours": record.standard_working_hours,
                    },
                )
                
    def process_less_time_slip(self):
        less_time_components = self.get_less_time_component_amounts()
        precision = frappe.db.get_single_value("System Settings", "currency_precision") or 2
        for component, total_amount in less_time_components.items():
            self.create_additional_salary(component, total_amount, precision)
   
    def get_less_time_component_amounts(self):
        print(self.less_time_details)
        if not self.less_time_details:
            return {}

        unique_less_time_types = {detail.less_time_type for detail in self.less_time_details}
        self.less_time_types = self._bulk_load_less_time_types(unique_less_time_types)
        less_time_components = {}
        
        for less_time_detail in self.less_time_details:
            less_time_type = less_time_detail.less_time_type
            applicable_hourly_rate = self._get_applicable_hourly_rate(
                less_time_type, less_time_detail.get("standard_working_hours")
            )

            less_time_amount = self.calculate_less_time_amount(
                less_time_type,
                applicable_hourly_rate,
                less_time_detail.less_time_duration,
                less_time_detail.date
            )

            salary_component = self.less_time_types[less_time_type]["less_time_salary_component"]
            less_time_components[salary_component] = (
                less_time_components.get(salary_component, 0) + less_time_amount
            )

        return less_time_components
    
    def create_additional_salary(self, salary_component, total_amount, precision=None):
        payroll_date = date(getdate(self.end_date).year, getdate(self.end_date).month, 28)
        if total_amount > 0:
            additional_salary = frappe.get_doc(
                {
                    "doctype": "Additional Salary",
                    "company": self.company,
                    "employee": self.employee,
                    "salary_component": salary_component,
                    "amount": flt(total_amount, precision),
                    "payroll_date": payroll_date,
                    "overwrite_salary_structure_amount": 0,
                    "ref_doctype": "Less Time Entry",
                    "ref_docname": self.name,
                }
            )
            additional_salary.submit()
    
    def _get_applicable_hourly_rate(self, less_time_type, standard_working_hours=0):
        less_time_details = self.less_time_types[less_time_type]
        less_time_amount_calculation = less_time_details["less_time_amount_calculation"]

        applicable_hourly_rate = 0.0
        if less_time_amount_calculation == "Fixed Hourly Rate":
            applicable_hourly_rate = less_time_details.get("hourly_rate", 0.0)
        elif less_time_amount_calculation == "Salary Component Based":
            applicable_hourly_rate = self._calculate_component_based_hourly_rate(
                less_time_type, standard_working_hours
            )
        print(applicable_hourly_rate)
        return applicable_hourly_rate
    
    def _calculate_component_based_hourly_rate(self, less_time_type, standard_working_hours):
        components = self.less_time_types[less_time_type]["components"] or []
        if not hasattr(self, "_cached_salary_slip"):
            salary_structure = get_assigned_salary_structure(self.employee, self.start_date)
            self._cached_salary_slip = self._make_salary_slip(salary_structure)

        if not components or not hasattr(self, "_cached_salary_slip"):
            return 0.0

        component_amount = sum(
            data.amount
            for data in self._cached_salary_slip.earnings
            if data.salary_component in components and not data.get("additional_salary", None)
        )
        # payment_days = max(self._cached_salary_slip.payment_days, 1)
        # applicable_daily_amount = component_amount / payment_days
        applicable_daily_amount = component_amount / 30

        return applicable_daily_amount / standard_working_hours
    
    def _make_salary_slip(self, salary_structure):
        from hrms.payroll.doctype.salary_structure.salary_structure import make_salary_slip

        return make_salary_slip(
            salary_structure,
            employee=self.employee,
            ignore_permissions=True,
            posting_date=self.start_date,
        )
        
    def calculate_less_time_amount(self, less_time_type, applicable_hourly_rate, less_time_duration, less_time_date):
        less_time_details = self.less_time_types.get(less_time_type)
        if not less_time_details:
            return 0.0

        if applicable_hourly_rate <= 0:
            return 0.0

        amount = less_time_duration * applicable_hourly_rate 
        return amount
    
    def _bulk_load_less_time_types(self, less_time_type_names):
        if not less_time_type_names:
            return {}

        print("Hello\n\n\n\n\n\n\n\n\n\n")
        less_time_types_data = frappe.get_all(
            "Less Time Type",
            filters={"name": ["in", list(less_time_type_names)]},
            fields=[
                "name",
                "less_time_salary_component",
                "less_time_amount_calculation",
                "hourly_rate",
            ],
        )

        less_time_types = {}
        salary_component_based_types = []

        for lt_data in less_time_types_data:
            less_time_types[lt_data.name] = lt_data
            if lt_data.less_time_amount_calculation == "Salary Component Based":
                salary_component_based_types.append(lt_data.name)

        # Bulk load salary components for salary component based types
        if salary_component_based_types:
            salary_components_data = frappe.get_all(
                "Overtime Salary Component",
                filters={"parent": ["in", salary_component_based_types]},
                fields=["parent", "salary_component"],
            )

            # Group by parent
            components_by_parent = {}
            for comp_data in salary_components_data:
                if comp_data.parent not in components_by_parent:
                    components_by_parent[comp_data.parent] = []
                components_by_parent[comp_data.parent].append(comp_data.salary_component)

            for lt_type in salary_component_based_types: 
                less_time_types[lt_type]["components"] = components_by_parent.get(lt_type, [])

        return less_time_types
    