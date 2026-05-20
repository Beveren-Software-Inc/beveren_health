

frappe.ui.form.on('Purchase Receipt', {
    onload: function(frm) {
        frm.current_focused_row = null;

        setTimeout(function() {
            setup_row_click_tracking(frm);
        }, 500);

        // Inject highlight CSS once
        if (!document.getElementById('pr-scanner-style')) {
            let style = document.createElement('style');
            style.id = 'pr-scanner-style';
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
    }
});


function setup_row_click_tracking(frm) {
    if (!frm.fields_dict['items'] || !frm.fields_dict['items'].grid) return;
    let wrapper = frm.fields_dict['items'].grid.wrapper;
    if (!wrapper) return;
    wrapper.off('click.pr_scanner', '.grid-row');
    wrapper.on('click.pr_scanner', '.grid-row', function() {
        let idx = $(this).attr('data-idx');
        if (idx) {
            frm.current_focused_row = parseInt(idx) - 1;
        }
    });
}


// ─── Scanner field handler ────────────────────────────────────────────────────

frappe.ui.form.on('Purchase Receipt Item', {
    custom_scanner: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        let barcode = row.custom_scanner;

        if (!barcode) return;

        // Remember which row triggered this scan
        let current_row_idx = frm.doc.items.findIndex(r => r.name === cdn);

        // Clear scanner immediately so it is ready for the next scan
        frappe.model.set_value(cdt, cdn, 'custom_scanner', '');

        if (frm.is_new()) {
            frm.save_or_update({
                callback: function () {
                    process_pr_scan(frm, cdt, cdn, row, barcode, current_row_idx);
                },
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

        process_pr_scan(frm, cdt, cdn, row, barcode, current_row_idx);
    },
});

function process_pr_scan(frm, cdt, cdn, row, barcode, current_row_idx) {
        frappe.call({
            method: "beveren_health.beveren_health.customize.scanner.process_batch_scan",
            args: {
        barcode_data: barcode,
        document_name: frm.doc.name,
        doctype: 'Purchase Receipt',
        current_item_code: row.item_code,
        current_batch_no: row.batch_no || ''
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

                    // Case 1: First scan on empty row → assign batch + serial
                    case 'assign_to_current':
                        handle_assign_to_current(frm, cdt, cdn, result, current_row_idx);
                        break;

                    // Case 2: Same batch scanned again → append serial only
                    case 'append_serial':
                        handle_append_serial(frm, cdt, cdn, result, current_row_idx);
                        break;

                    // Case 3: Different batch, current row already has a batch → add new child row
                    case 'create_new_row':
                        handle_create_new_row(frm, result);
                        break;

                    // Case 4: Batch found on a different row → move focus there, append serial
                    case 'move_to_existing':
                        handle_move_to_existing(frm, result);
                        break;
                }
                
                // ─── SAVE AND RETURN CURSOR ─────────────────────────────────────
                // After any successful scan, save the document and refocus
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
        // The current row is the one that was just updated
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
            // Find the scanner field in the grid
            let grid = frm.fields_dict['items'].grid;
            if (grid && grid.grid_rows_by_docname) {
                let grid_row = grid.grid_rows_by_docname[target_row_name];
                if (grid_row && grid_row.columns) {
                    // Find the custom_scanner field in this row
                    let scanner_field = grid_row.columns.find(col => col.fieldname === 'custom_scanner');
                    if (scanner_field && scanner_field.$input) {
                        scanner_field.$input.focus();
                        if (target_row_idx !== null) {
                            highlight_row(frm, target_row_idx);
                            scroll_to_row(frm, target_row_idx);
                        }
                    } else {
                        // Fallback: try to focus on any input in the row
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

function handle_assign_to_current(frm, cdt, cdn, result, row_idx) {
    frappe.model.set_value(cdt, cdn, 'item_code', result.item_code);
    frappe.model.set_value(cdt, cdn, 'item_name', result.item_name);
    frappe.model.set_value(cdt, cdn, 'use_serial_batch_fields', 1);
    if (result.uom) {
        frappe.model.set_value(cdt, cdn, 'uom', result.uom);
    }
    frappe.model.set_value(cdt, cdn, 'batch_no', result.batch_no);

    if (result.serial_no) {
        beveren_health.dispensing_lot_scan.set_lots(cdt, cdn, result.serial_no, frm);
    } else {
        frappe.model.set_value(cdt, cdn, 'qty', 1);
    }
    if (result.expiry_date) {
        frappe.model.set_value(cdt, cdn, 'expiry_date', result.expiry_date);
        frappe.model.set_value(cdt, cdn, 'custom_expiry_date', result.expiry_date);
    }
    if (result.gtin){
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


// ─── Case 2 ───────────────────────────────────────────────────────────────────

function handle_append_serial(frm, cdt, cdn, result, row_idx) {
    // Server already persisted qty + serial — sync form model to match
    frappe.model.set_value(cdt, cdn, 'qty', result.new_qty);
    frappe.model.set_value(cdt, cdn, 'amount', result.new_amount);
    beveren_health.dispensing_lot_scan.set_lots(
        cdt,
        cdn,
        result.all_dispensing_lots || result.all_serials
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

function handle_create_new_row(frm, result) {
    // Add a brand-new child row for the different batch
    let new_row = frm.add_child('items', {
        item_code: result.item_code,
        item_name: result.item_name,
        qty: result.qty || 1,
        use_serial_batch_fields: 1,
        uom: result.uom,
        rate: result.rate || 0,
        amount: result.amount || 0,
        batch_no: result.batch_no,
        custom_dispensing_lot: result.serial_no || '',
        expiry_date: result.expiry_date || '',
        custom_expiry_date: result.expiry_date || '',
        custom_manufacturing_date: result.mfg_date || '',
        custom_gstin: result.gtin || ''
    });

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

        // Append serial if not already present
        if (result.serial_no) {
            let updated_lots = beveren_health.dispensing_lot_scan.append_lot(
                target_row.custom_dispensing_lot,
                result.serial_no
            );
            if (updated_lots !== (target_row.custom_dispensing_lot || "")) {
                beveren_health.dispensing_lot_scan.set_lots(cdt, cdn, updated_lots);

                let serial_count = beveren_health.dispensing_lot_scan.count_lots(updated_lots);
                frappe.model.set_value(cdt, cdn, 'qty', serial_count);
                frappe.model.set_value(cdt, cdn, 'amount', serial_count * (target_row.rate || 0));
            }
        }

        // Fill dates if not already set
        if (result.expiry_date && !target_row.expiry_date) {
            frappe.model.set_value(cdt, cdn, 'expiry_date', result.expiry_date);
            frappe.model.set_value(cdt, cdn, 'custom_expiry_date', result.expiry_date);
        }
        if (result.gtin){
        frappe.model.set_value(cdt, cdn, 'custom_gstin', result.gtin);
    }
        if (result.mfg_date && !target_row.custom_manufacturing_date) {
            frappe.model.set_value(cdt, cdn, 'custom_manufacturing_date', result.mfg_date);
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
        
        // Check if the row exists
        if ($rows.length > row_idx && $rows[row_idx]) {
            let rowElement = $rows[row_idx];
            
            // Check if it's a jQuery object or DOM element
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