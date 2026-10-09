# Copyright (c) 2026, Beveren Software and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from beveren_health.beveren_health.customize.dispensing_lot import (
	_stock_row_zeroes_batch,
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
		self.assertEqual(round_dispensing_qty(45.117647), 45)

	def test_round_dispensing_qty_small_fraction_rounds_down_for_units(self):
		# UNIT rounding only — values below 1 round down (e.g. 0.126 is not a whole unit count).
		self.assertEqual(round_dispensing_qty(0.126), 0)

	def test_partial_pack_qty_with_small_conversion_factor(self):
		# 0.767 PACK ÷ 0.017 per UNIT ≈ 45.12 → rounds down to 45
		pack_size = 1 / 0.017
		self.assertEqual(compute_dispensing_qty_per_serial(0.767, ["SN1"], pack_size=pack_size), [45])

	# ─── Zeroed batches (Stock Reconciliation turned down to zero) ────────────────

	def _lot_after_transactions(self, transactions, initial_qty=50, stock_uom="Pack", uom="UNIT"):
		"""An in-memory lot with the transactions, remaining and status recalculated."""
		lot = frappe.get_doc(
			{
				"doctype": "Dispensing Lot",
				"serial_no": "SN-TEST-0001",
				"stock_uom": stock_uom,
				"uom": uom,
				"initial_qty": initial_qty,
				"transactions": [dict(row, posting_date="2026-10-08") for row in transactions],
			}
		)
		lot.set_remaining_qty()
		lot.set_status()
		return lot

	def test_stock_row_zeroes_batch(self):
		reconciliation = frappe._dict(doctype="Stock Reconciliation")

		self.assertTrue(_stock_row_zeroes_batch(reconciliation, frappe._dict(qty=0)))
		self.assertTrue(_stock_row_zeroes_batch(reconciliation, frappe._dict(qty=None)))
		self.assertFalse(_stock_row_zeroes_batch(reconciliation, frappe._dict(qty=5)))
		self.assertFalse(
			_stock_row_zeroes_batch(frappe._dict(doctype="Purchase Receipt"), frappe._dict(qty=0))
		)

	def test_zeroed_batch_lot_goes_inactive_and_keeps_serial(self):
		lot = self._lot_after_transactions(
			[
				{
					"transaction_type": "Out",
					"qty": 50,
					"uom": "UNIT",
					"reference_doctype": "Stock Reconciliation",
					"reference_name": "MAT-RECO-2026-00064",
					"remarks": "Zeroed by Stock Reconciliation MAT-RECO-2026-00064",
				}
			]
		)

		self.assertEqual(lot.remaining_qty, 0.0)
		self.assertEqual(lot.status, "Inactive")
		self.assertEqual(lot.serial_no, "SN-TEST-0001")

	def test_zeroed_batch_lot_without_unit_uom_goes_inactive(self):
		# An item without a UNIT UOM moves the whole pack in the stock UOM.
		lot = self._lot_after_transactions(
			[
				{
					"transaction_type": "Out",
					"qty": 1,
					"uom": "Pack",
					"reference_doctype": "Stock Reconciliation",
					"reference_name": "MAT-RECO-2026-00064",
					"remarks": "Zeroed by Stock Reconciliation MAT-RECO-2026-00064",
				}
			],
			initial_qty=1,
			uom="Pack",
		)

		self.assertEqual(lot.remaining_qty, 0.0)
		self.assertEqual(lot.status, "Inactive")
		self.assertEqual(lot.serial_no, "SN-TEST-0001")

	def test_partially_sold_lot_zeroed_by_reconciliation_goes_inactive(self):
		lot = self._lot_after_transactions(
			[
				{
					"transaction_type": "Out",
					"qty": 10,
					"uom": "UNIT",
					"reference_doctype": "Sales Invoice",
					"reference_name": "SINV-2026-00001",
					"remarks": "Sold",
				},
				{
					"transaction_type": "Out",
					"qty": 40,
					"uom": "UNIT",
					"reference_doctype": "Stock Reconciliation",
					"reference_name": "MAT-RECO-2026-00064",
					"remarks": "Zeroed by Stock Reconciliation MAT-RECO-2026-00064",
				},
			]
		)

		self.assertEqual(lot.remaining_qty, 0.0)
		self.assertEqual(lot.status, "Inactive")

	def test_cancelled_receipt_lot_goes_inactive(self):
		lot = self._lot_after_transactions(
			[
				{
					"transaction_type": "Out",
					"qty": 50,
					"uom": "UNIT",
					"reference_doctype": "Purchase Receipt",
					"reference_name": "MAT-PRE-2026-00001",
					"remarks": "Cancelled MAT-PRE-2026-00001",
				}
			]
		)

		self.assertEqual(lot.remaining_qty, 0.0)
		self.assertEqual(lot.status, "Inactive")
		self.assertEqual(lot.serial_no, "SN-TEST-0001")

	def test_full_pack_sale_is_still_delivered(self):
		lot = self._lot_after_transactions(
			[
				{
					"transaction_type": "Out",
					"qty": 1,
					"uom": "Pack",
					"reference_doctype": "Sales Invoice",
					"reference_name": "SINV-2026-00002",
					"remarks": "Sold",
				}
			],
			initial_qty=1,
		)

		self.assertEqual(lot.remaining_qty, 0.0)
		self.assertEqual(lot.status, "Delivered")
		self.assertIsNone(lot.serial_no)

	def test_full_pack_sale_beats_a_later_receipt_cancellation(self):
		# The customer already took the pack: cancelling the receipt afterwards does not
		# make the lot dispensable again.
		lot = self._lot_after_transactions(
			[
				{
					"transaction_type": "Out",
					"qty": 1,
					"uom": "Pack",
					"reference_doctype": "Sales Invoice",
					"reference_name": "SINV-2026-00003",
					"remarks": "Sold",
				},
				{
					"transaction_type": "Out",
					"qty": 1,
					"uom": "Pack",
					"reference_doctype": "Purchase Receipt",
					"reference_name": "MAT-PRE-2026-00001",
					"remarks": "Cancelled MAT-PRE-2026-00001",
				},
			],
			initial_qty=1,
		)

		self.assertEqual(lot.status, "Delivered")
		self.assertIsNone(lot.serial_no)

	def test_cancelled_return_keeps_a_full_pack_sale_delivered(self):
		lot = self._lot_after_transactions(
			[
				{
					"transaction_type": "Out",
					"qty": 1,
					"uom": "Pack",
					"reference_doctype": "Sales Invoice",
					"reference_name": "SINV-2026-00004",
					"remarks": "Sold",
				},
				{
					"transaction_type": "In",
					"qty": 1,
					"uom": "Pack",
					"reference_doctype": "Sales Invoice",
					"reference_name": "SINV-2026-00005",
					"remarks": "Return SINV-2026-00004",
				},
				{
					"transaction_type": "Out",
					"qty": 1,
					"uom": "Pack",
					"reference_doctype": "Sales Invoice",
					"reference_name": "SINV-2026-00005",
					"remarks": "Cancelled SINV-2026-00005",
				},
			],
			initial_qty=1,
		)

		self.assertEqual(lot.remaining_qty, 0.0)
		self.assertEqual(lot.status, "Delivered")
		self.assertIsNone(lot.serial_no)

	def test_lot_received_again_is_active(self):
		# Reactivation posts an In row with the received quantity, serial restored.
		lot = self._lot_after_transactions(
			[
				{
					"transaction_type": "Out",
					"qty": 50,
					"uom": "UNIT",
					"reference_doctype": "Stock Reconciliation",
					"reference_name": "MAT-RECO-2026-00064",
					"remarks": "Zeroed by Stock Reconciliation MAT-RECO-2026-00064",
				},
				{
					"transaction_type": "In",
					"qty": 50,
					"uom": "UNIT",
					"reference_doctype": "Purchase Receipt",
					"reference_name": "MAT-PRE-2026-00009",
					"remarks": "Received from Purchase Receipt MAT-PRE-2026-00009",
				},
			]
		)

		self.assertEqual(lot.remaining_qty, 50.0)
		self.assertEqual(lot.status, "Active")
		self.assertEqual(lot.serial_no, "SN-TEST-0001")
