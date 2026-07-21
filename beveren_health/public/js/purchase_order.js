// Copyright (c) 2026, Beveren Software and contributors
// For license information, please see license.txt

frappe.ui.form.on("Purchase Order", {
	set_warehouse(frm) {
		beveren_health.warehouse_cost_center.set_from_warehouse(frm, frm.doc.set_warehouse);
	},
});

frappe.ui.form.on("Purchase Order Item", {
	warehouse(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		beveren_health.warehouse_cost_center.set_row_from_warehouse(frm, cdt, cdn, row.warehouse);
	},
});
