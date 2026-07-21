# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class StockScanner(Document):
	def _validate_links(self):
		# Link validation runs before validate(); recreate deleted Batches first
		# so draft scanners remain savable after Batch masters were removed.
		self._ensure_item_batches_exist()
		super()._validate_links()

	def _ensure_item_batches_exist(self):
		from beveren_health.beveren_health.customize.scanner import get_or_create_batch

		for row in self.get("items") or []:
			if not row.batch_no or not row.item_code:
				continue
			if frappe.db.exists("Batch", row.batch_no):
				continue

			batch = get_or_create_batch(
				row.item_code,
				row.batch_no,
				getattr(row, "expiry_date", None),
			)
			if batch and batch.name != row.batch_no:
				row.batch_no = batch.name
