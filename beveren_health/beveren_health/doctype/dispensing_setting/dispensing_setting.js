// Copyright (c) 2026, Beveren Software and contributors
// For license information, please see license.txt

frappe.ui.form.on("Dispensing Setting", {
	refresh(frm) {
		if (frm.doc.enable_bulk_lot_qty_correction && frm.perm?.[0]?.write) {
			frm.add_custom_button(__("Bulk Correct Remaining Qty"), () => {
				if (frm.is_dirty()) {
					frappe.msgprint(__("Save Dispensing Setting before starting the correction."));
					return;
				}
				show_bulk_lot_qty_correction();
			});
		}

		frm.add_custom_button(__("Enable Has Dispense Lot from Lots"), function () {
			frappe.confirm(
				__(
					"This will go through every <b>Dispensing Lot</b> and tick <b>Has Dispense Lot</b> " +
						"on the linked Item if it is not already checked. Having lots means the item is a " +
						"dispensing item. Runs in the background. Continue?"
				),
				function () {
					frappe.call({
						method: "beveren_health.beveren_health.doctype.dispensing_setting.dispensing_setting.flag_has_dispense_lot_from_dispensing_lots",
						callback: function (r) {
							if (r.message && r.message.queued) {
								frappe.show_alert({
									message: r.message.message,
									indicator: "blue",
								});
							}
						},
						error: function (r) {
							frappe.msgprint(__("Error: {0}", [r.message || "Unknown error"]));
						},
					});
				},
				function () {}
			);
		});

		frm.add_custom_button(__("Import Medical UOMs"), function () {
			const dialog = new frappe.ui.Dialog({
				title: __("Import Medical UOMs"),
				fields: [
					{
						fieldtype: "HTML",
						fieldname: "help",
						options: __(
							"Upload a spreadsheet with a <b>UOM Name</b> column. Existing UOMs are marked <b>Is Medical</b>. UOMs that do not exist are created."
						),
					},
					{
						fieldname: "file",
						fieldtype: "Attach",
						label: __("UOM Spreadsheet"),
						reqd: 1,
					},
				],
				primary_action_label: __("Import"),
				primary_action(values) {
					frappe.call({
						method: "beveren_health.beveren_health.doctype.dispensing_setting.dispensing_setting.import_medical_uoms",
						args: { file_url: values.file },
						freeze: true,
						freeze_message: __("Importing UOMs..."),
						callback(r) {
							const msg = (r.message && r.message.message) || __("Import finished.");
							const has_errors = r.message && (r.message.errors || []).length;
							frappe.msgprint({
								title: has_errors ? __("UOM Import") : __("UOM Import Complete"),
								indicator: has_errors ? "orange" : "green",
								message: msg,
							});
							dialog.hide();
						},
					});
				},
			});
			dialog.show();
		});
	},
});

frappe.realtime.on("dispensing_setting_flag_dispense_lot_done", function (data) {
	const msg =
		data.message ||
		(data.error
			? __("Enable Has Dispense Lot failed.")
			: __("Enable Has Dispense Lot completed."));
	frappe.show_alert({
		message: msg,
		indicator: data.error ? "red" : "green",
	});
	if (data.message) {
		frappe.msgprint({
			title: data.error
				? __("Enable Has Dispense Lot Failed")
				: __("Enable Has Dispense Lot"),
			indicator: data.error ? "red" : "green",
			message: msg,
		});
	}
});

async function show_bulk_lot_qty_correction() {
	const api = "beveren_health.beveren_health.doctype.dispensing_setting.dispensing_setting";
	const response = await frappe.call({
		method: api + ".preview_bulk_lot_qty_correction",
		freeze: true,
	});
	const lots = response.message || [];
	if (!lots.length) {
		frappe.msgprint(__("No Dispensing Lots have Remaining Qty above Initial Qty."));
		return;
	}

	const dialog = new frappe.ui.Dialog({
		title: __("Bulk Correct Remaining Qty ({0} lots)", [lots.length]),
		size: "extra-large",
		fields: [{ fieldtype: "HTML", fieldname: "preview" }],
		primary_action_label: __("Apply Corrections"),
		async primary_action() {
			const result = await frappe.call({
				method: api + ".apply_bulk_lot_qty_correction",
				args: { lots },
				freeze: true,
				btn: dialog.get_primary_btn(),
			});
			dialog.hide();
			frappe.msgprint(__("Updated {0} lot(s). Skipped {1} lot(s).", [
				result.message.updated, result.message.skipped,
			]));
		},
	});

	const table = $("<table>").addClass("table table-bordered");
	const header = $("<tr>").appendTo($("<thead>").appendTo(table));
	for (const label of [__("Lot"), __("Item"), __("Warehouse"), __("Remaining Qty"), __("Initial Qty")]) {
		$("<th>").text(label).appendTo(header);
	}
	const body = $("<tbody>").appendTo(table);
	for (const lot of lots) {
		const row = $("<tr>").appendTo(body);
		for (const value of [lot.name, lot.item, lot.warehouse, lot.remaining_qty, lot.initial_qty]) {
			$("<td>").text(value ?? "").appendTo(row);
		}
	}
	dialog.fields_dict.preview.$wrapper.append(
		$("<p>").text(__("Apply Corrections will set Remaining Qty to Initial Qty for the lots shown below.")),
		$("<div>").css({ maxHeight: "50vh", overflow: "auto" }).append(table)
	);
	dialog.show();
}
