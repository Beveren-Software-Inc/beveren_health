"""Move the Close Observation food flag from Employee to the Timesheet.

The flag lives on each Timesheet now
(``Timesheet.custom_allow_food_allowance_on_close_observation``), so the two
Employee fields that used to drive it are removed:

* ``Employee.custom_food_allowance_applicable`` - the first, unused duplicate.
* ``Employee.custom_allow_food_allowance_on_close_observation`` - the field the
  costing used to read.

An employee that had either box ticked keeps the food portion: the flag is
carried onto their existing timesheets before the Employee fields are dropped.
Stored Total Days are refreshed too, so a timesheet whose hours / 24 worked out
to 29 for 21 Sep -> 20 Oct now says 30.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import delete_custom_fields
from frappe.utils import cint, flt

from beveren_health.beveren_health.customize.timesheet import total_days_from_time_logs

EMPLOYEE_FIELDS = (
	"custom_food_allowance_applicable",
	"custom_allow_food_allowance_on_close_observation",
)
TIMESHEET_FIELD = "custom_allow_food_allowance_on_close_observation"


def execute() -> None:
	carry_flag_to_timesheets()
	delete_custom_fields({"Employee": list(EMPLOYEE_FIELDS)})
	refresh_total_days()


def carry_flag_to_timesheets() -> None:
	if not frappe.db.has_column("Timesheet", TIMESHEET_FIELD):
		return
	employee_fields = [field for field in EMPLOYEE_FIELDS if frappe.db.has_column("Employee", field)]
	if not employee_fields:
		return
	for sheet in frappe.get_all(
		"Timesheet", fields=["name", "employee"], filters={"employee": ["is", "set"]}
	):
		employee = frappe.db.get_value("Employee", sheet.employee, employee_fields, as_dict=True) or {}
		if not any(cint(value) for value in employee.values()):
			continue
		if cint(frappe.db.get_value("Timesheet", sheet.name, TIMESHEET_FIELD)):
			continue
		frappe.db.set_value("Timesheet", sheet.name, TIMESHEET_FIELD, 1, update_modified=False)


def refresh_total_days() -> None:
	if not frappe.db.has_column("Timesheet", "custom_total_days"):
		return
	for sheet in frappe.get_all("Timesheet", pluck="name"):
		rows = frappe.get_all(
			"Timesheet Detail",
			filters={"parent": sheet, "parenttype": "Timesheet"},
			fields=["from_time", "to_time"],
		)
		days = total_days_from_time_logs(rows)
		if not days:
			continue
		if flt(frappe.db.get_value("Timesheet", sheet, "custom_total_days")) == days:
			continue
		frappe.db.set_value("Timesheet", sheet, "custom_total_days", days, update_modified=False)
