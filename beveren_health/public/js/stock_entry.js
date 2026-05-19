// // Custom scanner field on Stock Entry: custom_scustom_scanner
// // Similar simple pattern to Pick List custom_scan_transactional_barcode

// frappe.ui.form.on("Stock Entry", {
// 	custom_scustom_scanner(frm) {
// 		const barcode = frm.doc.custom_scustom_scanner;
// 		if (!barcode) return;

// 		frappe.call({
// 			method: "beveren_health.beveren_health.utils.scanner.get_item_and_batch_from_barcode",
// 			args: { barcode },
// 			callback(r) {
// 				if (!r.message || !r.message.item_code) {
// 					frappe.msgprint(__("No item found for barcode: {0}", [barcode]));
// 					frm.set_value("custom_scustom_scanner", "");
// 					return;
// 				}

// 				const { item_code, batch_no, qty } = r.message;

// 				// Add row in items (Stock Entry Detail)
// 				const row = frm.add_child("items");
// 				row.item_code = item_code;
// 				if (batch_no) {
// 					row.batch_no = batch_no;
// 				}
// 				row.qty = qty || 1;

// 				frm.refresh_field("items");
// 				frm.set_value("custom_scustom_scanner", "");
// 			},
// 		});
// 	},
// });

frappe.ui.form.on('Stock Entry', {
    onload: function(frm) {
        frm.current_focused_row = null;

        setTimeout(function() {
            setup_row_click_tracking(frm);
        }, 500);

        // Inject highlight CSS once
        if (!document.getElementById('se-scanner-style')) {
            let style = document.createElement('style');
            style.id = 'se-scanner-style';
            style.textContent = `
                .grid-row.row-highlight {
                    background-color: #fff3cd !important;
                    border-left: 4px solid #ffc107 !important;
                    transition: all 0.3s ease;
                }
                .grid-row.row-highlight input {
                    background-color: #fff8e1 !important;
                }
            `;
            document.head.appendChild(style);
        }
    },

    refresh: function(frm) {
        setTimeout(function() {
            setup_row_click_tracking(frm);
        }, 300);
    },

    /** Header scanner field (custom_custom_scanner) — same flow as row scanner */
    custom_custom_scanner: function(frm) {
        const barcode = (frm.doc.custom_custom_scanner || '').trim();
        if (!barcode) return;

        frm.set_value('custom_custom_scanner', '');

        const target = get_stock_entry_scan_row(frm);
        if (!target) {
            frappe.msgprint(__('Add an item row before scanning.'));
            return;
        }

        const { cdt, cdn, row, row_idx } = target;
        run_stock_entry_scan(frm, cdt, cdn, row, barcode, row_idx);
    },
});

function setup_row_click_tracking(frm) {
    if (!frm.fields_dict['items'] || !frm.fields_dict['items'].grid) return;
    let wrapper = frm.fields_dict['items'].grid.wrapper;
    if (!wrapper) return;
    wrapper.off('click.se_scanner', '.grid-row');
    wrapper.on('click.se_scanner', '.grid-row', function() {
        let idx = $(this).attr('data-idx');
        if (idx) {
            frm.current_focused_row = parseInt(idx) - 1;
        }
    });
}

// ─── Scanner field handler ────────────────────────────────────────────────────

function get_stock_entry_scan_row(frm) {
    const items = frm.doc.items || [];
    if (!items.length) {
        return null;
    }

    let row_idx =
        frm.current_focused_row !== null && frm.current_focused_row !== undefined
            ? frm.current_focused_row
            : items.length - 1;

    if (row_idx < 0 || row_idx >= items.length) {
        row_idx = items.length - 1;
    }

    const row = items[row_idx];
    return {
        cdt: row.doctype,
        cdn: row.name,
        row,
        row_idx,
    };
}

