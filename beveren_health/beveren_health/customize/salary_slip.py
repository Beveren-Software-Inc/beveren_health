import calendar

import frappe
from frappe import _
from frappe.utils import add_months, cint, flt, getdate
from hrms.payroll.doctype.salary_slip.salary_slip import get_salary_component_data

from beveren_health.beveren_health.customize.timesheet import (
	_food_allowance_applicable,
	_is_close_observation,
	close_observation_amounts,
	marked_salary_component,
	total_days_from_hours,
)


@frappe.whitelist()
def get_lwp_absents(employee, start_date, end_date):
	start_date = getdate(start_date)
	end_date = getdate(end_date)
	prev_month_date = add_months(getdate(start_date), -1)
	start_date = prev_month_date.replace(day=21)
	end_date = getdate(end_date).replace(day=20)
	lwp_entries = frappe.get_all(
		"Leave Application",
		filters={
			"employee": employee,
			"leave_type": "Leave Without Pay",
			"from_date": ["<=", end_date],
			"to_date": [">=", start_date],
			"docstatus": 1,
		},
		fields=["from_date", "to_date"],
	)
	total_lwp = 0
	for leave in lwp_entries:
		leave_start = max(getdate(leave.from_date), start_date)
		leave_end = min(getdate(leave.to_date), end_date)
		total_lwp += (leave_end - leave_start).days + 1

	absent_entries = frappe.get_all(
		"Attendance",
		filters={
			"employee": employee,
			"attendance_date": ["between", [start_date, end_date]],
			"status": "Absent",
			"docstatus": 1,
		},
		fields=["attendance_date"],
	)

	total_absent = len(absent_entries)

	return {"total_lwp": total_lwp, "total_absent": total_absent}


def set_close_observation_allowances(doc, method: str | None = None) -> None:
	"""On save, recalculate Close Observation when the timesheet table has changed."""
	if cint(doc.docstatus) != 0:
		return
	components = _allowance_components()
	removed_calculation_rows = _remove_calculation_rows(doc, components)
	timesheets = _close_observation_timesheets(doc)
	changed = bool(doc.flags.get("force_close_observation")) or _timesheet_table_changed(doc)
	close_name = components["close_observation"].name if components["close_observation"] else None

	if not timesheets:
		removed_close = _remove_component_rows(doc, {close_name}) if close_name and changed else False
		if removed_calculation_rows or removed_close:
			_retotal_slip(doc)
		return
	if not components["close_observation"]:
		frappe.throw(_("Tick Close Observation on the Salary Component that should receive it."))
	if not components["daily"]:
		frappe.throw(_("Tick Daily Allowance on the Salary Component used to calculate it."))

	already_added = any(row.salary_component == close_name for row in (doc.get("earnings") or []))
	if not changed and already_added:
		_drop_structure_timesheet_component(doc, components["close_observation"])
		if removed_calculation_rows:
			_retotal_slip(doc)
		return
	apply_close_observation_allowances(doc, components, timesheets)


@frappe.whitelist()
def calculate_close_observation(salary_slip: str) -> dict:
	"""Button action: recalculate Close Observation on a draft Salary Slip and save it."""
	doc = frappe.get_doc("Salary Slip", salary_slip)
	if cint(doc.docstatus) != 0:
		frappe.throw(_("Close Observation can only be calculated on a draft Salary Slip."))
	doc.flags.force_close_observation = True
	doc.save()
	component = marked_salary_component("close_observation")
	amount = _earning_amount(doc, component.name) if component else 0
	if not doc.flags.get("close_observation_days"):
		frappe.msgprint(
			_("No Close Observation time logs are linked to this Salary Slip."),
			alert=True,
		)
	return {"close_observation": amount}


