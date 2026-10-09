# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

# A stock document (Purchase Receipt / Stock Entry / Stock Reconciliation) posts an Out
# row on a lot when the app counts the pack down or reverses a receipt — see
# `customize.dispensing_lot`.  Such a row is a stock movement, never a sale, so the lot
# becomes `Inactive` with its serial kept and can be received again later.
STOCK_DOC_REVERSAL_DOCTYPES = frozenset({"Purchase Receipt", "Stock Entry", "Stock Reconciliation"})

# Documents that hand a pack to the customer.  Kept in step with
# `customize.dispensing_lot.DISPENSING_LOT_SALE_DOCTYPES`; the controller must not import
# the customize layer, which is loaded after it.
DISPENSING_LOT_SALE_DOCTYPES = frozenset({"Sales Invoice", "Delivery Note"})


def _is_stock_document_out(row):
	"""True for an Out row written by a stock document (count down / reversal)."""
	return row.transaction_type == "Out" and row.reference_doctype in STOCK_DOC_REVERSAL_DOCTYPES


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
				_("Batch {0} belongs to item {1}, not {2}").format(self.batch_no, batch_item, self.item)
			)

	def set_remaining_qty(self):
		if self._net_full_pack_sales() >= 1:
			# A net full-pack sale means the whole physical pack is gone from stock.
			# However, when a return comes back in the dispensing UOM (e.g. UNIT),
			# the lot is reactivated with only the returned quantity.
			returned_dispensing_qty = self._returned_dispensing_qty()
			self.remaining_qty = flt(returned_dispensing_qty)
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
			lot_label = self.name or _("New Dispensing Lot")
			serial_or_name = self.serial_no or self.name or _("N/A")
			frappe.throw(
				_(
					"Dispensing Lot {0} failed validation for item {1} "
					"(serial/lot: {2}, batch: {3}). Remaining qty cannot be negative. "
					"Issued {4}, returned {5}, initial {6}."
				).format(
					lot_label,
					self.item or _("N/A"),
					serial_or_name,
					self.batch_no or _("N/A"),
					issued,
					returned,
					self.initial_qty,
				)
			)

	def set_status(self):
		if flt(self.remaining_qty) <= 0 and flt(self.initial_qty) > 0:
			self.remaining_qty = 0
			if self._zeroed_by_stock_document():
				# Not a sale: the batch was counted down (or a receipt reversed), so the
				# serial stays and the pack comes back when it is received again.
				self.status = "Inactive"
			elif self._has_full_pack_sale():
				self.status = "Delivered"
				self.serial_no = None
			elif self._has_net_issue():
				self.status = "Delivered"
				self.serial_no = None
			else:
				self.status = "Inactive"
			return

		if self._has_full_pack_sale() and flt(self.remaining_qty) > 0:
			# Full pack was sold/consumed, but units were returned in the
			# dispensing UOM — reactivate the lot as partially sold with the
			# quantity that came back. Restore the serial that the full-pack
			# sale had cleared.
			self.status = "Partially Sold"
			self._restore_serial_no_if_active()
			return

		if self._has_net_issue():
			self.status = "Partially Sold"
		else:
			self.status = "Active"
			self._restore_serial_no_if_active()

	def _net_full_pack_sales(self, only_sale_documents=False):
		"""Net full packs sold in stock UOM (Out minus In reversals, e.g. cancelled invoice).

		With `only_sale_documents`, the rows a stock document wrote are left out: they
		count a pack down or reverse a receipt, they are not a sale.
		"""
		if not self.stock_uom:
			return 0

		out = 0
		inp = 0
		for row in self.transactions:
			if row.uom != self.stock_uom:
				continue
			if only_sale_documents and row.reference_doctype not in DISPENSING_LOT_SALE_DOCTYPES:
				continue
			qty = flt(row.qty)
			if row.transaction_type == "Out":
				out += qty
			elif row.transaction_type == "In":
				inp += qty

		return out - inp

	def _has_full_pack_sale(self):
		"""Selling in stock UOM (e.g. Pack) means the whole lot is delivered."""
		return self._net_full_pack_sales(only_sale_documents=True) >= 1

	def _returned_dispensing_qty(self):
		"""Net units returned in the dispensing UOM (e.g. UNIT) from a sales return.

		Used to reactivate a lot that was fully consumed by a stock-UOM (pack) sale
		when only part of the pack is returned in the dispensing UOM.  An In row that
		was later cancelled (a matching Out with "Cancelled" remarks) is excluded so
		the lot returns to Delivered when the return document is cancelled.
		"""
		if not self.stock_uom or self.stock_uom == self.uom:
			return 0

		returned = 0
		for row in self.transactions:
			if row.transaction_type != "In":
				continue
			if row.uom == self.stock_uom:
				continue
			qty = flt(row.qty)
			if qty <= 0:
				continue
			if self._return_reference_was_cancelled(row):
				continue
			returned += qty

		return returned

	def _return_reference_was_cancelled(self, in_row):
		"""True when the return document that created `in_row` has a cancellation Out."""
		if not in_row.reference_doctype or not in_row.reference_name:
			return False

		for out in self.transactions:
			if out.transaction_type != "Out":
				continue
			if out.reference_doctype != in_row.reference_doctype:
				continue
			if out.reference_name != in_row.reference_name:
				continue
			if "Cancelled" in (out.remarks or ""):
				return True
		return False

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

	def _zeroed_by_stock_document(self):
		"""True when remaining was cleared by a stock document, not by a sale.

		Covers a Stock Reconciliation that counts the batch down to zero and every other
		Out the app posts from a stock document (cancelled Purchase Receipt / Stock
		Entry / Stock Reconciliation).  Rows written before the reference was stamped
		are matched on their "Cancelled ..." remarks, the wording older versions used.

		A pack the customer took stays `Delivered` even when a receipt is cancelled
		afterwards, so a full-pack sale wins over this check.
		"""
		if self._has_full_pack_sale():
			return False

		for row in self.transactions:
			if row.transaction_type != "Out":
				continue
			if _is_stock_document_out(row):
				return True
			if "Cancelled" in (row.remarks or ""):
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
