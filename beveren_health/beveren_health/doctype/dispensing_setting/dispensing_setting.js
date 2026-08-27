// Copyright (c) 2026, Beveren Software and contributors
// For license information, please see license.txt

frappe.ui.form.on("Dispensing Setting", {
	refresh(frm) {
		frm.add_custom_button(__("Enable Has Dispense Lot from Lots"), function () {
			frappe.confirm(
				__(
					"This will go through every <b>Dispensing Lot</b> and tick <b>Has Dispense Lot</b> "
					+ "on the linked Item if it is not already checked. Having lots means the item is a "
					+ "dispensing item. Runs in the background. Continue?"
				),
				function () {
					frappe.call({
						method:
							"beveren_health.beveren_health.doctype.dispensing_setting.dispensing_setting.flag_has_dispense_lot_from_dispensing_lots",
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
			title: data.error ? __("Enable Has Dispense Lot Failed") : __("Enable Has Dispense Lot"),
			indicator: data.error ? "red" : "green",
			message: msg,
		});
	}
});
