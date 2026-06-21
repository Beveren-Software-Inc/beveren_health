import frappe
from frappe import _
from frappe.model.document import Document


class EmployeeVisaRenewalConsent(Document):
    def validate(self):
        self._validate_renewal_period()
        self._set_status()

    def on_submit(self):
        self.db_set("status", "Submitted")

    def on_cancel(self):
        self.db_set("status", "Cancelled")

    def _validate_renewal_period(self):
        if self.renewal_decision == "Renew" and not self.renewal_period:
            frappe.throw(_("Please select the Renewal Period for the visa renewal request."))
        if self.renewal_decision == "Not Renew":
            self.renewal_period = None

    def _set_status(self):
        if self.docstatus == 0:
            self.status = "Draft"
        elif self.docstatus == 1:
            self.status = "Submitted"
        elif self.docstatus == 2:
            self.status = "Cancelled"
