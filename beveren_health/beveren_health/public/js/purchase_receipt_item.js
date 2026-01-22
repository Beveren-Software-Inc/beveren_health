// Copyright (c) 2026, Beveren Software and contributors
// For license information, please see license.txt

frappe.ui.form.on("Purchase Receipt Item", {
	custom_label_print(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		
		if (!row.item_code) {
			frappe.msgprint(__("Please select an item first"));
			return;
		}

		if (!frm.doc.name) {
			frappe.msgprint(__("Please save the Purchase Receipt first"));
			return;
		}

		// Use Frappe's print system with proper URL
		let url = `/printview?doctype=Purchase Receipt&name=${encodeURIComponent(frm.doc.name)}&format=Medication Label&item_row_name=${encodeURIComponent(row.name)}`;
		
		// Open print dialog in new window
		window.open(url, '_blank');
	}
});
