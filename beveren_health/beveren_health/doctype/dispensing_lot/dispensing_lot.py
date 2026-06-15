# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class DispensingLot(Document):
	def validate(self):
		self.set_stock_uom_from_item()
		self.validate_batch_item()
		self.set_remaining_qty()
		self.set_status()

	def set_stock_uom_from_item(self):
		if self.item and not self.stock_uom:
			self.stock_uom = frappe.db.get_value("Item", self.item, "stock_uom")

	def validate_batch_item(self):
		if not self.batch_no or not self.item:
			return

		batch_item = frappe.db.get_value("Batch", self.batch_no, "item")
		if batch_item and batch_item != self.item:
			frappe.throw(
				_("Batch {0} belongs to item {1}, not {2}").format(
					self.batch_no, batch_item, self.item
				)
			)

	def set_remaining_qty(self):
		if self._net_full_pack_sales() >= 1:
			self.remaining_qty = 0
			return

		issued = 0
		returned = 0

		for row in self.transactions:
			if row.transaction_type == "Transfer":
				continue
			if row.uom == self.stock_uom and flt(row.qty) >= 1:
				continue
			qty = flt(row.qty)
			if row.transaction_type == "In":
				returned += qty
			elif row.transaction_type == "Out":
				issued += qty

		self.remaining_qty = flt(self.initial_qty) - issued + returned

		if self.remaining_qty < 0:
			frappe.throw(
				_("Remaining qty cannot be negative. Issued {0}, returned {1}, initial {2}.").format(
					issued, returned, self.initial_qty
				)
			)

	def set_status(self):
		if flt(self.remaining_qty) <= 0 and flt(self.initial_qty) > 0:
			self.remaining_qty = 0
			if self._has_full_pack_sale():
				self.status = "Delivered"
				self.serial_no = None
			elif self._cancelled_to_zero():
				self.status = "Inactive"
			elif self._has_net_issue():
				self.status = "Delivered"
				self.serial_no = None
			else:
				self.status = "Inactive"
			return

		if self._has_net_issue():
			self.status = "Partially Sold"
		else:
			self.status = "Active"
			self._restore_serial_no_if_active()

	def _net_full_pack_sales(self):
		"""Net full packs sold in stock UOM (Out minus In reversals, e.g. cancelled invoice)."""
		if not self.stock_uom:
			return 0

		out = 0
		inp = 0
		for row in self.transactions:
			if row.uom != self.stock_uom:
				continue
			qty = flt(row.qty)
			if row.transaction_type == "Out":
				out += qty
			elif row.transaction_type == "In":
				inp += qty

		return out - inp

	def _has_full_pack_sale(self):
		"""Selling in stock UOM (e.g. Pack) means the whole lot is delivered."""
		return self._net_full_pack_sales() >= 1

	def _restore_serial_no_if_active(self):
		if self.serial_no:
			return
		if self.name and not (self.name or "").startswith("DL-"):
			self.serial_no = self.name

	def _has_net_issue(self):
		issued = 0
		returned = 0

		for row in self.transactions:
			if row.transaction_type == "Transfer":
				continue
			qty = flt(row.qty)
			if row.transaction_type == "In":
				returned += qty
			elif row.transaction_type == "Out":
				issued += qty

		return issued > returned

	def _cancelled_to_zero(self):
		"""True when remaining was cleared by cancelling a stock document (not a sale)."""
		for row in self.transactions:
			if row.transaction_type == "Out" and "Cancelled" in (row.remarks or ""):
				return True
		return False

	def before_insert(self):
		self.set_stock_uom_from_item()
		if self.remaining_qty is None:
			self.remaining_qty = flt(self.initial_qty)
		if not self.status:
			self.status = "Active"


@frappe.whitelist()
def add_transaction(
	dispensing_lot,
	qty,
	reference_doctype=None,
	reference_name=None,
	transaction_type="Out",
	posting_date=None,
	remarks=None,
	uom=None,
):
	"""Record a transaction and update remaining qty. For use from Sales Invoice etc."""
	doc = frappe.get_doc("Dispensing Lot", dispensing_lot)
	row_uom = uom or doc.uom

	doc.append(
		"transactions",
		{
			"posting_date": posting_date or frappe.utils.today(),
			"transaction_type": transaction_type,
			"qty": flt(qty),
			"uom": row_uom,
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"remarks": remarks,
		},
	)
	doc.save()
	return {
		"name": doc.name,
		"remaining_qty": doc.remaining_qty,
		"status": doc.status,
		"serial_no": doc.serial_no,
	}
