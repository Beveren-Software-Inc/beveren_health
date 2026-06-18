import frappe
from frappe import _


class FullandFinalStatement:
    def validate(self):
        self._validate_unique_fnf()
        super().validate()

    def get_payable_component(self):
        return ["Expense Claim", "Bonus", "Leave Encashment"]

    def _validate_unique_fnf(self):
        if not self.date_of_joining or not self.relieving_date:
            return
        existing = frappe.db.get_value(
            "Full and Final Statement",
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
                    "A Full and Final Statement {0} already exists for employee {1} "
                    "for the same joining and relieving period."
                ).format(
                    frappe.bold(frappe.get_desk_link("Full and Final Statement", existing)),
                    frappe.bold(self.employee),
                )
            )
