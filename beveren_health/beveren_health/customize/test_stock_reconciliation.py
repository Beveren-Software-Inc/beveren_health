# Copyright (c) 2026, Beveren Software and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from beveren_health.beveren_health.customize.stock_reconciliation import (
	_build_zeroing_item_row,
	_summarise_unreconciled_lines,
	get_warehouse_zeroing_lines,
)

# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]


class IntegrationTestWarehouseZeroingLines(IntegrationTestCase):
	"""
	The zero-quantity lines behind Zero Unreconciled Batches and the Zero Batch from
	Chosen Warehouse button. Both hand the same line shape to Stock Reconciliation, so
	the shape is checked here rather than through a submitted document.
	"""

	def _line(self, **overrides):
		line = {
			"item_code": "ITEM-001",
			"item_name": "Item One",
			"stock_uom": "Nos",
			"warehouse": "Stores - S",
			"batch_no": "BATCH-001",
			"qty": 3.0,
			"valuation_rate": 2.5,
			"value": 7.5,
			"needs_dispensing_lot": False,
			"lots": [],
			"lot_count": 0,
		}
		line.update(overrides)
		return line

	def test_zeroing_row_counts_the_batch_down_to_zero(self):
		row = _build_zeroing_item_row(self._line())

		self.assertEqual(row["qty"], 0)
		self.assertEqual(row["amount"], 0)
		self.assertEqual(row["valuation_rate"], 2.5)
		self.assertEqual(row["current_qty"], 3.0)
		self.assertEqual(row["current_valuation_rate"], 2.5)
		self.assertEqual(row["current_amount"], 7.5)
		self.assertEqual(row["quantity_difference"], -3.0)
		self.assertEqual(row["amount_difference"], -7.5)
		self.assertEqual(row["item_code"], "ITEM-001")
		self.assertEqual(row["batch_no"], "BATCH-001")
		self.assertEqual(row["warehouse"], "Stores - S")
		self.assertEqual(row["use_serial_batch_fields"], 1)
		self.assertEqual(row["allow_zero_valuation_rate"], 1)

	def test_zeroing_row_lists_the_dispensing_lots_of_the_batch(self):
		row = _build_zeroing_item_row(self._line(lots=["LOT-1", "LOT-2"]))

		if not frappe.db.has_column("Stock Reconciliation Item", "custom_dispensing_lot"):
			self.assertNotIn("custom_dispensing_lot", row)
			return

		self.assertEqual(row["custom_dispensing_lot"], "LOT-1\nLOT-2")

	def test_zeroing_row_without_lots_keeps_the_lot_field_empty(self):
		row = _build_zeroing_item_row(self._line())

		self.assertNotIn("custom_dispensing_lot", row)

	def test_summary_totals_lines_warehouses_and_lots(self):
		summary = _summarise_unreconciled_lines(
			[
				self._line(qty=2, value=5, needs_dispensing_lot=True, lot_count=2),
				self._line(batch_no="BATCH-002", qty=1, value=2),
				self._line(item_code="ITEM-002", warehouse="Finished Goods - S", qty=-1, value=-3),
			]
		)

		self.assertEqual(summary["total_lines"], 3)
		self.assertEqual(summary["total_qty"], 2)
		self.assertEqual(summary["total_value"], 4)
		self.assertEqual(summary["warehouse_count"], 2)
		self.assertEqual(summary["lot_lines"], 1)
		self.assertEqual(summary["lot_count"], 2)
		self.assertEqual(summary["warning_lines"], 0)

	def test_warehouse_is_required(self):
		self.assertRaises(frappe.ValidationError, get_warehouse_zeroing_lines, "")

	def test_group_warehouse_is_rejected(self):
		group_warehouse = frappe.db.get_value("Warehouse", {"is_group": 1}, "name")
		if not group_warehouse:
			self.skipTest("No group warehouse on this site.")

		self.assertRaises(frappe.ValidationError, get_warehouse_zeroing_lines, group_warehouse)

	def test_warehouse_of_another_company_is_rejected(self):
		warehouse, company = frappe.db.get_value(
			"Warehouse",
			{"is_group": 0, "company": ("is", "set")},
			["name", "company"],
		)
		if not warehouse:
			self.skipTest("No leaf warehouse with a company on this site.")

		self.assertRaises(
			frappe.ValidationError,
			get_warehouse_zeroing_lines,
			warehouse,
			f"other-company-not-{company}",
		)
