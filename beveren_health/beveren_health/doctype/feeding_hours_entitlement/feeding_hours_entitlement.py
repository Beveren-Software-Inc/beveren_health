# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import add_months, getdate, today


def _hours_for(child_dob, on_date):
	"""Daily paid feeding hours for a child of the given DOB on a given date.

	2h/day while the child is under 6 months, 1h/day from 6 to 12 months, 0 after.
	"""
	if not child_dob or not on_date:
		return 0.0
	child_dob = getdate(child_dob)
	on_date = getdate(on_date)
	if on_date < child_dob:
		return 0.0
	if on_date < add_months(child_dob, 6):
		return 2.0
	if on_date < add_months(child_dob, 12):
		return 1.0
	return 0.0


class FeedingHoursEntitlement(Document):
	def validate(self):
		if self.child_dob:
			self.entitlement_start = getdate(self.child_dob)
			self.entitlement_end = add_months(getdate(self.child_dob), 12)
		self.current_hours_per_day = _hours_for(self.child_dob, today())
		self.status = "Active" if self.current_hours_per_day > 0 else "Expired"


def get_feeding_hours(employee, on_date):
	"""Return the daily feeding-hours entitlement (2h / 1h / 0) for an employee on a date.

	Used by the Attendance before_insert hook to reduce standard working hours so the
	less-time engine does not dock a nursing mother's entitled paid break.
	"""
	if not employee or not on_date:
		return 0.0
	best = 0.0
	for row in frappe.get_all(
		"Feeding Hours Entitlement",
		filters={"employee": employee},
		fields=["child_dob"],
	):
		best = max(best, _hours_for(row.child_dob, on_date))
	return best
