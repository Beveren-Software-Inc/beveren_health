# Copyright (c) 2026, Beveren Software and Contributors
# See license.txt

from datetime import date

import frappe
from frappe.tests import UnitTestCase

from beveren_health.beveren_health.customize.timesheet import (
	close_observation_amounts,
	payroll_period_days,
	payroll_period_for_date,
	set_payroll_period,
	set_total_days,
	total_days_from_hours,
	total_days_from_time_logs,
)


class TestCloseObservationAmounts(UnitTestCase):
	def test_shortfall_is_earned_per_day_of_the_period(self):
		# Salary 200, four close observation days in a 30-day payroll period, food applicable.
		# Daily = (250 - 200) / 30 * 4 = 6.666...
		# Food = (50 / 30) * 4
		result = close_observation_amounts(200, 4, 30, True, 50)

		self.assertTrue(result["applies"])
		self.assertAlmostEqual(result["daily_allowance"], (50 / 30) * 4)
		self.assertAlmostEqual(result["food_allowance"], (50 / 30) * 4)
		self.assertAlmostEqual(result["allowance"], ((50 / 30) * 4) + ((50 / 30) * 4))

	def test_full_period_of_close_observation_earns_the_whole_gap(self):
		result = close_observation_amounts(200, 30, 30, False)

		self.assertAlmostEqual(result["daily_allowance"], 50)

	def test_food_is_left_out_when_the_employee_is_not_applicable(self):
		result = close_observation_amounts(200, 4, 30, False)

		self.assertEqual(result["food_allowance"], 0.0)
		self.assertAlmostEqual(result["allowance"], (50 / 30) * 4)

	def test_salary_at_the_threshold_keeps_hourly_costing(self):
		result = close_observation_amounts(250, 4, 30, True)

		self.assertFalse(result["applies"])
		self.assertEqual(result["allowance"], 0.0)

	def test_no_observations_does_not_apply(self):
		result = close_observation_amounts(100, 0, 31, True)

		self.assertFalse(result["applies"])

	def test_zero_days_in_period_does_not_divide_by_zero(self):
		result = close_observation_amounts(100, 4, 0, False)

		self.assertFalse(result["applies"])
		self.assertEqual(result["allowance"], 0.0)

	def test_payroll_period_runs_from_the_21st_to_the_20th(self):
		self.assertEqual(payroll_period_for_date("2026-10-05"), (date(2026, 9, 21), date(2026, 10, 20)))
		self.assertEqual(payroll_period_for_date("2026-10-21"), (date(2026, 10, 21), date(2026, 11, 20)))
		self.assertEqual(payroll_period_for_date("2026-12-27"), (date(2026, 12, 21), date(2027, 1, 20)))

	def test_payroll_period_days_count_both_ends(self):
		# 21 Sep -> 20 Oct is one payroll period of 30 days, not two months.
		self.assertEqual(payroll_period_days("2026-09-21", "2026-10-20"), 30)
		self.assertEqual(payroll_period_days("2026-10-21", "2026-11-20"), 31)
		# Sheets that predate the fields fall back to the period around the date.
		self.assertEqual(payroll_period_days(None, None, "2026-10-05"), 30)

	def test_new_timesheet_defaults_its_payroll_period(self):
		doc = frappe._dict(start_date="2026-10-05", time_logs=[])

		set_payroll_period(doc)

		self.assertEqual(doc.custom_payroll_start_date, date(2026, 9, 21))
		self.assertEqual(doc.custom_payroll_end_date, date(2026, 10, 20))

	def test_timesheet_keeps_the_payroll_period_the_user_set(self):
		doc = frappe._dict(
			start_date="2026-10-05",
			custom_payroll_start_date="2026-10-01",
			custom_payroll_end_date="2026-10-31",
		)

		set_payroll_period(doc)

		self.assertEqual(doc.custom_payroll_start_date, "2026-10-01")
		self.assertEqual(doc.custom_payroll_end_date, "2026-10-31")

	def test_total_days_follows_working_hours(self):
		self.assertEqual(total_days_from_hours(30), 1.25)
		self.assertEqual(total_days_from_hours(24), 1.0)
		self.assertEqual(total_days_from_hours(274), 11.42)

	def test_total_days_count_the_last_day(self):
		# 21 Sep 00:00 -> 20 Oct 00:00 is 696 hours (29 x 24), but the period
		# covers 30 calendar days: the last day counts.
		rows = [{"from_time": "2026-09-21 00:00:00", "to_time": "2026-10-20 00:00:00"}]
		self.assertEqual(total_days_from_time_logs(rows), 30)

		# 9 Oct 13:59 -> 12 Oct 13:59 touches four dates.
		rows = [{"from_time": "2026-10-09 13:59:06", "to_time": "2026-10-12 13:59:06"}]
		self.assertEqual(total_days_from_time_logs(rows), 4)

	def test_total_days_are_distinct_calendar_days(self):
		rows = [
			{"from_time": "2026-10-01 08:00:00", "to_time": "2026-10-01 20:00:00"},
			{"from_time": "2026-10-03 08:00:00", "to_time": "2026-10-03 20:00:00"},
		]
		self.assertEqual(total_days_from_time_logs(rows), 2)

	def test_total_days_without_times_fall_back_to_hours(self):
		self.assertEqual(total_days_from_time_logs([{"hours": 24}]), 0)

		doc = frappe._dict(time_logs=[frappe._dict(hours=24)])
		set_total_days(doc)
		self.assertEqual(doc.custom_total_days, 1)

	def test_set_total_days_counts_the_last_day(self):
		doc = frappe._dict(
			time_logs=[
				frappe._dict(
					from_time="2026-09-21 00:00:00",
					to_time="2026-10-20 00:00:00",
					hours=696,
				)
			]
		)

		set_total_days(doc)

		self.assertEqual(doc.custom_total_days, 30)

	def test_slip_totals_one_observation_without_food(self):
		from beveren_health.beveren_health.customize.salary_slip import close_observation_component_totals

		# Salary 180, Total Days 3 in the 21 Sep -> 20 Oct payroll period (30 days).
		# Daily = (250 - 180) / 30 * 3; food off → Close Observation ≈ 7.00.
		sheets = [{"name": "TS-1", "from_time": "2026-10-16 12:00:00", "total_days": 3}]
		totals = close_observation_component_totals(sheets, 180)

		self.assertAlmostEqual(totals["daily_allowance"], (70 / 30) * 3, places=6)
		self.assertEqual(totals["food_allowance"], 0)

	def test_slip_food_uses_timesheet_days(self):
		from beveren_health.beveren_health.customize.salary_slip import close_observation_component_totals

		sheets = [
			{
				"name": "TS-1",
				"from_time": "2026-10-16 12:00:00",
				"total_days": 4.42,
				"food_applicable": True,
			}
		]
		totals = close_observation_component_totals(sheets, 180, 50)

		self.assertAlmostEqual(totals["daily_allowance"], (70 / 30) * 4.42, places=6)
		self.assertAlmostEqual(totals["food_allowance"], (50 / 30) * 4.42, places=6)

	def test_slip_food_only_on_the_timesheets_that_allow_it(self):
		from beveren_health.beveren_health.customize.salary_slip import close_observation_component_totals

		sheets = [
			{"name": "TS-1", "from_time": "2026-10-03 08:00:00", "total_days": 2, "food_applicable": True},
			{"name": "TS-2", "from_time": "2026-10-10 08:00:00", "total_days": 3, "food_applicable": False},
		]
		totals = close_observation_component_totals(sheets, 180, 50)

		# Daily is paid for all five days, food only for the flagged two.
		self.assertAlmostEqual(totals["daily_allowance"], (70 / 30) * 5, places=6)
		self.assertAlmostEqual(totals["food_allowance"], (50 / 30) * 2, places=6)

	def test_slip_costs_a_period_that_spans_two_months_as_one_block(self):
		from beveren_health.beveren_health.customize.salary_slip import close_observation_component_totals

		# 21 Sep -> 20 Oct is one payroll period of 30 days. A full period of
		# close observation earns the whole (250 - 200) gap: it is not 10 days
		# costed as September plus 20 days costed as October.
		sheets = [
			{
				"name": "TS-1",
				"from_time": "2026-09-21 00:00:00",
				"total_days": 30,
				"payroll_start_date": "2026-09-21",
				"payroll_end_date": "2026-10-20",
			}
		]
		totals = close_observation_component_totals(sheets, 200)

		self.assertAlmostEqual(totals["daily_allowance"], 50, places=6)

	def test_slip_adds_the_days_of_both_months_to_the_same_period(self):
		from beveren_health.beveren_health.customize.salary_slip import close_observation_component_totals

		# Two timesheets in the same 21 Sep -> 20 Oct period: 5 days in
		# September and 6 in October are 11 days of one 30-day period.
		sheets = [
			{
				"name": "TS-1",
				"from_time": "2026-09-22 08:00:00",
				"total_days": 5,
				"payroll_start_date": "2026-09-21",
				"payroll_end_date": "2026-10-20",
			},
			{
				"name": "TS-2",
				"from_time": "2026-10-15 08:00:00",
				"total_days": 6,
				"payroll_start_date": "2026-09-21",
				"payroll_end_date": "2026-10-20",
			},
		]
		totals = close_observation_component_totals(sheets, 180)

		self.assertAlmostEqual(totals["daily_allowance"], (70 / 30) * 11, places=6)

	def test_slip_divides_by_the_payroll_period_not_the_calendar_month(self):
		from beveren_health.beveren_health.customize.salary_slip import close_observation_component_totals

		# The log starts in October (31 calendar days) but belongs to the
		# 21 Sep -> 20 Oct payroll period, which has 30 days.
		sheets = [
			{
				"name": "TS-1",
				"from_time": "2026-10-01 08:00:00",
				"total_days": 20,
				"payroll_start_date": "2026-09-21",
				"payroll_end_date": "2026-10-20",
			}
		]
		totals = close_observation_component_totals(sheets, 180)

		self.assertAlmostEqual(totals["daily_allowance"], (70 / 30) * 20, places=6)

	def test_slip_food_divides_by_the_payroll_period_too(self):
		from beveren_health.beveren_health.customize.salary_slip import close_observation_component_totals

		sheets = [
			{
				"name": "TS-1",
				"from_time": "2026-09-21 00:00:00",
				"total_days": 30,
				"food_applicable": True,
				"payroll_start_date": "2026-09-21",
				"payroll_end_date": "2026-10-20",
			}
		]
		totals = close_observation_component_totals(sheets, 200, 60)

		self.assertAlmostEqual(totals["food_allowance"], 60, places=6)
