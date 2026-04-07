frappe.provide("custom.barcode_scanner");

// Override the global barcode scan handler
custom.barcode_scanner.handle_scan = function(frm, barcode) {
   
    if (!barcode) return;

    frappe.call({
        method: "beveren_health.beveren_health.utils.scanner.get_item_and_batch_from_barcode",
        args: { barcode: barcode },
        callback: function(r) {
            if (!r.message || !r.message.item_code) {
                frappe.show_alert({
                    message: __("No item found for barcode: {0}", [barcode]),
                    indicator: "red"
                });
                return;
            }

            const { item_code, batch_no, qty } = r.message;

            // Find the items child table (works for most stock doctypes)
            const items_field = frm.fields_dict["items"];
            if (!items_field) return;

            // Derive child doctype from the grid (handles Stock Reconciliation, Stock Entry, etc.)
            const child_doctype =
                (items_field.grid && items_field.grid.doctype) ||
                items_field.df.options ||
                (frm.doc.items && frm.doc.items[0] && frm.doc.items[0].doctype);

            if (!child_doctype) return;

            // Check if item already exists in table (same item + batch)
            let existing_row = null;
            (frm.doc.items || []).forEach(row => {
                if (row.item_code === item_code && row.batch_no === batch_no) {
                    existing_row = row;
                }
            });

            if (existing_row) {
                // Increment qty if row already exists
                frappe.model.set_value(
                    existing_row.doctype,
                    existing_row.name,
                    "qty",
                    (existing_row.qty || 0) + qty
                );
                frappe.show_alert({
                    message: __("Updated qty for {0} - {1}", [item_code, batch_no]),
                    indicator: "green"
                });
            } else {
                // Add new row in the detected child doctype
                let new_row = frappe.model.add_child(frm.doc, child_doctype, "items");
                frappe.model.set_value(new_row.doctype, new_row.name, "item_code", item_code)
                    .then(() => {
                        if (batch_no && new_row.hasOwnProperty("batch_no")) {
                            frappe.model.set_value(new_row.doctype, new_row.name, "batch_no", batch_no);
                        }
                        frappe.model.set_value(new_row.doctype, new_row.name, "qty", qty);
                    });

                frappe.show_alert({
                    message: __("Added {0} - Batch: {1}", [item_code, batch_no || "N/A"]),
                    indicator: "green"
                });
            }

            frm.refresh_field("items");
        }
    });
};

