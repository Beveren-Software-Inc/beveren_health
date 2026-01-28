// Copyright (c) 2026, Beveren Software and contributors
// For license information, please see license.txt

frappe.ui.form.on("Item Group", {
	refresh(frm) {
		// Add button to generate barcodes for all items in this group
		if (!frm.is_new()) {
			frm.add_custom_button(__("Generate EAN Barcodes"), function() {
				frappe.confirm(
					__("This will generate EAN13 barcodes for all items in this group that don't have barcodes. Continue?"),
					function() {
						// Yes
						frappe.call({
							method: "beveren_health.beveren_health.customize.item_group.generate_barcodes_for_item_group",
							args: {
								item_group: frm.doc.name
							},
							freeze: true,
							freeze_message: __("Generating barcodes..."),
							callback: function(r) {
								if (r.message) {
									frappe.show_alert({
										message: __("Barcodes generated successfully"),
										indicator: "green"
									});
								}
							},
							error: function(r) {
								frappe.msgprint(__("Error: {0}", [r.message || "Unknown error"]));
							}
						});
					},
					function() {
						// No
					}
				);
			}, __("Actions"));
		}
	}
});
