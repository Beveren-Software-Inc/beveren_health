// Copyright (c) 2026, Beveren Software and contributors
// For license information, please see license.txt

frappe.ui.form.on("Purchase Invoice", {
	set_warehouse(frm) {
		beveren_health.warehouse_cost_center.set_from_warehouse(frm, frm.doc.set_warehouse);
	},
});

frappe.ui.form.on("Purchase Invoice Item", {
	warehouse(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		beveren_health.warehouse_cost_center.set_row_from_warehouse(frm, cdt, cdn, row.warehouse);
	},
});