def apply_close_observation_allowances(doc, components: dict | None = None, timesheets=None) -> None:
	"""Set the ticked Close Observation earning. Daily and Food stay off the slip."""
	components = components or _allowance_components()
	timesheets = _close_observation_timesheets(doc) if timesheets is None else timesheets
	doc.flags.close_observation_days = sum(flt(row.get("total_days")) for row in timesheets)
	_remove_calculation_rows(doc, components)
	if not timesheets:
		_retotal_slip(doc)
		return
	if not components["close_observation"]:
		frappe.throw(_("Tick Close Observation on the Salary Component that should receive it."))
	if not components["daily"]:
		frappe.throw(_("Tick Daily Allowance on the Salary Component used to calculate it."))

	monthly_food = flt(components["food"].amount) if components["food"] else 0
	food_applicable = _food_allowance_applicable(doc.employee) if doc.employee else False
	totals = close_observation_component_totals(
		timesheets,
		_salary_excluding_close_observation(doc, components),
		food_applicable,
		monthly_food,
	)
	close_total = flt(totals["daily_allowance"]) + flt(totals["food_allowance"])
	_drop_structure_timesheet_component(doc, components["close_observation"])
	_upsert_earning(doc, components["close_observation"].name, close_total)
	_retotal_slip(doc)


def _timesheet_table_changed(doc) -> bool:
	"""True when the timesheets on this Salary Slip differ from the last save."""
	if doc.is_new() or not doc.name or not frappe.db.exists("Salary Slip", doc.name):
		return True
	saved = frappe.get_all(
		"Salary Slip Timesheet",
		filters={"parent": doc.name, "parenttype": "Salary Slip"},
		fields=["time_sheet", "working_hours"],
	)
	current = list(doc.get("timesheets") or [])
	if _timesheet_signature(saved) != _timesheet_signature(current):
		return True
	names = [row.time_sheet for row in current if row.get("time_sheet")]
	if not names:
		return False
	sheets = {
		sheet.name: sheet
		for sheet in frappe.get_all(
			"Timesheet",
			filters={"name": ["in", names]},
			fields=["name", "total_hours", "modified"],
		)
	}
	for row in current:
		sheet = sheets.get(row.time_sheet)
		if not sheet:
			return True
		if flt(sheet.total_hours) != flt(row.working_hours):
			return True
		if doc.modified and sheet.modified and str(sheet.modified) > str(doc.modified):
			return True
	return False


def _timesheet_signature(rows) -> tuple:
	return tuple(sorted((row.get("time_sheet") or "", flt(row.get("working_hours"))) for row in rows or []))


def _remove_calculation_rows(doc, components: dict) -> bool:
	"""Daily and Food are only inputs. They are not earnings on the Salary Slip."""
	names = {component.name for component in (components.get("daily"), components.get("food")) if component}
	return _remove_component_rows(doc, names)


def _remove_component_rows(doc, names: set) -> bool:
	if not names:
		return False
	removed = False
	for row in list(doc.get("earnings") or []):
		if row.salary_component in names:
			doc.remove(row)
			removed = True
	return removed


def close_observation_component_totals(
	timesheets,
	total_salary: float,
	food_applicable: bool,
	monthly_food: float = 0,
) -> dict:
	"""Slip totals from the linked timesheets' Total Days.

	Daily Allowance is (250 - total salary) / timesheet Total Days when salary
	is below 250. Food Allowance is the Food Allowance component amount / days
	in the month, times the timesheet Total Days, only when the employee allows
	food on Close Observation. Close Observation = Daily + Food.
	"""
	grouped: dict[tuple[int, int], float] = {}
	seen = set()
	for sheet in timesheets or []:
		key = sheet.get("name") or id(sheet)
		if key in seen:
			continue
		seen.add(key)
		observed_on = sheet.get("from_time") or sheet.get("start_date")
		if not observed_on:
			continue
		observed_on = getdate(observed_on)
		days = flt(sheet.get("total_days"))
		if not days:
			days = total_days_from_hours(sheet.get("total_hours"))
		grouped[(observed_on.year, observed_on.month)] = (
			grouped.get((observed_on.year, observed_on.month), 0) + days
		)

	daily = 0.0
	food = 0.0
	for (year, month), days in grouped.items():
		amounts = close_observation_amounts(
			total_salary,
			days,
			calendar.monthrange(year, month)[1],
			food_applicable,
			monthly_food,
		)
		if not amounts["applies"]:
			continue
		daily += flt(amounts["daily_allowance"])
		food += flt(amounts["food_allowance"])
	return {"daily_allowance": flt(daily), "food_allowance": flt(food)}


def _allowance_components() -> dict:
	return {
		"daily": marked_salary_component("daily"),
		"food": marked_salary_component("food"),
		"close_observation": marked_salary_component("close_observation"),
	}


