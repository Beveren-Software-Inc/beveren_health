# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

"""Timesheet: keep the row level Patient in sync with the header Patient.

``Timesheet.custom_patient`` is the patient the whole sheet is logged against;
``Timesheet Detail.custom_patient`` (time_logs) repeats it so that reports and
the portal can read the patient straight off the row. The desk form fills the
rows on the client (public/js/timesheet.js) - this hook covers documents created
through the API, data import or any other server side script.
"""

from __future__ import annotations

import calendar
import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

# A close observation is costed as one allowance, not hours times a rate.
# When the employee's total salary (gross from the assigned Salary Structure)
# is below 250, the gap is spread across the close observation rows:
#   daily allowance = (250 - total salary) / close observation days
# Food, when the employee is marked applicable, is
#   food component amount / days in the month * close observation days
# The food amount is the Amount on the Salary Component ticked Food Allowance.
# Close observation days are the timesheet Total Days (working hours / 24).
# Costing amount on the row = daily allowance + that row's share of the food.
CLOSE_OBSERVATION_SALARY_THRESHOLD = 250
CLOSE_OBSERVATION_ACTIVITY = "close observation"
SALARY_COMPONENT_FLAGS = {
	"food": "custom_food_allowance",
	"daily": "custom_daily_allowance",
	"close_observation": "custom_close_observation",
}


def set_patient_on_time_logs(doc, method: str | None = None) -> None:
	"""``validate`` hook for Timesheet (see hooks.py)."""
	patient = doc.get("custom_patient")
	if not patient:
		return

	if not frappe.get_meta("Timesheet Detail").has_field("custom_patient"):
		return

	for row in doc.get("time_logs") or []:
		# Never overwrite a patient deliberately picked on a single row.
		if not row.get("custom_patient"):
			row.custom_patient = patient


HOURS_PER_DAY = 24


def set_total_days(doc, method: str | None = None) -> None:
	"""``validate`` hook: total days are working hours divided by 24."""
	meta = getattr(doc, "meta", None)
	if meta and not meta.has_field("custom_total_days"):
		return
	hours = flt(doc.get("total_hours"))
	if not hours:
		hours = sum(flt(row.get("hours")) for row in doc.get("time_logs") or [])
	doc.custom_total_days = total_days_from_hours(hours)


def total_days_from_hours(hours: float) -> float:
	"""30 working hours is 1.25 days."""
	return flt(flt(hours) / HOURS_PER_DAY, 2)


def close_observation_amounts(
	total_salary: float,
	observation_days: float,
	days_in_month: int,
	food_applicable: bool,
	monthly_food: float = 0,
) -> dict:
	"""Daily rate and the food total for a block of close observation days.

	Applies only when total salary is below 250 and there is at least a fraction
	of a close observation day. Food is the Food Allowance component amount
	divided by the days in the month, times those days, and only when the
	employee is marked for it.
	"""
	days = flt(observation_days)
	empty = {
		"applies": False,
		"daily_allowance": 0.0,
		"food_allowance": 0.0,
		"allowance": 0.0,
	}
	if days <= 0 or flt(total_salary) >= CLOSE_OBSERVATION_SALARY_THRESHOLD:
		return empty

	daily = (CLOSE_OBSERVATION_SALARY_THRESHOLD - flt(total_salary)) / days
	food = food_allowance_for_days(days_in_month, days, food_applicable, monthly_food)
	return {
		"applies": True,
		"daily_allowance": flt(daily),
		"food_allowance": food,
		"allowance": flt(daily + food),
	}


def food_allowance_for_days(
	days_in_month: int,
	observation_days: float,
	food_applicable: bool,
	monthly_food: float = 0,
) -> float:
	"""Food component amount / days in the month, times the timesheet's days."""
	if (
		not food_applicable
		or cint(days_in_month) <= 0
		or flt(observation_days) <= 0
		or flt(monthly_food) <= 0
	):
		return 0.0
	return flt((flt(monthly_food) / cint(days_in_month)) * flt(observation_days))


