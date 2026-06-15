import frappe
from hrms.hr.doctype.appraisal.appraisal import Appraisal as BaseAppraisal


class Appraisal(BaseAppraisal):
    @frappe.whitelist()
    def set_appraisal_template(self):
        # Do not auto-set template from appraisal cycle — user selects manually
        pass

    @frappe.whitelist()
    def set_kras_and_rating_criteria(self):
        if not self.appraisal_template:
            return

        self.set("appraisal_kra", [])
        self.set("self_ratings", [])
        self.set("goals", [])

        template = frappe.get_doc("Appraisal Template", self.appraisal_template)

        for entry in template.goals:
            row_data = {
                "kra": entry.key_result_area,
                "per_weightage": entry.per_weightage,
                "custom_minimum_requirement_out_of_100": entry.get("custom_minimum_requirement_out_of_100") or 0,
            }
            self.append("appraisal_kra", row_data)
            self.append("goals", row_data.copy())

        for entry in template.rating_criteria:
            self.append("self_ratings", {
                "criteria": entry.criteria,
                "per_weightage": entry.per_weightage,
                "custom_minimum_requirement_out_of_100": entry.get("custom_minimum_requirement_out_of_100") or 0,
            })

        return self
