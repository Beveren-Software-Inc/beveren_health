// Copyright (c) 2026, Beveren Software and contributors
// For license information, please see license.txt

frappe.ui.form.on("Item Group", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Generate EAN Barcodes"), function() {
				frappe.confirm(
					__("This will generate EAN13 barcodes for all items in this group that don't have barcodes. The job will run in the background. Continue?"),
					function() {
						frappe.call({
							method: "beveren_health.beveren_health.customize.item_group.generate_barcodes_for_item_group",
							args: { item_group: frm.doc.name },
							callback: function(r) {
								if (r.message && r.message.queued) {
									frappe.show_alert({
										message: r.message.message,
										indicator: "blue",
									});
								}
							},
							error: function(r) {
								frappe.msgprint(__("Error: {0}", [r.message || "Unknown error"]));
							}
						});
					},
					function() {}
				);
			}, __("Actions"));
		}
		frm.add_custom_button(__('Reverse UOM Conversions'), function() {
            frappe.confirm(
                'This will reverse UOM conversions (PACK↔Unit) for all items in this group. Continue?',
                function() {
                    // User confirmed
                    frappe.call({
                        method: 'beveren_health.beveren_health.customize.item_group.reverse_uom_conversions',
                        args: {
                            item_group: frm.doc.name
                        },
                        freeze: true,
                        freeze_message: __('Converting UOMs...'),
                        callback: function(r) {
                            if (r.message.success) {
                                frappe.msgprint({
                                    title: __('Conversion Complete'),
                                    indicator: 'green',
                                    message: __('Updated {0} items successfully.', [r.message.updated_count])
                                });
                                
                                if (r.message.errors.length > 0) {
                                    frappe.msgprint({
                                        title: __('Errors'),
                                        indicator: 'red',
                                        message: r.message.errors.join('<br>')
                                    });
                                }
                            }
                        }
                    });
                }
            );
        }, __('Actions'));
	}
});

// Show result when background barcode generation completes
frappe.realtime.on("item_group_barcode_generation_done", function(data) {
	const msg = data.message || (data.error ? __("Barcode generation failed.") : __("Barcode generation completed."));
	frappe.show_alert({
		message: msg,
		indicator: data.error ? "red" : "green",
	});
});