function run_stock_entry_scan(frm, cdt, cdn, row, barcode, current_row_idx) {
    barcode = (barcode || '').trim();
    if (!barcode) return;

    const warehouse = get_warehouse_for_stock_entry(frm, row);
    if (!warehouse) {
        frappe.msgprint({
            title: __('Warehouse required'),
            indicator: 'orange',
            message: __(
                'Set <b>To Warehouse</b> or <b>From Warehouse</b> on the Stock Entry header (or on the row) before scanning.'
            ),
        });
        return;
    }

    const process = () => {
        const active_row = locals[cdt] && locals[cdt][cdn] ? locals[cdt][cdn] : row;
        process_scan(
            frm,
            cdt,
            cdn,
            active_row,
            barcode,
            current_row_idx,
            get_warehouse_for_stock_entry(frm, active_row)
        );
    };

    if (frm.is_new()) {
        frm.save_or_update({
            callback: process,
            error: function () {
                frappe.msgprint({
                    title: __('Save Error'),
                    indicator: 'red',
                    message: __('Failed to save document. Please save manually and try again.'),
                });
            },
        });
        return;
    }

    process();
}

frappe.ui.form.on('Stock Entry Detail', {
    custom_scanner: function (frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        const barcode = (row.custom_scanner || '').trim();

        if (!barcode) return;

        const current_row_idx = frm.doc.items.findIndex((r) => r.name === cdn);

        // Clear scanner field; barcode is kept in the closure below
        frappe.model.set_value(cdt, cdn, 'custom_scanner', '');

        run_stock_entry_scan(frm, cdt, cdn, row, barcode, current_row_idx);
    },
});

function get_warehouse_for_stock_entry(frm, row) {
    // Row-level warehouses first (Stock Entry Detail uses s_warehouse / t_warehouse)
    if (row) {
        if (row.t_warehouse) return row.t_warehouse;
        if (row.s_warehouse) return row.s_warehouse;
    }

    const doc = frm.doc;
    const purpose = doc.purpose;

    switch (purpose) {
        case 'Material Receipt':
        case 'Manufacture':
        case 'Repack':
            return doc.to_warehouse || doc.t_warehouse;
        case 'Material Issue':
        case 'Material Transfer for Manufacture':
            return doc.from_warehouse || doc.s_warehouse;
        case 'Material Transfer':
            return doc.to_warehouse || doc.from_warehouse;
        default:
            return (
                doc.to_warehouse ||
                doc.from_warehouse ||
                doc.t_warehouse ||
                doc.s_warehouse
            );
    }
}

function process_scan(frm, cdt, cdn, row, barcode, current_row_idx, warehouse) {
    console.log("Sending to server:", {
        barcode_data: barcode,
        document_name: frm.doc.name,
        doctype: 'Stock Entry',
        current_item_code: row.item_code,
        current_batch_no: row.batch_no || '',
        warehouse: warehouse
    });

    frappe.call({
        method: "beveren_health.beveren_health.customize.scanner.process_batch_scan",
        args: {
            barcode_data: barcode,
            document_name: frm.doc.name,
            doctype: 'Stock Entry',
            current_item_code: row.item_code,
            current_batch_no: row.batch_no || '',
            current_row_name: cdn,
            warehouse: warehouse
        },
        callback: function(r) {
            if (!r.message || !r.message.success) {
                frappe.msgprint({
                    title: __('Scan Error'),
                    indicator: 'red',
                    message: (r.message && r.message.message) || 'Failed to process barcode'
                });
                return;
            }

            let result = r.message;

            switch (result.action) {
                case 'assign_to_current':
                    handle_assign_to_current(frm, cdt, cdn, result, current_row_idx, warehouse);
                    break;
                case 'append_serial':
                    handle_append_serial(frm, cdt, cdn, result, current_row_idx);
                    break;
                case 'create_new_row':
                    handle_create_new_row(frm, result, warehouse);
                    break;
                case 'move_to_existing':
                    handle_move_to_existing(frm, result);
                    break;
            }
            
            // Save and refocus after successful scan
            save_and_refocus_scanner(frm, result);
        },
        error: function(err) {
            console.error('Scan error:', err);
            frappe.msgprint(__('Error processing scan. Check server logs.'));
        }
    });
}

// ─── Save and refocus function ───────────────────────────────────────────────

