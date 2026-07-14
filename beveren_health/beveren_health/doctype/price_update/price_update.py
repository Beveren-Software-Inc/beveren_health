# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

SELLING_PRICE_LIST = "Standard Selling"


class PriceUpdate(Document):
	def validate(self):
		for row in self.items:
			if not row.item:
				continue
			if flt(row.new_price) <= 0:
				frappe.throw(
					_("Row {0}: New Price must be greater than zero (item {1}).").format(row.idx, row.item)
				)

	def on_submit(self):
		"""F024: apply each row's new_price to the Selling price list. Previously this
		doctype collected prices but applied nothing (controller was a no-op)."""
		for row in self.items:
			if row.item:
				self._apply_row(row)

	def on_cancel(self):
		for row in self.items:
			if row.item:
				self._revert_row(row)

	def _find_item_price(self, row):
		filters = {"item_code": row.item, "price_list": SELLING_PRICE_LIST, "selling": 1}
		if row.batch:
			filters["batch_no"] = row.batch
		return frappe.db.get_value("Item Price", filters, ["name", "price_list_rate"], as_dict=True)

	def _apply_row(self, row):
		rate = flt(row.new_price)
		existing = self._find_item_price(row)
		if existing:
			# Capture the true prior rate so on_cancel restores it accurately.
			row.db_set("current_price", flt(existing.price_list_rate))
			frappe.db.set_value("Item Price", existing.name, "price_list_rate", rate)
		else:
			# current_price 0 marks a row whose Item Price this document created,
			# so on_cancel removes it rather than resetting to a bogus rate.
			row.db_set("current_price", 0)
			doc = frappe.get_doc(
				{
					"doctype": "Item Price",
					"item_code": row.item,
					"price_list": SELLING_PRICE_LIST,
					"selling": 1,
					"price_list_rate": rate,
					"valid_from": self.posting_date,
					"batch_no": row.batch or None,
				}
			)
			doc.insert(ignore_permissions=True)

	def _revert_row(self, row):
		existing = self._find_item_price(row)
		if not existing:
			return
		if flt(row.current_price) > 0:
			frappe.db.set_value("Item Price", existing.name, "price_list_rate", flt(row.current_price))
		else:
			frappe.delete_doc("Item Price", existing.name, ignore_permissions=True, force=True)
