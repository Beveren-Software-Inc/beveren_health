// Copyright (c) 2026, Beveren Software and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		frm.set_query("custom_dispensing_lot", "items", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			if (!row || !row.item_code) {
				return { filters: { name: ["in", []] } };
			}

			const filters = {
				item: row.item_code,
				status: ["in", ["Active", "Partially Sold"]],
				remaining_qty: [">", 0],
			};

			if (row.batch_no) {
				filters.batch_no = row.batch_no;
			}

			return { filters };
		});
	},
});

function set_dispensing_lot_reqd(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row || !row.item_code) {
		return;
	}
	frappe.db.get_value("Item", row.item_code, "custom_has_dispense_lot", (r) => {
		const reqd = r.message && r.message.custom_has_dispense_lot ? 1 : 0;
		frm.fields_dict.items.grid.update_docfield_property(
			"custom_dispensing_lot",
			"reqd",
			reqd,
			cdn
		);
	});
}

frappe.ui.form.on("Sales Invoice Item", {
	item_code(frm, cdt, cdn) {
		set_dispensing_lot_reqd(frm, cdt, cdn);
	},

	custom_dispensing_lot(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.custom_dispensing_lot) {
			return;
		}

		frappe.db.get_value(
			"Dispensing Lot",
			row.custom_dispensing_lot,
			["batch_no", "item", "uom", "remaining_qty"],
			(r) => {
				if (!r) {
					return;
				}
				if (r.item && r.item !== row.item_code) {
					frappe.msgprint(
						__("Dispensing Lot belongs to item {0}, not {1}", [r.item, row.item_code])
					);
					frappe.model.set_value(cdt, cdn, "custom_dispensing_lot", "");
					return;
				}
				if (r.batch_no && row.batch_no && r.batch_no !== row.batch_no) {
					frappe.msgprint(
						__("Dispensing Lot batch {0} does not match line batch {1}", [
							r.batch_no,
							row.batch_no,
						])
					);
				}
			}
		);
	},
});
