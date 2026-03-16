frappe.ui.form.on("Stock Reconciliation", {
	custom_custom_scanner(frm) {
		const barcode = frm.doc.custom_custom_scanner;
		if (!barcode) return;

		const warehouse = frm.doc.set_warehouse; // the default warehouse on Stock Reconciliation header
		
		if (!warehouse) {
			frappe.msgprint(__("Please set a Warehouse on the form before scanning."));
			frm.set_value("custom_custom_scanner", "");
			return;
		}

		frappe.call({
			method: "beveren_health.beveren_health.utils.scanner.get_item_and_batch_from_barcode",
			args: { barcode, warehouse },
			callback(r) {
				if (!r.message || !r.message.item_code) {
					frappe.msgprint(__("No item found for barcode: {0}", [barcode]));
					frm.set_value("custom_custom_scanner", "");
					return;
				}

				const { item_code, batch_no, qty } = r.message;

				const row = frm.add_child("items");
				row.item_code = item_code;
				console.log()
				row.warehouse = warehouse;

				if (batch_no) {
					row.batch_no = batch_no;
					row.use_serial_batch_fields = 1;
				}

				row.qty = qty || 1;

				frm.refresh_field("items");
				frm.set_value("custom_custom_scanner", "");
			},
		});
	},
});