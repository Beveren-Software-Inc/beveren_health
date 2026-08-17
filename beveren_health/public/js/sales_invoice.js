// Copyright (c) 2026, Beveren Software and contributors
// For license information, please see license.txt

function auto_fill_return_lots(frm) {
	if (!frm.doc.return_against || !frm.doc.items?.length) {
		return;
	}

	frappe.call({
		method: "beveren_health.beveren_health.customize.dispensing_lot.resolve_return_lots_for_lines",
		args: {
			doctype: frm.doc.doctype,
			return_against: frm.doc.return_against,
		},
		callback(r) {
			if (!r || !r.message) {
				return;
			}
			const lot_map = r.message;
			frm.doc.items.forEach((row) => {
				if (row.custom_dispensing_lot) {
					return;
				}
				const ref = row.sales_invoice_item || row.dn_detail;
				if (ref && lot_map[ref]) {
					frappe.model.set_value(
						row.doctype,
						row.name,
						"custom_dispensing_lot",
						lot_map[ref]
					);
				}
			});
			frm.refresh_field("items");
		},
	});
}

frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (frm.doc.is_return) {
			auto_fill_return_lots(frm);
		}

		frm.set_query("custom_dispensing_lot", "items", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			if (!row || !row.item_code) {
				return { filters: { name: ["in", []] } };
			}

			const filters = {
				item: row.item_code,
			};

			if (frm.doc.is_return) {
				// A return can put stock back onto a delivered lot (full pack sold)
				// or a partially sold lot — include all non-inactive lots.
				filters.status = ["in", ["Active", "Partially Sold", "Delivered"]];
			} else {
				filters.status = ["in", ["Active", "Partially Sold"]];
				filters.remaining_qty = [">", 0];
			}

			if (row.batch_no) {
				filters.batch_no = row.batch_no;
			}

			return { filters };
		});
	},

	update_stock(frm) {
		(frm.doc.items || []).forEach((row) => {
			set_dispensing_lot_reqd(frm, row.doctype, row.name);
		});
	},
});

function set_dispensing_lot_reqd(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row || !row.item_code) {
		return;
	}
	// Only require lot when the invoice updates stock (DN already handled stock otherwise).
	if (!frm.doc.update_stock) {
		frm.fields_dict.items.grid.update_docfield_property(
			"custom_dispensing_lot",
			"reqd",
			0,
			cdn
		);
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
