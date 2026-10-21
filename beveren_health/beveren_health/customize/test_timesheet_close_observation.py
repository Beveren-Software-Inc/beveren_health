# Copyright (c) 2026, Beveren Software and Contributors
# See license.txt

from frappe.tests import UnitTestCase

from beveren_health.beveren_health.customize.timesheet import (
	close_observation_amounts,
	total_days_from_hours,
)


class TestCloseObservationAmounts(UnitTestCase):
	def test_shortfall_is_spread_across_observation_days(self):
		# Salary 200, four close observation days in a 30-day month, food applicable.
		# Daily rate = (250 - 200) / 4 = 12.5
		# Food = (50 / 30) * 4
		result = close_observation_amounts(200, 4, 30, True, 50)

		self.assertTrue(result["applies"])
		self.assertEqual(result["daily_allowance"], 12.5)
		self.assertAlmostEqual(result["food_allowance"], (50 / 30) * 4)
		self.assertAlmostEqual(result["allowance"], 12.5 + (50 / 30) * 4)

	def test_food_is_left_out_when_the_employee_is_not_applicable(self):
		result = close_observation_amounts(200, 4, 30, False)

		self.assertEqual(result["food_allowance"], 0.0)
		self.assertEqual(result["allowance"], 12.5)

	def test_salary_at_the_threshold_keeps_hourly_costing(self):
		result = close_observation_amounts(250, 4, 30, True)

		self.assertFalse(result["applies"])
		self.assertEqual(result["allowance"], 0.0)

	def test_no_observations_does_not_apply(self):
		result = close_observation_amounts(100, 0, 31, True)

		self.assertFalse(result["applies"])

	def test_total_days_follows_working_hours(self):
		self.assertEqual(total_days_from_hours(30), 1.25)
		self.assertEqual(total_days_from_hours(24), 1.0)
		self.assertEqual(total_days_from_hours(274), 11.42)

	def test_slip_totals_one_observation_without_food(self):
		from beveren_health.beveren_health.customize.salary_slip import close_observation_component_totals

		# Salary 180, Total Days 3. Daily = (250 - 180) / 3; food off → Close Observation ≈ 23.33.
		sheets = [{"name": "TS-1", "from_time": "2026-10-16 12:00:00", "total_days": 3}]
		totals = close_observation_component_totals(sheets, 180, False)

		self.assertAlmostEqual(totals["daily_allowance"], 70 / 3, places=6)
		self.assertEqual(totals["food_allowance"], 0)

	def test_slip_food_uses_timesheet_days(self):
		from beveren_health.beveren_health.customize.salary_slip import close_observation_component_totals

		sheets = [{"name": "TS-1", "from_time": "2026-10-16 12:00:00", "total_days": 4.42}]
		totals = close_observation_component_totals(sheets, 180, True, 50)

		self.assertAlmostEqual(totals["daily_allowance"], 70 / 4.42, places=6)
		self.assertAlmostEqual(totals["food_allowance"], (50 / 31) * 4.42, places=6)