def marked_salary_component(kind: str):
	"""The Salary Component ticked for food, daily, or close observation.

	``kind`` is ``food``, ``daily``, or ``close_observation``.
	"""
	flag = SALARY_COMPONENT_FLAGS[kind]
	if not frappe.db.has_column("Salary Component", flag):
		return None
	rows = frappe.get_all(
		"Salary Component",
		filters={flag: 1, "disabled": 0},
		fields=["name", "amount"],
		order_by="modified desc",
	)
	if len(rows) > 1:
		frappe.throw(
			_("Tick {0} on only one Salary Component. It is ticked on {1}.").format(
				flag, ", ".join(row.name for row in rows)
			)
		)
	return rows[0] if rows else None


def set_close_observation_costing(doc, method: str | None = None) -> None:
	"""``validate`` hook: replace hourly costing on Close Observation rows."""
	_apply_close_observation_costing(doc)


@frappe.whitelist()
def preview_close_observation_costing(
	employee: str,
	time_logs: str | list | None = None,
	exchange_rate: float | str | None = None,
	currency: str | None = None,
) -> dict:
	"""Costing preview for the desk form, using the same rules as validate."""
	if isinstance(time_logs, str):
		time_logs = json.loads(time_logs or "[]")

	doc = frappe._dict(
		employee=employee,
		exchange_rate=flt(exchange_rate) or 1,
		currency=currency,
		time_logs=[frappe._dict(row) for row in (time_logs or [])],
		doctype="Timesheet",
	)
	_apply_close_observation_costing(doc, preview=True)

	rows = []
	for row in doc.time_logs:
		if not _is_close_observation(row.get("activity_type")):
			continue
		rows.append(
			{
				"name": row.get("name"),
				"idx": row.get("idx"),
				"applies": bool(row.get("_close_observation_applies")),
				"costing_rate": flt(row.get("costing_rate")),
				"costing_amount": flt(row.get("costing_amount")),
				"base_costing_rate": flt(row.get("base_costing_rate")),
				"base_costing_amount": flt(row.get("base_costing_amount")),
				"daily_allowance": flt(row.get("custom_daily_allowance")),
				"food_allowance": flt(row.get("custom_food_allowance")),
			}
		)
	return {
		"rows": rows,
		"close_observation_allowance": flt(doc.get("custom_close_observation_allowance")),
	}


def _apply_close_observation_costing(doc, preview: bool = False) -> None:
	rows = list(doc.get("time_logs") or [])
	observation_rows = [row for row in rows if _is_close_observation(row.get("activity_type"))]
	detail_meta = frappe.get_meta("Timesheet Detail")
	has_daily = detail_meta.has_field("custom_daily_allowance")
	has_food = detail_meta.has_field("custom_food_allowance")

	if not observation_rows:
		_set_parent_allowance(doc, 0)
		_set_parent_calculation(doc, "")
		return

	if not doc.get("employee"):
		frappe.throw(_("Set the Employee before costing Close Observation."))

	food_component = marked_salary_component("food")
	monthly_food = flt(food_component.amount) if food_component else 0
	food_applicable = bool(monthly_food)
	grouped: dict[tuple[int, int], list] = defaultdict(list)
	for row in observation_rows:
		observed_on = _observation_date(row)
		if not observed_on:
			frappe.throw(
				_("Row {0}: From Time is required to cost Close Observation.").format(row.get("idx") or "")
			)
		grouped[(observed_on.year, observed_on.month)].append(row)

	exchange_rate = flt(doc.get("exchange_rate")) or 1
	allowance_total = 0.0

	sheet_days = flt(doc.get("custom_total_days"))
	if not sheet_days:
		sheet_days = total_days_from_hours(sum(flt(row.get("hours")) for row in observation_rows))
	all_hours = sum(flt(row.get("hours")) for row in observation_rows) or 1

	for (year, month), month_rows in grouped.items():
		on_date = getdate(f"{year}-{month:02d}-01")
		total_salary = _total_salary_from_structure(doc.employee, on_date)
		days_in_month = calendar.monthrange(year, month)[1]
		month_hours = sum(flt(row.get("hours")) for row in month_rows) or 1
		month_days = sheet_days * (month_hours / all_hours) if len(grouped) > 1 else sheet_days
		amounts = close_observation_amounts(
			total_salary,
			month_days,
			days_in_month,
			food_applicable,
			monthly_food,
		)
		daily_total = flt(amounts["daily_allowance"]) * month_days
		food_total = flt(amounts["food_allowance"])
		for row in month_rows:
			if preview:
				row._close_observation_applies = amounts["applies"]
			if not amounts["applies"]:
				_set_row_value(row, "custom_daily_allowance", 0, has_daily)
				_set_row_value(row, "custom_food_allowance", 0, has_food)
				continue

			hours = flt(row.get("hours")) or 1
			share = hours / month_hours
			amount = (daily_total * share) + (food_total * share)
			rate = amount / hours
			_set_money(row, "costing_amount", amount)
			_set_money(row, "costing_rate", rate)
			_set_money(row, "base_costing_amount", amount * exchange_rate)
			_set_money(row, "base_costing_rate", rate * exchange_rate)
			_set_row_value(row, "custom_daily_allowance", daily_total * share, has_daily)
			_set_row_value(row, "custom_food_allowance", food_total * share, has_food)
			allowance_total += flt(row.get("costing_amount"))

	if not preview:
		doc.total_costing_amount = sum(flt(row.get("costing_amount")) for row in rows)
		doc.base_total_costing_amount = sum(flt(row.get("base_costing_amount")) for row in rows)
	_set_parent_allowance(doc, allowance_total)
	_set_parent_calculation(doc, "")


