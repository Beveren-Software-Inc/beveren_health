# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr
from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file


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
			frappe.db.set_value("Item", item_code, "custom_has_dispense_lot", 1, update_modified=True)
			updated.append(item_code)
		except Exception as e:
			errors.append(f"{item_code}: {e}")
			frappe.log_error(
				title="Flag Has Dispense Lot from Lots",
				message=f"Item {item_code}: {e}",
			)

	frappe.db.commit()

	message = _("Has Dispense Lot enabled on {0} item(s) ({1} already set, {2} error(s)).").format(
		len(updated), len(skipped), len(errors)
	)

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


def _uom_names_from_file(file_url):
	"""Return UOM names from the 'UOM Name' column of an uploaded spreadsheet."""
	if not file_url:
		frappe.throw(_("Upload the UOM spreadsheet."))

	rows = read_xlsx_file_from_attached_file(file_url=file_url) or []
	if not rows:
		frappe.throw(_("The spreadsheet is empty."))

	header = [cstr(cell).strip().lower() for cell in (rows[0] or [])]
	try:
		name_idx = header.index("uom name")
	except ValueError:
		frappe.throw(_("The spreadsheet must have a UOM Name column."))

	names = []
	seen = set()
	for row in rows[1:]:
		if not row or name_idx >= len(row):
			continue
		name = cstr(row[name_idx]).strip()
		if not name or name.lower() in seen:
			continue
		seen.add(name.lower())
		names.append(name)
	if not names:
		frappe.throw(_("No UOM names found in the UOM Name column."))
	return names


def _find_uom(uom_name):
	if frappe.db.exists("UOM", uom_name):
		return uom_name
	return frappe.db.get_value("UOM", {"uom_name": uom_name})


def import_medical_uoms_from_file(file_url):
	"""Create missing UOMs from the UOM Name column and tick Is Medical on each."""
	if not frappe.db.has_column("UOM", "custom_is_medical"):
		frappe.throw(_("Custom field Is Medical is not on UOM."))

	created = []
	marked = []
	already = []
	errors = []

	for uom_name in _uom_names_from_file(file_url):
		try:
			existing = _find_uom(uom_name)
			if existing:
				if cint(frappe.db.get_value("UOM", existing, "custom_is_medical") or 0):
					already.append(existing)
					continue
				frappe.db.set_value("UOM", existing, "custom_is_medical", 1, update_modified=True)
				marked.append(existing)
				continue

			doc = frappe.get_doc(
				{
					"doctype": "UOM",
					"uom_name": uom_name,
					"enabled": 1,
					"custom_is_medical": 1,
				}
			)
			doc.insert(ignore_permissions=True)
			created.append(doc.name)
		except Exception as e:
			errors.append(f"{uom_name}: {e}")
			frappe.log_error(
				title="Import Medical UOMs",
				message=f"{uom_name}: {frappe.get_traceback()}",
			)

	message = _(
		"Created {0} UOM(s), marked Is Medical on {1} existing UOM(s), " "{2} already medical, {3} error(s)."
	).format(len(created), len(marked), len(already), len(errors))

	return {
		"message": message,
		"created": created,
		"marked": marked,
		"already_medical": already,
		"errors": errors,
	}


@frappe.whitelist()
def import_medical_uoms(file_url: str):
	"""Upload a UOM spreadsheet and mark each UOM Name as medical, creating it if missing."""
	frappe.has_permission("Dispensing Setting", "write", throw=True)
	result = import_medical_uoms_from_file(file_url)
	return result
