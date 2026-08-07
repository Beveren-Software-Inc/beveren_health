// Copyright (c) 2026, Beveren Software and contributors
// For license information, please see license.txt

frappe.ui.form.on("Item", {
	refresh(frm) {
		
		if (!frm.is_new()) {
			frm.add_custom_button(__("Generate Barcode"), function() {
				frappe.call({
					method: "beveren_health.beveren_health.customize.item_barcode.generate_barcode_for_item",
					args: { item_code: frm.doc.name },
					freeze: true,
					freeze_message: __("Generating barcode..."),
					callback(r) {
						if (r.message && r.message.success) {
							frappe.show_alert({ message: r.message.message, indicator: "green" });
							frm.reload_doc();
						}
					},
					error(r) {
						frappe.msgprint(__("Error: {0}", [r.message || "Unknown error"]));
					}
				});
			}, __("Actions"));

			frm.add_custom_button(__("Migrate Serials to Dispensing Lot"), function () {
				frappe.confirm(
					__(
						"This will create <b>Dispensing Lot</b> records from existing <b>Serial No</b> "
						+ "for this item (serial → lot identity, batch from Serial No, pack size / UNIT from item). "
						+ "Serial No records are not changed. Use this for old stock that never got dispensing lots. Continue?"
					),
					function () {
						frappe.call({
							method:
								"beveren_health.beveren_health.customize.item.migrate_serials_to_dispensing_lots_for_item",
							args: { item_code: frm.doc.name },
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
	}
});

frappe.realtime.on("item_migrate_serials_done", function (data) {
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