function save_and_refocus_scanner(frm, result) {
    // Show saving indicator
    frappe.show_alert({ message: __('Saving...'), indicator: 'blue' });
    
    // Save the document
    frm.save_or_update({
        callback: function() {
            frappe.show_alert({ message: __('Saved successfully'), indicator: 'green', timeout: 1 });
            
            // After save, refocus on the appropriate scanner field
            setTimeout(function() {
                refocus_scanner_field(frm, result);
            }, 300);
        },
        error: function() {
            frappe.msgprint({
                title: __('Save Error'),
                indicator: 'red',
                message: __('Failed to save document. Please check and save manually.')
            });
        }
    });
}

function refocus_scanner_field(frm, result) {
    let target_row_idx = null;
    let target_row_name = null;
    
    if (result.action === 'create_new_row') {
        // For new row, focus on the newly created row
        let target_row = frm.doc.items.find(r => r.batch_no === result.batch_no);
        if (target_row) {
            target_row_idx = frm.doc.items.findIndex(r => r.name === target_row.name);
            target_row_name = target_row.name;
        }
    } else if (result.action === 'move_to_existing') {
        // For move to existing, focus on the existing row
        target_row_idx = result.existing_row_index;
        if (target_row_idx !== undefined && frm.doc.items[target_row_idx]) {
            target_row_name = frm.doc.items[target_row_idx].name;
        }
    } else {
        // For assign_to_current and append_serial, focus on the current row
        if (result.row_name) {
            target_row_name = result.row_name;
            target_row_idx = frm.doc.items.findIndex(r => r.name === result.row_name);
        }
    }
    
    // If we couldn't determine by row_name, try to find by batch_no
    if (!target_row_name && result.batch_no) {
        let target_row = frm.doc.items.find(r => r.batch_no === result.batch_no);
        if (target_row) {
            target_row_name = target_row.name;
            target_row_idx = frm.doc.items.findIndex(r => r.name === target_row.name);
        }
    }
    
    // If we still don't have a target, use the current focused row
    if (!target_row_name && frm.current_focused_row !== null && frm.doc.items[frm.current_focused_row]) {
        target_row_name = frm.doc.items[frm.current_focused_row].name;
        target_row_idx = frm.current_focused_row;
    }
    
    // Focus on the scanner field of the target row
    if (target_row_name) {
        setTimeout(function() {
            let grid = frm.fields_dict['items'].grid;
            if (grid && grid.grid_rows_by_docname) {
                let grid_row = grid.grid_rows_by_docname[target_row_name];
                if (grid_row && grid_row.columns) {
                    let scanner_field = grid_row.columns.find(col => col.fieldname === 'custom_scanner');
                    if (scanner_field && scanner_field.$input) {
                        scanner_field.$input.focus();
                        if (target_row_idx !== null) {
                            highlight_row(frm, target_row_idx);
                            scroll_to_row(frm, target_row_idx);
                        }
                    } else {
                        let $row = grid_row.$row;
                        if ($row) {
                            $row.find('input:first').focus();
                        }
                    }
                }
            }
        }, 100);
    }
}

// ─── Case 1 ───────────────────────────────────────────────────────────────────

function handle_assign_to_current(frm, cdt, cdn, result, row_idx, warehouse) {
    frappe.model.set_value(cdt, cdn, 'item_code', result.item_code);
    frappe.model.set_value(cdt, cdn, 'item_name', result.item_name);
    frappe.model.set_value(cdt, cdn, 'use_serial_batch_fields', 1);
    if (result.uom) {
        frappe.model.set_value(cdt, cdn, 'uom', result.uom);
    }
    frappe.model.set_value(cdt, cdn, 'batch_no', result.batch_no);

    // Set appropriate warehouse fields based on Stock Entry purpose
    set_warehouse_for_row(frm, cdt, cdn, warehouse);

    if (result.serial_no) {
        beveren_health.dispensing_lot_scan.set_lots(cdt, cdn, result.serial_no, frm);
    } else {
        frappe.model.set_value(cdt, cdn, 'qty', 1);
        frappe.model.set_value(cdt, cdn, 'transfer_qty', 1);
    }
    if (result.expiry_date) {
        frappe.model.set_value(cdt, cdn, 'expiry_date', result.expiry_date);
        frappe.model.set_value(cdt, cdn, 'custom_expiry_date', result.expiry_date);
    }
    if (result.gtin) {
        frappe.model.set_value(cdt, cdn, 'custom_gstin', result.gtin);
    }
    if (result.mfg_date) {
        frappe.model.set_value(cdt, cdn, 'custom_manufacturing_date', result.mfg_date);
    }

    frm.refresh_field('items');
    frm.current_focused_row = row_idx;
    highlight_row(frm, row_idx);
    scroll_to_row(frm, row_idx);

    frappe.show_alert({
        message: `✓ ${result.item_name} | Batch: ${result.batch_no} | SN: ${result.serial_no || 'N/A'}`,
        indicator: 'green'
    });
}

