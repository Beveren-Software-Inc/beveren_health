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

import json
from datetime import timedelta
from inspect import signature

import frappe
from frappe import _
from frappe.utils import add_months, cint, flt, getdate, today

# A close observation is costed as one allowance, not hours times a rate.
# When the employee's total salary (gross from the assigned Salary Structure)
# is below 250, the gap is earned per day of the payroll period and paid for
# the days actually worked as close observation:
#   daily allowance = (250 - total salary) / days in period * close observation days
# so a full payroll period of close observation earns the whole gap.
# Food is included only when the Timesheet box
# custom_allow_food_allowance_on_close_observation is ticked. Then food is:
#   food component amount / days in the period * close observation days
# The food amount is the Amount on the Salary Component ticked Food Allowance.
#
# The days in the period come from the Timesheet payroll period
# (custom_payroll_start_date -> custom_payroll_end_date). Payroll normally runs
# from the 21st of a month to the 20th of the next, so 21 Sep -> 20 Oct is one
# period of 30 days. A period that spans two calendar months is costed as that
# one block - the days are never split into a September and an October sum.
#
# Close observation days are the timesheet Total Days: every calendar day the
# time logs touch, counting both the first and the last day (21 Sep -> 20 Oct
# is 30 days, not 29). Working hours / 24 is only the fallback for a row that
# has no From Time / To Time.
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

# Payroll runs from the 21st of a month to the 20th of the next. Each Timesheet
# stores its own period (custom_payroll_start_date / custom_payroll_end_date),
# so a period that spans two calendar months is costed as the one block it is.
PAYROLL_PERIOD_START_DAY = 21
PAYROLL_PERIOD_END_DAY = 20


def payroll_period_for_date(on_date) -> tuple:
	"""The payroll period that contains ``on_date``: 21st -> 20th next month."""
	on_date = getdate(on_date)
	if on_date.day >= PAYROLL_PERIOD_START_DAY:
		start = on_date.replace(day=PAYROLL_PERIOD_START_DAY)
	else:
		start = add_months(on_date.replace(day=1), -1).replace(day=PAYROLL_PERIOD_START_DAY)
	end = add_months(start, 1).replace(day=PAYROLL_PERIOD_END_DAY)
	return start, end


def payroll_period_days(start_date, end_date, fallback_date=None) -> int:
	"""Calendar days in the payroll period, first and last day included.

	The period stored on the Timesheet wins. Sheets that predate the fields fall
	back to the payroll period that contains ``fallback_date``.
	"""
	if start_date and end_date:
		start, end = getdate(start_date), getdate(end_date)
		if end < start:
			start, end = end, start
		return (end - start).days + 1
	if fallback_date:
		start, end = payroll_period_for_date(fallback_date)
		return (end - start).days + 1
	return 0


def set_payroll_period(doc, method: str | None = None) -> None:
	"""``validate`` hook: default the payroll period to 21st -> 20th next month.

	The period follows the first time log From Time (26 Jul -> 21 Jul -> 20 Aug),
	then the sheet Start Date when there are no time logs yet, then today. It
	only fills an empty field, so a period the user typed on the Timesheet is
	kept.
	"""
	meta = getattr(doc, "meta", None)
	if meta and not meta.has_field("custom_payroll_start_date"):
		return
	start = doc.get("custom_payroll_start_date")
	end = doc.get("custom_payroll_end_date")
	if start and end:
		return
	on_date = _first_time_log_date(doc.get("time_logs")) or doc.get("start_date") or today()
	default_start, default_end = payroll_period_for_date(on_date)
	if not start:
		doc.custom_payroll_start_date = default_start
	if not end:
		doc.custom_payroll_end_date = default_end


def _first_time_log_date(rows):
	dates = [getdate(row.get("from_time")) for row in rows or [] if row.get("from_time")]
	return min(dates) if dates else None


def set_total_days(doc, method: str | None = None) -> None:
	"""``validate`` hook: Total Days counts every calendar day the time logs touch."""
	meta = getattr(doc, "meta", None)
	if meta and not meta.has_field("custom_total_days"):
		return
	rows = doc.get("time_logs") or []
	days = total_days_from_time_logs(rows)
	if not days:
		hours = flt(doc.get("total_hours")) or sum(flt(row.get("hours")) for row in rows)
		days = total_days_from_hours(hours)
	doc.custom_total_days = flt(days, 2)


def total_days_from_hours(hours: float) -> float:
	"""30 working hours is 1.25 days."""
	return flt(flt(hours) / HOURS_PER_DAY, 2)


def total_days_from_time_logs(rows) -> float:
	"""Calendar days covered by the time logs, both the first and last day included.

	A log running from 21 Sep 00:00 to 20 Oct 00:00 touches 30 dates, so it is
	30 close observation days: the last day counts as well. Returns 0 when the
	rows carry no From Time / To Time, so the caller can fall back to hours.
	"""
	days = set()
	for row in rows or []:
		start = row.get("from_time")
		end = row.get("to_time") or start
		if not start:
			continue
		start_date = getdate(start)
		end_date = getdate(end)
		if end_date < start_date:
			start_date, end_date = end_date, start_date
		days.update(start_date + timedelta(days=offset) for offset in range((end_date - start_date).days + 1))
	return float(len(days))


