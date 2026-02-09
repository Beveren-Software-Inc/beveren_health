// Copyright (c) 2026, Beveren Software and contributors
// For license information, please see license.txt

frappe.ui.form.on("Stock Settings", "refresh", function (frm) {
	frm.add_custom_button(__("Move Expired Batches"), function () {
			frappe.call({
				method: "beveren_health.beveren_health.utils.expiry_movement.trigger_expiry_movement",
				freeze: true,
				freeze_message: __("Moving expired batches to expiry warehouse..."),
				callback(r) {
					if (r.message) {
						const msg = r.message;
						if (msg.success) {
							frappe.show_alert({
								message: msg.message,
								indicator: "green",
							});
							if (msg.stock_entries && msg.stock_entries.length) {
								frappe.msgprint({
									title: __("Expiry Movement Completed"),
									message: __("{0}<br><br>Stock Entries created: {1}", [
										msg.message,
										msg.stock_entries
											.map((n) => `<a href="/app/stock-entry/${n}">${n}</a>`)
											.join(", "),
									]),
									indicator: "green",
								});
							}
						} else {
							frappe.msgprint({
								title: __("Expiry Movement"),
								message: msg.message || __("An error occurred."),
								indicator: "red",
							});
						}
					}
				},
			});
		});
});