function set_warehouse_for_row(frm, cdt, cdn, warehouse) {
    if (!warehouse) return;

    const purpose = frm.doc.purpose;
    const doc = frm.doc;

    switch (purpose) {
        case 'Material Receipt':
        case 'Manufacture':
        case 'Repack':
            frappe.model.set_value(cdt, cdn, 't_warehouse', warehouse);
            break;
        case 'Material Issue':
        case 'Material Transfer for Manufacture':
            frappe.model.set_value(cdt, cdn, 's_warehouse', warehouse);
            break;
        case 'Material Transfer':
            frappe.model.set_value(
                cdt,
                cdn,
                's_warehouse',
                doc.from_warehouse || doc.s_warehouse
            );
            frappe.model.set_value(
                cdt,
                cdn,
                't_warehouse',
                doc.to_warehouse || doc.t_warehouse || warehouse
            );
            break;
        default:
            frappe.model.set_value(cdt, cdn, 't_warehouse', warehouse);
    }
}

// ─── Case 2 ───────────────────────────────────────────────────────────────────

function handle_append_serial(frm, cdt, cdn, result, row_idx) {
    frappe.model.set_value(cdt, cdn, 'qty', result.new_qty);
    frappe.model.set_value(cdt, cdn, 'transfer_qty', result.new_qty);
    frappe.model.set_value(cdt, cdn, 'amount', result.new_amount);
    if (result.gtin) {
        frappe.model.set_value(cdt, cdn, 'custom_gstin', result.gtin);
    }
    beveren_health.dispensing_lot_scan.set_lots(
        cdt,
        cdn,
        result.all_dispensing_lots || result.all_serials,
        frm
    );

    frm.refresh_field('items');
    frm.current_focused_row = row_idx;
    highlight_row(frm, row_idx);
    scroll_to_row(frm, row_idx);

    frappe.show_alert({
        message: `✓ Serial appended | Batch: ${result.batch_no} | Qty: ${result.new_qty}`,
        indicator: 'green'
    });
}

// ─── Case 3 ───────────────────────────────────────────────────────────────────

function handle_create_new_row(frm, result, warehouse) {
    let new_row_data = {
        item_code: result.item_code,
        item_name: result.item_name,
        qty: result.qty || 1,
        transfer_qty: result.qty || 1,
        uom: result.uom,
        rate: result.rate || 0,
        amount: result.amount || 0,
        basic_rate: result.rate || 0,
        basic_amount: result.amount || 0,
        batch_no: result.batch_no,
        custom_dispensing_lot: result.serial_no || '',
        expiry_date: result.expiry_date || '',
        custom_expiry_date: result.expiry_date || '',
        custom_manufacturing_date: result.mfg_date || '',
        custom_gstin: result.gtin || '',
        use_serial_batch_fields: 1
    };
    
    // Set warehouse based on purpose
    let purpose = frm.doc.purpose;
    switch(purpose) {
        case 'Material Receipt':
        case 'Manufacture':
        case 'Repack':
            new_row_data.t_warehouse = warehouse;
            break;
        case 'Material Issue':
            new_row_data.s_warehouse = warehouse;
            break;
        case 'Material Transfer':
        case 'Material Transfer for Manufacture':
            new_row_data.s_warehouse = frm.doc.from_warehouse || frm.doc.s_warehouse;
            new_row_data.t_warehouse = frm.doc.to_warehouse || frm.doc.t_warehouse || warehouse;
            break;
        default:
            new_row_data.s_warehouse = warehouse;
            new_row_data.t_warehouse = warehouse;
    }
    
    let new_row = frm.add_child('items', new_row_data);
    frm.refresh_field('items');

    let new_idx = frm.doc.items.findIndex(r => r.name === new_row.name);
    frm.current_focused_row = new_idx;
    highlight_row(frm, new_idx);
    scroll_to_row(frm, new_idx);

    frappe.show_alert({
        message: `✓ New row created | Batch: ${result.batch_no} | SN: ${result.serial_no || 'N/A'}`,
        indicator: 'orange'
    });
}