def _drop_structure_timesheet_component(doc, close_component) -> None:
	"""Remove the structure's hourly timesheet line when it is not the ticked component."""
	if not doc.salary_structure:
		return
	structure_component = frappe.db.get_value("Salary Structure", doc.salary_structure, "salary_component")
	close_name = close_component.name if close_component else None
	if not structure_component or structure_component == close_name:
		return
	for row in list(doc.get("earnings") or []):
		if row.salary_component == structure_component:
			doc.remove(row)


def _retotal_slip(doc) -> None:
	"""Retotal after Close Observation is written onto the slip."""
	doc.set_totals()
	precision = doc.precision("gross_pay")
	doc.gross_pay = flt(
		sum(flt(row.amount) for row in (doc.get("earnings") or []) if not cint(row.do_not_include_in_total)),
		precision,
	)
	doc.total_deduction = flt(
		sum(
			flt(row.amount) for row in (doc.get("deductions") or []) if not cint(row.do_not_include_in_total)
		),
		precision,
	)
	doc.net_pay = flt(doc.gross_pay) - flt(doc.total_deduction) - flt(doc.get("total_loan_repayment"))
	doc.set_base_totals()
	doc.compute_year_to_date()
	doc.compute_month_to_date()
	doc.compute_component_wise_year_to_date()


def _close_observation_timesheets(doc) -> list:
	"""Linked timesheets that have a Close Observation row, with their Total Days."""
	names = [row.time_sheet for row in (doc.get("timesheets") or []) if row.get("time_sheet")]
	if not names:
		return []
	logs = frappe.get_all(
		"Timesheet Detail",
		filters={"parent": ["in", names], "parenttype": "Timesheet"},
		fields=["activity_type", "from_time", "to_time", "parent"],
	)
	observed = {}
	for log in logs:
		if not _is_close_observation(log.activity_type):
			continue
		observed.setdefault(log.parent, log.from_time or log.to_time)
	if not observed:
		return []

	fields = ["name", "total_hours", "start_date"]
	if frappe.db.has_column("Timesheet", "custom_total_days"):
		fields.append("custom_total_days")
	sheets = frappe.get_all("Timesheet", filters={"name": ["in", list(observed)]}, fields=fields)
	result = []
	for sheet in sheets:
		days = flt(sheet.get("custom_total_days")) or total_days_from_hours(sheet.get("total_hours"))
		result.append(
			{
				"name": sheet.name,
				"from_time": observed.get(sheet.name) or sheet.start_date,
				"total_days": days,
				"total_hours": sheet.total_hours,
			}
		)
	return result


def _salary_excluding_close_observation(doc, components: dict | None = None) -> float:
	"""Other earnings on the slip. Close observation lines are not part of this salary."""
	components = components or _allowance_components()
	excluded = {
		component.name
		for component in (components["daily"], components["food"], components["close_observation"])
		if component
	}
	if doc.salary_structure:
		timesheet_component = frappe.db.get_value(
			"Salary Structure", doc.salary_structure, "salary_component"
		)
		if timesheet_component:
			excluded.add(timesheet_component)
	return sum(flt(row.amount) for row in (doc.get("earnings") or []) if row.salary_component not in excluded)


def _upsert_earning(
	doc,
	component: str,
	amount: float,
	keep_zero: bool = False,
	include_in_total: bool = True,
) -> None:
	precision = doc.precision("gross_pay")
	amount = flt(amount, precision)
	rows = [row for row in (doc.get("earnings") or []) if row.salary_component == component]
	if not amount and not keep_zero:
		for row in rows:
			doc.remove(row)
		return

	data = get_salary_component_data(component) or {}
	row = rows[0] if rows else doc.append("earnings", {})
	for extra in rows[1:]:
		doc.remove(extra)
	row.salary_component = component
	row.abbr = data.get("abbr")
	row.amount = amount
	row.default_amount = amount
	row.additional_amount = 0
	row.depends_on_payment_days = 0
	row.is_tax_applicable = cint(data.get("is_tax_applicable"))
	row.do_not_include_in_total = 0 if include_in_total else 1


def _earning_amount(doc, component: str) -> float:
	for row in doc.get("earnings") or []:
		if row.salary_component == component:
			return flt(row.amount)
	return 0.0
