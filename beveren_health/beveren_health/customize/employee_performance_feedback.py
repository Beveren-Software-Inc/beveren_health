import frappe
from hrms.hr.doctype.employee_performance_feedback.employee_performance_feedback import (
    EmployeePerformanceFeedback as BaseEmployeePerformanceFeedback,
)


class EmployeePerformanceFeedback(BaseEmployeePerformanceFeedback):
    @frappe.whitelist()
    def set_feedback_criteria(self):
        if not self.appraisal:
            return

        template_name = frappe.db.get_value("Appraisal", self.appraisal, "appraisal_template")
        if not template_name:
            return

        template = frappe.get_doc("Appraisal Template", template_name)

        self.set("feedback_ratings", [])
        for entry in template.rating_criteria:
            self.append("feedback_ratings", {
                "criteria": entry.criteria,
                "per_weightage": entry.per_weightage,
                "custom_minimum_requirement_out_of_100": entry.get("custom_minimum_requirement_out_of_100") or 0,
            })

        return self
