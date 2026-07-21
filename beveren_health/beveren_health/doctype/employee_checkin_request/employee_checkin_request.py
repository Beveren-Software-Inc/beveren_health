# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt
"""Employee Checkin Request - a missed IN/OUT punch, raised by staff, approved by HR.

Attendance Request does not cover this: it works on whole dates and produces
Attendance, so it cannot express "my 08:02 IN punch on Tuesday never registered".
This raises the punch itself, and on approval creates the Employee Checkin with a
reference back to the request that authorised it.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, getdate, now_datetime

# Fieldname on Employee Checkin that points back at the approved request.
CHECKIN_LINK_FIELD = "custom_checkin_request"


class EmployeeCheckinRequest(Document):
	def validate(self):
		self._validate_employee()
		self._validate_time()
		self._validate_duplicate()
		self._set_shift_from_assignment()
		if self.docstatus == 0 and self.status not in ("Draft", "Pending Approval"):
			self.status = "Draft"

	def on_submit(self):
		approver = frappe.session.user
		approved_on = now_datetime()

		# A workflow may submit this as Rejected; only an approval creates a punch.
		if self.status == "Rejected":
			self.db_set({"approver": approver, "approved_on": approved_on})
			return

		checkin = self._create_checkin()
		self.db_set(
			{
				"status": "Approved",
				"approver": approver,
				"approved_on": approved_on,
				"employee_checkin": checkin,
			}
		)

	def on_cancel(self):
		# Employee Checkin is not submittable, so an approved punch is removed
		# outright rather than cancelled - otherwise the attendance it feeds would
		# keep counting a punch that is no longer authorised.
		if self.employee_checkin and frappe.db.exists("Employee Checkin", self.employee_checkin):
			attendance = frappe.db.get_value("Employee Checkin", self.employee_checkin, "attendance")
			if attendance:
				frappe.throw(
					_(
						"Cannot cancel: the punch is already linked to Attendance {0}. "
						"Cancel that Attendance first."
					).format(frappe.get_desk_link("Attendance", attendance))
				)
			frappe.delete_doc(
				"Employee Checkin", self.employee_checkin, force=1, ignore_permissions=True
			)
		self.db_set({"status": "Cancelled", "employee_checkin": None})

	# ------------------------------------------------------------------ helpers
	def _validate_employee(self) -> None:
		status = frappe.db.get_value("Employee", self.employee, "status")
		if status and status != "Active":
			frappe.throw(
				_("{0} is {1}. A checkin request can only be raised for an active employee.").format(
					frappe.bold(self.employee_name or self.employee), status
				)
			)

	def _validate_time(self) -> None:
		if not self.request_time:
			return

		if get_datetime(self.request_time) > now_datetime():
			frappe.throw(_("Punch Time cannot be in the future."))

		doj = frappe.db.get_value("Employee", self.employee, "date_of_joining")
		if doj and getdate(self.request_time) < getdate(doj):
			frappe.throw(
				_("Punch Time is before the employee's joining date {0}.").format(frappe.bold(str(doj)))
			)

	def _validate_duplicate(self) -> None:
		existing = frappe.db.exists(
			self.doctype,
			{
				"employee": self.employee,
				"log_type": self.log_type,
				"request_time": self.request_time,
				"docstatus": ["<", 2],
				"name": ["!=", self.name or ""],
			},
		)
		if existing:
			frappe.throw(
				_("{0} already requests a {1} punch for this employee at {2}.").format(
					frappe.get_desk_link(self.doctype, existing), self.log_type, self.request_time
				)
			)

		if frappe.db.exists(
			"Employee Checkin",
			{"employee": self.employee, "log_type": self.log_type, "time": self.request_time},
		):
			frappe.throw(
				_("A {0} punch already exists for this employee at {1}.").format(
					self.log_type, self.request_time
				)
			)

	def _set_shift_from_assignment(self) -> None:
		"""Resolve the shift from the employee's Shift Assignment for that date.

		The field is read-only on the form: staff state when the punch happened,
		not which shift it belonged to. Recomputed on every save so correcting the
		punch time re-resolves the shift, and so a request cannot carry a shift the
		employee was never assigned. Falls back to nothing rather than to
		Employee.default_shift - guessing the shift on a document that feeds
		attendance would be worse than leaving it for hrms to resolve on the punch.
		"""
		self.shift = None
		if not (self.employee and self.request_time):
			return

		punch_date = getdate(self.request_time)
		assignment = frappe.db.sql(
			"""
			SELECT shift_type
			FROM `tabShift Assignment`
			WHERE employee = %(employee)s
			  AND docstatus = 1
			  AND status = 'Active'
			  AND start_date <= %(date)s
			  AND (end_date IS NULL OR end_date >= %(date)s)
			ORDER BY start_date DESC
			LIMIT 1
			""",
			{"employee": self.employee, "date": punch_date},
			as_dict=True,
		)
		if assignment:
			self.shift = assignment[0].shift_type

	def _create_checkin(self) -> str:
		checkin = frappe.new_doc("Employee Checkin")
		checkin.employee = self.employee
		checkin.log_type = self.log_type
		checkin.time = self.request_time
		if self.shift:
			checkin.shift = self.shift
		if checkin.meta.has_field(CHECKIN_LINK_FIELD):
			checkin.set(CHECKIN_LINK_FIELD, self.name)
		checkin.flags.ignore_permissions = True
		checkin.insert(ignore_permissions=True)

		frappe.msgprint(
			_("Employee Checkin {0} created.").format(
				frappe.get_desk_link("Employee Checkin", checkin.name)
			),
			alert=True,
		)
		return checkin.name
