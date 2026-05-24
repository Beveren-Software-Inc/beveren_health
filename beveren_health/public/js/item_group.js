// Copyright (c) 2026, Beveren Software and contributors
// For license information, please see license.txt

frappe.ui.form.on("Item Group", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Generate EAN Barcodes"), function () {
				frappe.confirm(
					__(
						"This will generate EAN13 barcodes for all items in this group that don't have barcodes. The job will run in the background. Continue?"
					),
					function () {
						frappe.call({
							method:
								"beveren_health.beveren_health.customize.item_group.generate_barcodes_for_item_group",
							args: { item_group: frm.doc.name },
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
			}, __("Actions"));

			frm.add_custom_button(__("Clear Has Serial No"), function () {
				frappe.confirm(
					__(
						"This will set <b>Has Serial No</b> to unchecked on all items in this group. "
						+ "The job runs in the background. Continue?"
					),
					function () {
						frappe.call({
							method:
								"beveren_health.beveren_health.customize.item_group.clear_has_serial_no_for_item_group",
							args: { item_group: frm.doc.name },
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
			}, __("Actions"));

			frm.add_custom_button(__("Migrate Serials to Dispensing Lot"), function () {
				frappe.confirm(
					__(
						"This will create <b>Dispensing Lot</b> records from existing <b>Serial No</b> "
						+ "for all items in this group (pack size / UOM from item conversion). "
						+ "Serial No records are not changed. Runs in the background (up to 45 min). Continue?"
					),
					function () {
						frappe.call({
							method:
								"beveren_health.beveren_health.customize.item_group.migrate_serials_to_dispensing_lots",
							args: { item_group: frm.doc.name },
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
			}, __("Actions"));

			frm.add_custom_button(__("Enable Has Dispense Lot from Lots"), function () {
				frappe.confirm(
					__(
						"This will tick <b>Has Dispense Lot</b> on every item in this group that already "
						+ "has at least one <b>Dispensing Lot</b> record. Runs in the background. Continue?"
					),
					function () {
						frappe.call({
							method:
								"beveren_health.beveren_health.customize.item_group.flag_has_dispense_lot_from_dispensing_lots",
							args: { item_group: frm.doc.name },
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
			}, __("Actions"));
		}

		frm.add_custom_button(__("Reverse UOM Conversions"), function () {
			frappe.confirm(
				__(
					"This will reverse UOM conversions (PACK↔Unit) for all items in this group. Continue?"
				),
				function () {
					frappe.call({
						method:
							"beveren_health.beveren_health.customize.item_group.reverse_uom_conversions",
						args: { item_group: frm.doc.name },
						freeze: true,
						freeze_message: __("Converting UOMs..."),
						callback: function (r) {
							if (r.message && r.message.success) {
								frappe.msgprint({
									title: __("Conversion Started"),
									indicator: "green",
									message: r.message.message || __("Job queued."),
								});
							}
						},
					});
				}
			);
		}, __("Actions"));
	},
});

frappe.realtime.on("item_group_barcode_generation_done", function (data) {
	const msg =
		data.message ||
		(data.error ? __("Barcode generation failed.") : __("Barcode generation completed."));
	frappe.show_alert({
		message: msg,
		indicator: data.error ? "red" : "green",
	});
});

frappe.realtime.on("item_group_clear_serial_no_done", function (data) {
	const msg =
		data.message ||
		(data.error
			? __("Clear Has Serial No failed.")
			: __("Clear Has Serial No completed."));
	frappe.show_alert({
		message: msg,
		indicator: data.error ? "red" : "green",
	});
});

frappe.realtime.on("item_group_migrate_serials_done", function (data) {
	const msg =
		data.message ||
		(data.error
			? __("Serial to Dispensing Lot migration failed.")
			: __("Serial to Dispensing Lot migration completed."));
	frappe.show_alert({
		message: msg,
		indicator: data.error ? "red" : "green",
	});
});

frappe.realtime.on("item_group_flag_dispense_lot_done", function (data) {
	const msg =
		data.message ||
		(data.error
			? __("Enable Has Dispense Lot failed.")
			: __("Enable Has Dispense Lot completed."));
	frappe.show_alert({
		message: msg,
		indicator: data.error ? "red" : "green",
	});
});
