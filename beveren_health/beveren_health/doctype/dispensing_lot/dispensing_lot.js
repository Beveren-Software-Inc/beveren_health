// Copyright (c) 2026, Beveren Software and contributors
// For license information, please see license.txt

frappe.ui.form.on("Dispensing Lot", {
	refresh(frm) {
		frm.set_query("batch_no", () => {
			if (!frm.doc.item) {
				return { filters: { name: ["in", []] } };
			}
			return {
				filters: {
					item: frm.doc.item,
				},
			};
		});

		frm.set_df_property("remaining_qty", "description", __("Updated from transaction rows on save."));
		if (frm.doc.status === "Delivered") {
			frm.set_df_property("serial_no", "description", __("Cleared when the full pack is sold (stock UOM)."));
		}
	},

	item(frm) {
		if (frm.doc.batch_no && frm.doc.item) {
			frappe.db.get_value("Batch", frm.doc.batch_no, "item", (r) => {
				if (r && r.item && r.item !== frm.doc.item) {
					frm.set_value("batch_no", "");
				}
			});
		} else if (!frm.doc.item) {
			frm.set_value("batch_no", "");
		}
	},

	initial_qty(frm) {
		if (frm.is_new() && frm.doc.initial_qty) {
			frm.set_value("remaining_qty", frm.doc.initial_qty);
		}
	},
});
