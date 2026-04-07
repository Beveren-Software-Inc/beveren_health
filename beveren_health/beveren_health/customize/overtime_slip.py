import frappe
from datetime import date
from frappe.utils import cstr, flt, add_months, getdate
from hrms.hr.doctype.overtime_slip.overtime_slip import OvertimeSlip as BaseOvertimeSlip
from hrms.payroll.doctype.salary_structure_assignment.salary_structure_assignment import (
	get_assigned_salary_structure,
)
from beveren_health.beveren_health.doctype.less_time_entry.less_time_entry import LessTimeEntry as LTE

class OvertimeSlip(BaseOvertimeSlip):
    def before_submit(self):
        if self.total_overtime_duration <= 0:
            self.flags.ignore_mandatory = True
        name, total = self.fetch_less_time_total(self.employee, self.start_date, self.end_date)
        if name:
            self.custom_reference_document = name
        if total:
            self.custom_total_less_time_duration = total
            self.custom_total_over_time_duration = self.total_overtime_duration
            self.total_overtime_duration = self.custom_total_over_time_duration - self.custom_total_less_time_duration
        
    def on_submit(self):
        if self.total_overtime_duration < 0:
            LTE.cadforlte(self.name, self.custom_reference_document, self.total_overtime_duration)
        else:
            if self.custom_is_overtime_payable_:
                self.process_overtime_slip()
        
        
    def process_overtime_slip(self):
        overtime_components = self.get_overtime_component_amounts()
        precision = frappe.db.get_single_value("System Settings", "currency_precision") or 2
        for component, total_amount in overtime_components.items():
            self.create_additional_salary(component, total_amount, precision)
   
    def get_overtime_component_amounts(self):
        if not self.overtime_details:
            return {}

        unique_overtime_types = {detail.overtime_type for detail in self.overtime_details}

        self.overtime_types = self._bulk_load_overtime_types(unique_overtime_types)
        holiday_date_map = self.get_holiday_map()
        overtime_components = {}

        for overtime_detail in self.overtime_details:
            overtime_type = overtime_detail.overtime_type
            applicable_hourly_rate = self._get_applicable_hourly_rate(
                overtime_type, overtime_detail.get("standard_working_hours")
            )

            overtime_amount = self.calculate_overtime_amount(
                overtime_type,
                applicable_hourly_rate,
                overtime_detail.overtime_duration,
                overtime_detail.date,
                holiday_date_map,
            )

            salary_component = self.overtime_types[overtime_type]["overtime_salary_component"]
            overtime_components[salary_component] = (
                overtime_components.get(salary_component, 0) + overtime_amount
            )

        return overtime_components
    
    def create_additional_salary(self, salary_component, total_amount, precision=None):
        next_month_date = add_months(getdate(self.end_date), 1)
        payroll_date = date(next_month_date.year, next_month_date.month, 28)
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
                    "ref_doctype": "Overtime Slip",
                    "ref_docname": self.name,
                }
            )
            additional_salary.submit()
    
    def _get_applicable_hourly_rate(self, overtime_type, standard_working_hours=0):
        overtime_details = self.overtime_types[overtime_type]
        overtime_calculation_method = overtime_details["overtime_calculation_method"]

        applicable_hourly_rate = 0.0
        if overtime_calculation_method == "Fixed Hourly Rate":
            applicable_hourly_rate = overtime_details.get("hourly_rate", 0.0)
        elif overtime_calculation_method == "Salary Component Based":
            applicable_hourly_rate = self._calculate_component_based_hourly_rate(
                overtime_type, standard_working_hours
            )
        print(applicable_hourly_rate)
        return applicable_hourly_rate
    
    def _calculate_component_based_hourly_rate(self, overtime_type, standard_working_hours):
        components = self.overtime_types[overtime_type]["components"] or []
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
        
    def calculate_overtime_amount(self, overtime_type, applicable_hourly_rate, overtime_duration, overtime_date, holiday_date_map):
        overtime_details = self.overtime_types.get(overtime_type)
        if not overtime_details:
            return 0.0

        if applicable_hourly_rate <= 0:
            return 0.0

        overtime_date_str = cstr(overtime_date)
        multiplier = overtime_details.get("standard_multiplier", 1)
        multiplier_after_cutoff_hours = overtime_details.get("custom_rate_change_multiplier", multiplier)
        holiday_info = holiday_date_map.get(overtime_date_str)
        if holiday_info:
            if overtime_details.get("applicable_for_weekend") and holiday_info.weekly_off:
                multiplier = overtime_details.get("weekend_multiplier", multiplier)
            elif overtime_details.get("applicable_for_public_holiday") and not holiday_info.weekly_off:
                multiplier = overtime_details.get("public_holiday_multiplier", multiplier)
        if overtime_duration <= overtime_details.get("custom_rate_change_cutoff_hours", multiplier):
            amount = overtime_duration * applicable_hourly_rate * multiplier
        else:
            amount = overtime_details.get("custom_rate_change_cutoff_hours") * applicable_hourly_rate * multiplier
            amount += (overtime_duration - overtime_details.get("custom_rate_change_cutoff_hours")) * applicable_hourly_rate * multiplier_after_cutoff_hours
        return amount
    
    def _bulk_load_overtime_types(self, overtime_type_names):
        """
        Load all overtime type details in bulk
        """
        if not overtime_type_names:
            return {}

        # Get all overtime types details
        overtime_types_data = frappe.get_all(
            "Overtime Type",
            filters={"name": ["in", list(overtime_type_names)]},
            fields=[
                "name",
                "custom_rate_change_cutoff_hours",
                "standard_multiplier",
                "custom_rate_change_multiplier",
                "weekend_multiplier",
                "public_holiday_multiplier",
                "applicable_for_weekend",
                "applicable_for_public_holiday",
                "overtime_salary_component",
                "overtime_calculation_method",
                "hourly_rate",
            ],
        )

        overtime_types = {}
        salary_component_based_types = []

        for ot_data in overtime_types_data:
            overtime_types[ot_data.name] = ot_data
            if ot_data.overtime_calculation_method == "Salary Component Based":
                salary_component_based_types.append(ot_data.name)

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

            for ot_type in salary_component_based_types:  # Add components to overtime types
                overtime_types[ot_type]["components"] = components_by_parent.get(ot_type, [])

        return overtime_types

    def fetch_less_time_total(self, employee, start_date, end_date):
        start_date = getdate(start_date)
        end_date = getdate(end_date)
        prev_month_21 = add_months(start_date, -1).replace(day=21)
        curr_month_20 = end_date.replace(day=20)
        name = frappe.db.get_value("Less Time Entry", {
            "employee" : employee,
            "start_date" : prev_month_21,
            "end_date" : curr_month_20,
            "is_less_time_deductible_" : 1,
            "docstatus" : 1
            }, "name")
        total = frappe.db.get_value("Less Time Entry", {
            "employee" : employee,
            "start_date" : prev_month_21,
            "end_date" : curr_month_20,
            "is_less_time_deductible_" : 1,
            "docstatus" : 1
            }, "total_less_time_duration_1")
        return name, total