def _observation_date(row):
	value = row.get("from_time") or row.get("to_time")
	return getdate(value) if value else None


def _is_close_observation(activity_type: str | None) -> bool:
	if not activity_type:
		return False
	if str(activity_type).strip().lower() == CLOSE_OBSERVATION_ACTIVITY:
		return True
	if not frappe.db.has_column("Activity Type", "custom_is_close_observation"):
		return False
	return bool(cint(frappe.db.get_value("Activity Type", activity_type, "custom_is_close_observation")))


def _total_salary_from_structure(employee: str, on_date) -> float:
	"""Gross pay from the Salary Structure assigned to the employee on this date."""
	from hrms.payroll.doctype.salary_structure.salary_structure import make_salary_slip
	from hrms.payroll.doctype.salary_structure_assignment.salary_structure_assignment import (
		get_assigned_salary_structure,
	)

	structure = get_assigned_salary_structure(employee, on_date)
	if not structure:
		frappe.throw(
			_("No Salary Structure is assigned to {0} on {1}.").format(
				employee, frappe.format(on_date, {"fieldtype": "Date"})
			)
		)

	# Building the slip can msgprint about tax components. This is only a
	# salary lookup, so those notices must not surface on the Timesheet.
	logged = list(frappe.local.message_log or [])
	previous_mute = frappe.flags.mute_messages
	frappe.flags.mute_messages = True
	try:
		slip = make_salary_slip(
			structure,
			employee=employee,
			posting_date=on_date,
			ignore_permissions=True,
		)
	finally:
		frappe.flags.mute_messages = previous_mute
		frappe.local.message_log = logged
	return flt(slip.gross_pay)


def _set_parent_allowance(doc, amount: float) -> None:
	meta = getattr(doc, "meta", None)
	if meta and not meta.has_field("custom_close_observation_allowance"):
		return
	doc.custom_close_observation_allowance = flt(amount)


def _set_parent_calculation(doc, note: str) -> None:
	meta = getattr(doc, "meta", None)
	if meta and not meta.has_field("custom_close_observation_calculation"):
		return
	doc.custom_close_observation_calculation = note or ""


def _set_row_value(row, field: str, value, enabled: bool) -> None:
	if not enabled:
		return
	_assign(row, field, flt(value))


def _set_money(row, field: str, amount: float) -> None:
	precision = None
	precision_fn = getattr(type(row), "precision", None)
	if callable(precision_fn):
		precision = row.precision(field)
	value = flt(amount, precision) if precision else flt(amount)
	_assign(row, field, value)


def _assign(row, field: str, value) -> None:
	"""Set a field on a Document, or a key on the preview dict.

	``frappe._dict`` answers ``hasattr(row, "set")`` with None, because a
	missing key is returned instead of raising. Only a real method may be called.
	"""
	setter = getattr(type(row), "set", None)
	if callable(setter):
		row.set(field, value)
	else:
		row[field] = value
