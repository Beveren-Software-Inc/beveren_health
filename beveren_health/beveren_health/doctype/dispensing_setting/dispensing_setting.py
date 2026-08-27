# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class DispensingSetting(Document):
	pass


def _run_flag_has_dispense_lot_from_lots():
	"""
	Walk every Dispensing Lot. If the linked Item does not have Has Dispense Lot
	checked, tick it — having lots means the item is a dispensing item.
	"""
	if not frappe.db.has_column("Item", "custom_has_dispense_lot"):
		return {
			"message": _("Custom field custom_has_dispense_lot is not on Item."),
			"updated_count": 0,
			"skipped_count": 0,
			"errors": [],
		}

	item_codes = frappe.db.sql(
		"""
		SELECT DISTINCT item
		FROM `tabDispensing Lot`
		WHERE item IS NOT NULL AND item != ''
		""",
		pluck=True,
	)

	if not item_codes:
		return {
			"message": _("No Dispensing Lots found."),
			"updated_count": 0,
			"skipped_count": 0,
			"errors": [],
		}

	updated = []
	skipped = []
	errors = []

	for item_code in item_codes:
		try:
			if not frappe.db.exists("Item", item_code):
				errors.append(f"{item_code}: Item not found")
				continue
			if cint(frappe.db.get_value("Item", item_code, "custom_has_dispense_lot") or 0):
				skipped.append(item_code)
				continue
			frappe.db.set_value(
				"Item", item_code, "custom_has_dispense_lot", 1, update_modified=True
			)
			updated.append(item_code)
		except Exception as e:
			errors.append(f"{item_code}: {e}")
			frappe.log_error(
				title="Flag Has Dispense Lot from Lots",
				message=f"Item {item_code}: {e}",
			)

	frappe.db.commit()

	message = _(
		"Has Dispense Lot enabled on {0} item(s) ({1} already set, {2} error(s))."
	).format(len(updated), len(skipped), len(errors))

	return {
		"message": message,
		"updated_count": len(updated),
		"skipped_count": len(skipped),
		"updated_items": updated,
		"errors": errors,
	}


def _run_flag_has_dispense_lot_from_lots_job():
	try:
		result = _run_flag_has_dispense_lot_from_lots()
		_notify_flag_has_dispense_lot_from_lots_done(result)
	except Exception as e:
		frappe.log_error(
			title="Flag Has Dispense Lot from Lots Job",
			message=frappe.get_traceback(),
		)
		_notify_flag_has_dispense_lot_from_lots_done(e)


def _notify_flag_has_dispense_lot_from_lots_done(result):
	if result is None or isinstance(result, Exception):
		frappe.publish_realtime(
			"dispensing_setting_flag_dispense_lot_done",
			{
				"error": True,
				"message": str(result) if result else _("Job failed."),
			},
		)
		return

	frappe.publish_realtime(
		"dispensing_setting_flag_dispense_lot_done",
		{
			"message": result.get("message"),
			"result": result,
		},
	)


@frappe.whitelist()
def flag_has_dispense_lot_from_dispensing_lots():
	"""Enable Has Dispense Lot on every Item that already has Dispensing Lot records."""
	frappe.has_permission("Dispensing Setting", "write", throw=True)

	frappe.enqueue(
		method="beveren_health.beveren_health.doctype.dispensing_setting.dispensing_setting._run_flag_has_dispense_lot_from_lots_job",
		queue="long",
		timeout=3600,
		job_name="Flag Has Dispense Lot from Dispensing Lots",
	)
	return {
		"queued": True,
		"message": _(
			"Enabling Has Dispense Lot for all items that have Dispensing Lots has started in the background."
		),
	}