// ─── Case 4 ───────────────────────────────────────────────────────────────────

function handle_move_to_existing(frm, result) {
    let target_idx = result.existing_row_index;
    let target_row = frm.doc.items[target_idx];

    if (target_row) {
        let cdt = target_row.doctype;
        let cdn = target_row.name;

        if (result.serial_no) {
            let updated_lots = beveren_health.dispensing_lot_scan.append_lot(
                target_row.custom_dispensing_lot,
                result.serial_no
            );
            if (updated_lots !== (target_row.custom_dispensing_lot || "")) {
                beveren_health.dispensing_lot_scan.set_lots(cdt, cdn, updated_lots);

                let serial_count = beveren_health.dispensing_lot_scan.count_lots(updated_lots);
                frappe.model.set_value(cdt, cdn, 'qty', serial_count);
                frappe.model.set_value(cdt, cdn, 'transfer_qty', serial_count);
                frappe.model.set_value(cdt, cdn, 'amount', serial_count * (target_row.rate || 0));
                frappe.model.set_value(cdt, cdn, 'basic_amount', serial_count * (target_row.rate || 0));
            }
        }

        if (result.expiry_date && !target_row.expiry_date) {
            frappe.model.set_value(cdt, cdn, 'expiry_date', result.expiry_date);
            frappe.model.set_value(cdt, cdn, 'custom_expiry_date', result.expiry_date);
        }
        if (result.mfg_date && !target_row.custom_manufacturing_date) {
            frappe.model.set_value(cdt, cdn, 'custom_manufacturing_date', result.mfg_date);
        }
        if (result.gtin && !target_row.custom_gstin) {
            frappe.model.set_value(cdt, cdn, 'custom_gstin', result.gtin);
        }
    }

    frm.refresh_field('items');
    frm.current_focused_row = target_idx;
    highlight_row(frm, target_idx);
    scroll_to_row(frm, target_idx);

    frappe.show_alert({
        message: `↗ Moved to existing batch: ${result.batch_no}`,
        indicator: 'blue'
    });
}

// ─── UI helpers ───────────────────────────────────────────────────────────────

function highlight_row(frm, row_idx) {
    setTimeout(function() {
        if (!frm.fields_dict['items'] || !frm.fields_dict['items'].grid) return;
        let $rows = frm.fields_dict['items'].grid.wrapper.find('.grid-row');
        $rows.removeClass('row-highlight');
        if ($rows[row_idx]) {
            $($rows[row_idx]).addClass('row-highlight');
        }
    }, 150);
}

function scroll_to_row(frm, row_idx) {
    setTimeout(function() {
        if (!frm.fields_dict['items'] || !frm.fields_dict['items'].grid) return;
        
        let $rows = frm.fields_dict['items'].grid.wrapper.find('.grid-row');
        
        if ($rows.length > row_idx && $rows[row_idx]) {
            let rowElement = $rows[row_idx];
            
            if (rowElement && typeof rowElement.scrollIntoView === 'function') {
                rowElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
            } else if (rowElement && rowElement[0] && typeof rowElement[0].scrollIntoView === 'function') {
                rowElement[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
            } else if (rowElement && rowElement.length && rowElement[0]) {
                rowElement[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }
    }, 200);
}