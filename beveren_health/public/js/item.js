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
		}
	}
});

