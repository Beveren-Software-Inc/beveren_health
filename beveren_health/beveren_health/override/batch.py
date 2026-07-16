

import frappe
from erpnext.stock.doctype.batch.batch import Batch


# Voucher types that carry custom_expiry_date / custom_manufacturing_date on items
_VOUCHER_DATE_SOURCES = {
	"Purchase Receipt": "Purchase Receipt",
	"Stock Entry": "Stock Entry",
	"Stock Reconciliation": "Stock Reconciliation",
}


def _find_voucher_row_for_batch(voucher, batch):
	"""Find the item row that owns this batch (prefer exact batch_no, then dated item row)."""
	exact = None
	dated_fallback = None
	item_fallback = None

	for row in voucher.items:
		if row.batch_no == batch.name:
			exact = row
			break

		if getattr(row, "item_code", None) != batch.item:
			continue

		has_dates = row.get("custom_expiry_date") or row.get("custom_manufacturing_date")
		if not row.batch_no and has_dates and dated_fallback is None:
			dated_fallback = row
		elif not row.batch_no and item_fallback is None:
			item_fallback = row
		elif has_dates and dated_fallback is None:
			dated_fallback = row
		elif item_fallback is None:
			item_fallback = row

	return exact or dated_fallback or item_fallback


def _apply_dates_from_voucher_row(batch, row, source_label):
	expiry_date = row.get("custom_expiry_date")
	manufacturing_date = row.get("custom_manufacturing_date")
	changed = False

	if expiry_date and batch.expiry_date != expiry_date:
		batch.expiry_date = expiry_date
		changed = True

	if manufacturing_date and batch.manufacturing_date != manufacturing_date:
		batch.manufacturing_date = manufacturing_date
		changed = True

	if changed:
		frappe.msgprint(frappe._("Batch dates updated from {0}").format(source_label))

	return changed


def before_save(self, method=None):
	"""Copy custom expiry / manufacturing dates from the creating voucher onto Batch."""
	if not self.reference_doctype or not self.reference_name:
		return

	if self.reference_doctype not in _VOUCHER_DATE_SOURCES:
		return

	if not frappe.db.exists(self.reference_doctype, self.reference_name):
		return

	voucher = frappe.get_doc(self.reference_doctype, self.reference_name)
	source_label = _VOUCHER_DATE_SOURCES[self.reference_doctype]

	matched_row = _find_voucher_row_for_batch(voucher, self)
	if not matched_row:
		return

	_apply_dates_from_voucher_row(self, matched_row, source_label)


def _batch_nos_from_stock_entry_row(row):
    """Resolve batch name(s) from batch_no or Serial and Batch Bundle."""
    batches = set()
    if row.batch_no:
        batches.add(row.batch_no)

    if row.serial_and_batch_bundle:
        for batch_no in frappe.get_all(
            "Serial and Batch Entry",
            filters={"parent": row.serial_and_batch_bundle, "batch_no": ["is", "set"]},
            pluck="batch_no",
        ):
            if batch_no:
                batches.add(batch_no)

    return batches


@frappe.whitelist()
def update_batch_dates_from_stock_entry(stock_entry):
    """
    Copy custom_expiry_date / custom_manufacturing_date from Stock Entry Detail
    rows onto the linked Batch documents.
    """
    if not stock_entry:
        frappe.throw(frappe._("Stock Entry is required"))

    doc = frappe.get_doc("Stock Entry", stock_entry)
    updated = []
    skipped = []

    for row in doc.items:
        expiry_date = row.get("custom_expiry_date")
        manufacturing_date = row.get("custom_manufacturing_date")
        if not expiry_date and not manufacturing_date:
            continue

        batch_nos = _batch_nos_from_stock_entry_row(row)
        if not batch_nos:
            skipped.append(frappe._("Row {0}: no batch").format(row.idx))
            continue

        for batch_no in batch_nos:
            if not frappe.db.exists("Batch", batch_no):
                skipped.append(frappe._("Row {0}: Batch {1} not found").format(row.idx, batch_no))
                continue

            batch = frappe.get_doc("Batch", batch_no)
            changed = False

            if expiry_date and batch.expiry_date != expiry_date:
                batch.expiry_date = expiry_date
                changed = True

            if manufacturing_date and batch.manufacturing_date != manufacturing_date:
                batch.manufacturing_date = manufacturing_date
                changed = True

            if changed:
                batch.save(ignore_permissions=True)
                updated.append(batch_no)
            elif batch_no not in updated:
                skipped.append(
                    frappe._("Row {0}: Batch {1} already up to date").format(row.idx, batch_no)
                )

    return {
        "updated": list(dict.fromkeys(updated)),
        "skipped": skipped,
        "updated_count": len(dict.fromkeys(updated)),
    }


class CustomBatch(Batch):

    def validate(self):
        original_batch_id = self.batch_id
        existing_batch = frappe.db.get_value(
            "Batch",
            {"batch_id": self.batch_id},
            ["name", "item"],
            as_dict=True
        )
        if existing_batch and existing_batch.item != self.item:
            new_batch_id = f"{self.batch_id}_{self.item}"

            frappe.logger().info(
                f"Batch {self.batch_id} exists for {existing_batch.item}. "
                f"Changing to {new_batch_id}"
            )
      
            self.batch_id = new_batch_id
            self.name = new_batch_id
            self.custom_original_batch_id = original_batch_id
           
        super().validate()