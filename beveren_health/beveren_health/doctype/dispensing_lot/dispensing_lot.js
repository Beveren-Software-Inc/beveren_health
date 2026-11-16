// Copyright (c) 2026, Beveren Software and contributors
// For license information, please see license.txt

frappe.ui.form.on("Dispensing Lot", {
	refresh(frm) {
		if (!frm.is_new() && frm.perm?.[0]?.write &&
			flt(frm.doc.remaining_qty) > flt(frm.doc.initial_qty)) {
			frm.add_custom_button(__("Correct Remaining Qty"), () => {
				if (frm.is_dirty()) {
					frappe.msgprint(__("Save or discard your changes before correcting the balance."));
					return;
				}

				frappe.confirm(
					__("Set Remaining Qty to Initial Qty for this lot?"),
					async () => {
						const response = await frappe.call({
							method: "beveren_health.beveren_health.doctype.dispensing_lot.dispensing_lot.correct_remaining_qty",
							args: { name: frm.doc.name },
							freeze: true,
						});
						await frm.reload_doc();
						frappe.show_alert({
							message: response.message ? __("Remaining Qty corrected.") : __("No correction needed."),
							indicator: response.message ? "green" : "blue",
						});
					}
				);
			});
		}

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

		frm.set_df_property(
			"remaining_qty",
			"description",
			__("Updated from transaction rows on save.")
		);
		if (frm.doc.status === "Delivered") {
			frm.set_df_property(
				"serial_no",
				"description",
				__("Cleared when the full pack is sold (stock UOM).")
			);
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
