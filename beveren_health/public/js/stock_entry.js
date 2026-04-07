// Custom scanner field on Stock Entry: custom_scustom_scanner
// Similar simple pattern to Pick List custom_scan_transactional_barcode

frappe.ui.form.on("Stock Entry", {
	custom_scustom_scanner(frm) {
		const barcode = frm.doc.custom_scustom_scanner;
		if (!barcode) return;

		frappe.call({
			method: "beveren_health.beveren_health.utils.scanner.get_item_and_batch_from_barcode",
			args: { barcode },
			callback(r) {
				if (!r.message || !r.message.item_code) {
					frappe.msgprint(__("No item found for barcode: {0}", [barcode]));
					frm.set_value("custom_scustom_scanner", "");
					return;
				}

				const { item_code, batch_no, qty } = r.message;

				// Add row in items (Stock Entry Detail)
				const row = frm.add_child("items");
				row.item_code = item_code;
				if (batch_no) {
					row.batch_no = batch_no;
				}
				row.qty = qty || 1;

				frm.refresh_field("items");
				frm.set_value("custom_scustom_scanner", "");
			},
		});
	},
});

