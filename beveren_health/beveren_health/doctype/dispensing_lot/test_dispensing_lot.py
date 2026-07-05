# Copyright (c) 2026, Beveren Software and Contributors
# See license.txt

# import frappe
from frappe.tests import IntegrationTestCase

from beveren_health.beveren_health.customize.dispensing_lot import (
	compute_dispensing_qty_per_serial,
	round_dispensing_qty,
)


# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]



class IntegrationTestDispensingLot(IntegrationTestCase):
	"""
	Integration tests for DispensingLot.
	Use this class for testing interactions between multiple components.
	"""

	def test_compute_dispensing_qty_per_serial_single_partial(self):
		self.assertEqual(compute_dispensing_qty_per_serial(0.4, ["SN1"], 50), [20.0])

	def test_compute_dispensing_qty_per_serial_two_lots_with_remainder(self):
		self.assertEqual(
			compute_dispensing_qty_per_serial(1.86, ["SN1", "SN2"], 50),
			[50.0, 43.0],
		)

	def test_compute_dispensing_qty_per_serial_many_full_plus_partial(self):
		serials = [f"SN{i}" for i in range(11)]
		result = compute_dispensing_qty_per_serial(10.39, serials, 50)
		self.assertEqual(result[:10], [50.0] * 10)
		self.assertEqual(result[10], 19)

	def test_round_dispensing_qty(self):
		self.assertEqual(round_dispensing_qty(9.99), 10)
		self.assertEqual(round_dispensing_qty(9.80), 10)
		self.assertEqual(round_dispensing_qty(9.79), 9)
		self.assertEqual(round_dispensing_qty(0.79), 0)
		self.assertEqual(round_dispensing_qty(0.80), 1)
		self.assertEqual(round_dispensing_qty(50), 50)