def close_observation_amounts(
	total_salary: float,
	observation_days: float,
	period_days: int,
	food_applicable: bool,
	monthly_food: float = 0,
	food_days: float | None = None,
) -> dict:
	"""Daily total and the food total for a block of close observation days.

	Applies only when total salary is below 250 and there is at least a fraction
	of a close observation day. Daily Allowance is the salary gap earned per day
	of the payroll period, paid for the close observation days:

	    (250 - total salary) / days in period * close observation days

	Food is the Food Allowance component amount divided by the days in the
	period, times the close observation days that allow food (``food_days``;
	all observation days when it is not given).
	"""
	days = flt(observation_days)
	empty = {
		"applies": False,
		"daily_allowance": 0.0,
		"food_allowance": 0.0,
		"allowance": 0.0,
	}
	days_in_period = cint(period_days)
	if days <= 0 or days_in_period <= 0:
		return empty
	if flt(total_salary) >= CLOSE_OBSERVATION_SALARY_THRESHOLD:
		return empty

	daily = ((CLOSE_OBSERVATION_SALARY_THRESHOLD - flt(total_salary)) / days_in_period) * days
	food = food_allowance_for_days(
		days_in_period,
		days if food_days is None else flt(food_days),
		food_applicable,
		monthly_food,
	)
	return {
		"applies": True,
		"daily_allowance": flt(daily),
		"food_allowance": food,
		"allowance": flt(daily + food),
	}


def food_allowance_for_days(
	period_days: int,
	observation_days: float,
	food_applicable: bool,
	monthly_food: float = 0,
) -> float:
	"""Food component amount / days in the payroll period, times the days."""
	if not food_applicable or cint(period_days) <= 0 or flt(observation_days) <= 0 or flt(monthly_food) <= 0:
		return 0.0
	return flt((flt(monthly_food) / cint(period_days)) * flt(observation_days))


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
	food_applicable: bool | str | None = None,
	payroll_start_date: str | None = None,
	payroll_end_date: str | None = None,
) -> dict:
	"""Costing preview for the desk form, using the same rules as validate."""
	if isinstance(time_logs, str):
		time_logs = json.loads(time_logs or "[]")

	doc = frappe._dict(
		employee=employee,
		exchange_rate=flt(exchange_rate) or 1,
		currency=currency,
		time_logs=[frappe._dict(row) for row in (time_logs or [])],
		custom_allow_food_allowance_on_close_observation=cint(food_applicable),
		custom_payroll_start_date=payroll_start_date,
		custom_payroll_end_date=payroll_end_date,
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
	food_applicable = _food_allowance_applicable(doc)
	for row in observation_rows:
		if not _observation_date(row):
			frappe.throw(
				_("Row {0}: From Time is required to cost Close Observation.").format(row.get("idx") or "")
			)
	observed_on = _first_observation_date(observation_rows)

	period_start = doc.get("custom_payroll_start_date")
	period_end = doc.get("custom_payroll_end_date")
	period_days = payroll_period_days(period_start, period_end, observed_on)
	if not period_days:
		frappe.throw(_("Set the Payroll Start Date and Payroll End Date to cost Close Observation."))

	# The payroll period is one block. A period running 21 Sep -> 20 Oct is 30
	# days of payroll, not a September sum plus an October sum. The salary is
	# the one assigned on the day the observation is worked, so a Salary
	# Structure Assignment that starts inside the period (1 Oct) still applies.
	total_salary = _total_salary_from_structure(doc.employee, observed_on)
	exchange_rate = flt(doc.get("exchange_rate")) or 1
	allowance_total = 0.0

	sheet_days = total_days_from_time_logs(observation_rows)
	if not sheet_days:
		sheet_days = flt(doc.get("custom_total_days")) or total_days_from_hours(
			sum(flt(row.get("hours")) for row in observation_rows)
		)
	all_hours = sum(flt(row.get("hours")) for row in observation_rows) or 1

	amounts = close_observation_amounts(
		total_salary,
		sheet_days,
		period_days,
		food_applicable,
		monthly_food,
	)
	# Daily is already (250 - salary) / days in period * days; do not multiply by days again.
	daily_total = flt(amounts["daily_allowance"])
	food_total = flt(amounts["food_allowance"])
	for row in observation_rows:
		if preview:
			row._close_observation_applies = amounts["applies"]
		if not amounts["applies"]:
			_set_row_value(row, "custom_daily_allowance", 0, has_daily)
			_set_row_value(row, "custom_food_allowance", 0, has_food)
			continue

		hours = flt(row.get("hours")) or 1
		share = hours / all_hours
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


def _first_observation_date(rows):
	dates = [value for value in (_observation_date(row) for row in rows) if value]
	return min(dates) if dates else None


def _is_close_observation(activity_type: str | None) -> bool:
	if not activity_type:
		return False
	if str(activity_type).strip().lower() == CLOSE_OBSERVATION_ACTIVITY:
		return True
	if not frappe.db.has_column("Activity Type", "custom_is_close_observation"):
		return False
	return bool(cint(frappe.db.get_value("Activity Type", activity_type, "custom_is_close_observation")))


def _food_allowance_applicable(doc) -> bool:
	"""Food is part of Close Observation only when the Timesheet box is ticked."""
	meta = getattr(doc, "meta", None)
	if meta and not meta.has_field("custom_allow_food_allowance_on_close_observation"):
		return False
	return bool(cint(doc.get("custom_allow_food_allowance_on_close_observation")))


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
	# Live HRMS does not accept ignore_permissions on make_salary_slip; local does.
	logged = list(frappe.local.message_log or [])
	previous_mute = frappe.flags.mute_messages
	previous_ignore = frappe.flags.ignore_permissions
	frappe.flags.mute_messages = True
	kwargs = {"employee": employee, "posting_date": on_date}
	if "ignore_permissions" in signature(make_salary_slip).parameters:
		kwargs["ignore_permissions"] = True
	else:
		frappe.flags.ignore_permissions = True
	try:
		slip = make_salary_slip(structure, **kwargs)
	finally:
		frappe.flags.mute_messages = previous_mute
		frappe.flags.ignore_permissions = previous_ignore
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
