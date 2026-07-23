

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

		if (!frm.is_new()) {
			frm.add_custom_button(__("Batch Label Print"), function () {
				show_pr_batch_range_dialog(frm);
			}, __("Actions"));
		}
    },

	set_warehouse: function (frm) {
		beveren_health.warehouse_cost_center.set_from_warehouse(frm, frm.doc.set_warehouse);
	},
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
	warehouse: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		beveren_health.warehouse_cost_center.set_row_from_warehouse(frm, cdt, cdn, row.warehouse);
	},

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
        current_batch_no: row.batch_no || '',
		current_row_name: row.name,
		warehouse: row.warehouse || frm.doc.set_warehouse || '',
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
                
                beveren_health.auto_save_scan.after_successful_scan(
					frm,
					result,
					refocus_scanner_field
				);
            },
            error: function(err) {
                console.error('Scan error:', err);
                frappe.msgprint(__('Error processing scan. Check server logs.'));
            }
        });
}


// ─── Save and refocus function ───────────────────────────────────────────────

function save_and_refocus_scanner(frm, result) {
	beveren_health.auto_save_scan.save_and_refocus(frm, result, refocus_scanner_field);
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
	if (result.server_persisted) {
		beveren_health.auto_save_scan.patch_row(cdt, cdn, {
			item_code: result.item_code,
			item_name: result.item_name,
			use_serial_batch_fields: 1,
			uom: result.uom || locals[cdt][cdn].uom,
			batch_no: result.batch_no,
			qty: result.qty || 1,
			received_qty: result.received_qty != null ? result.received_qty : result.qty || 1,
			rate: result.rate || 0,
			amount: result.amount || 0,
			custom_dispensing_lot: result.serial_no || "",
			custom_expiry_date: result.expiry_date || "",
			custom_manufacturing_date: result.mfg_date || "",
			custom_gstin: result.gtin || "",
		});
	} else {
		frappe.model.set_value(cdt, cdn, "item_code", result.item_code);
		frappe.model.set_value(cdt, cdn, "item_name", result.item_name);
		frappe.model.set_value(cdt, cdn, "use_serial_batch_fields", 1);
		if (result.uom) {
			frappe.model.set_value(cdt, cdn, "uom", result.uom);
		}
		frappe.model.set_value(cdt, cdn, "batch_no", result.batch_no);

		if (result.serial_no) {
			beveren_health.dispensing_lot_scan.set_lots(cdt, cdn, result.serial_no, frm);
		} else {
			frappe.model.set_value(cdt, cdn, "qty", 1);
		}
		if (result.expiry_date) {
			frappe.model.set_value(cdt, cdn, "custom_expiry_date", result.expiry_date);
		}
		if (result.gtin) {
			frappe.model.set_value(cdt, cdn, "custom_gstin", result.gtin);
		}
		if (result.mfg_date) {
			frappe.model.set_value(cdt, cdn, "custom_manufacturing_date", result.mfg_date);
		}
	}

	frm.refresh_field("items");
	frm.current_focused_row = row_idx;
	highlight_row(frm, row_idx);
	scroll_to_row(frm, row_idx);

	frappe.show_alert({
		message: `✓ ${result.item_name} | Batch: ${result.batch_no} | SN: ${result.serial_no || "N/A"}`,
		indicator: "green",
	});
}


// ─── Case 2 ───────────────────────────────────────────────────────────────────

function handle_append_serial(frm, cdt, cdn, result, row_idx) {
	if (result.server_persisted) {
		beveren_health.auto_save_scan.patch_row(cdt, cdn, {
			qty: result.new_qty,
			received_qty: result.received_qty != null ? result.received_qty : result.new_qty,
			amount: result.new_amount,
			custom_dispensing_lot: result.all_dispensing_lots || result.all_serials || "",
		});
	} else {
		frappe.model.set_value(cdt, cdn, "qty", result.new_qty);
		frappe.model.set_value(cdt, cdn, "amount", result.new_amount);
		beveren_health.dispensing_lot_scan.set_lots(
			cdt,
			cdn,
			result.all_dispensing_lots || result.all_serials
		);
	}

	frm.refresh_field("items");
	frm.current_focused_row = row_idx;
	highlight_row(frm, row_idx);
	scroll_to_row(frm, row_idx);

	frappe.show_alert({
		message: `✓ Serial appended | Batch: ${result.batch_no} | Qty: ${result.new_qty}`,
		indicator: "green",
	});
}


// ─── Case 3 ───────────────────────────────────────────────────────────────────

function handle_create_new_row(frm, result) {
	if (result.server_persisted) {
		beveren_health.auto_save_scan.after_server_created_row(
			frm,
			result,
			refocus_scanner_field,
			() => {
				let target = null;
				if (result.row_name) {
					target = frm.doc.items.find((r) => r.name === result.row_name);
				}
				if (!target && result.batch_no) {
					target = frm.doc.items.find((r) => r.batch_no === result.batch_no);
				}
				const new_idx = target
					? frm.doc.items.findIndex((r) => r.name === target.name)
					: frm.doc.items.length - 1;
				frm.current_focused_row = new_idx;
				highlight_row(frm, new_idx);
				scroll_to_row(frm, new_idx);
			}
		);
		return;
	}

	let new_row = frm.add_child("items", {
		item_code: result.item_code,
		item_name: result.item_name,
		qty: result.qty || 1,
		use_serial_batch_fields: 1,
		uom: result.uom,
		rate: result.rate || 0,
		amount: result.amount || 0,
		batch_no: result.batch_no,
		custom_dispensing_lot: result.serial_no || "",
		custom_expiry_date: result.expiry_date || "",
		custom_manufacturing_date: result.mfg_date || "",
		custom_gstin: result.gtin || "",
		received_qty: result.received_qty != null ? result.received_qty : result.qty || 1,
	});

	frm.refresh_field("items");

	let new_idx = frm.doc.items.findIndex((r) => r.name === new_row.name);
	frm.current_focused_row = new_idx;
	highlight_row(frm, new_idx);
	scroll_to_row(frm, new_idx);

	frappe.show_alert({
		message: `✓ New row created | Batch: ${result.batch_no} | SN: ${result.serial_no || "N/A"}`,
		indicator: "orange",
	});
}


// ─── Case 4 ───────────────────────────────────────────────────────────────────

function handle_move_to_existing(frm, result) {
	let target_idx = result.existing_row_index;
	let target_row = frm.doc.items[target_idx];

	if (target_row) {
		let cdt = target_row.doctype;
		let cdn = target_row.name;

		if (result.server_persisted) {
			beveren_health.auto_save_scan.patch_row(cdt, cdn, {
				qty: result.new_qty != null ? result.new_qty : target_row.qty,
				received_qty:
					result.received_qty != null
						? result.received_qty
						: result.new_qty != null
							? result.new_qty
							: target_row.received_qty,
				amount: result.new_amount != null ? result.new_amount : target_row.amount,
				custom_dispensing_lot:
					result.all_dispensing_lots ||
					result.all_serials ||
					target_row.custom_dispensing_lot,
			});
		} else if (result.serial_no) {
			let updated_lots = beveren_health.dispensing_lot_scan.append_lot(
				target_row.custom_dispensing_lot,
				result.serial_no
			);
			if (updated_lots !== (target_row.custom_dispensing_lot || "")) {
				beveren_health.dispensing_lot_scan.set_lots(cdt, cdn, updated_lots);

				let serial_count = beveren_health.dispensing_lot_scan.count_lots(updated_lots);
				frappe.model.set_value(cdt, cdn, "qty", serial_count);
				frappe.model.set_value(cdt, cdn, "amount", serial_count * (target_row.rate || 0));
			}
		}

		if (!result.server_persisted) {
			if (result.expiry_date && !target_row.custom_expiry_date) {
				frappe.model.set_value(cdt, cdn, "custom_expiry_date", result.expiry_date);
			}
			if (result.gtin) {
				frappe.model.set_value(cdt, cdn, "custom_gstin", result.gtin);
			}
			if (result.mfg_date && !target_row.custom_manufacturing_date) {
				frappe.model.set_value(cdt, cdn, "custom_manufacturing_date", result.mfg_date);
			}
		}
	}

	frm.refresh_field("items");
	frm.current_focused_row = target_idx;
	highlight_row(frm, target_idx);
	scroll_to_row(frm, target_idx);

	frappe.show_alert({
		message: `↗ Moved to existing batch: ${result.batch_no}`,
		indicator: "blue",
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

// Batch printing
const PR_LABEL_CSS = `
	body { font-family: Arial, sans-serif; margin: 0; padding: 0; box-sizing: border-box; }
	@page { size: 2.299in 1.5in; margin: 0; }
	.label-page { width: 2.299in; height: 1.5in; padding: 5px; box-sizing: border-box; page-break-after: always; }
	.label-page:last-child { page-break-after: auto; }
	.medication-label { width: 100%; height: 100%; border: 1px solid #000; padding: 5px; box-sizing: border-box; overflow: hidden; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; }
	.barcode-section { text-align: center; margin-bottom: 2px; }
	.barcode-section img { max-width: 100%; height: 52px; margin-bottom: 1px; image-rendering: crisp-edges; }
	.details-section { padding-top: 1px; font-size: 7px; line-height: 1.1; text-align: center; width: 100%; }
	.detail-row { margin-bottom: 1px; line-height: 1.1; }
	.item-name-line { font-family: Georgia, 'Times New Roman', serif; font-size: 8px; font-weight: bold; margin-bottom: 2px; }
	.price-row { font-size: 9px; }
	.price-value { font-weight: 900; font-size: 9px; }
	img { max-width: 100%; height: auto; }
`;

function build_pr_label_html(data, branch_display) {
	const item_code = data.item_code || "N/A";
	const item_name_line_val = data.item_name_line || "N/A";
	const standard_selling_price = data.standard_selling_price != null ? data.standard_selling_price : "N/A";
	const batch_number = data.batch_no || "N/A";
	const expiry_date = data.expiry_date != null ? data.expiry_date : "N/A";
	const branch = branch_display || "N/A";

	return `
		<div class="medication-label">
			<div class="details-section" style="border-top: none; padding-top: 0; margin-top: 2px; margin-bottom: 1px;">
				<div class="detail-row"><strong>${branch}</strong></div>
			</div>
			<div class="barcode-section">
				<img src="${data.barcode_image}" alt="Barcode" />
			</div>
			<div class="details-section">
				<div class="detail-row"><span>${item_code} - </span><span class="item-name-line">${item_name_line_val}</span></div>
				<div class="detail-row"><strong>Price:</strong> <span class="price-value">${standard_selling_price}</span></div>
				<div class="detail-row"><strong>Batch No:</strong> ${batch_number}</div>
				<div class="detail-row"><strong>Expiry Date:</strong> ${expiry_date}</div>
			</div>
		</div>
	`;
}

function show_pr_batch_range_dialog(frm) {
	const items = frm.doc.items || [];
	const max_rows = items.length;

	if (max_rows === 0) {
		frappe.msgprint(__("No items found in this Purchase Receipt."));
		return;
	}

	const d = new frappe.ui.Dialog({
		title: __("Select Item Row Range for Label Printing"),
		fields: [
			{
				fieldtype: "Section Break",
				label: __("Row Range"),
			},
			{
				fieldname: "from_row",
				fieldtype: "Int",
				label: __("From Row"),
				default: 1,
				reqd: 1,
				description: __(`Enter row number (1 to ${max_rows})`),
			},
			{
				fieldname: "to_row",
				fieldtype: "Int",
				label: __("To Row"),
				default: max_rows,
				reqd: 1,
				description: __(`Enter row number (1 to ${max_rows}), total rows: ${max_rows}`),
			},
			{
				fieldname: "cost_center",
				fieldtype: "Link",
				label: __("Branch (Cost Center)"),
				options: "Cost Center",
				description: __("Shown as Branch on the label. Leave blank to use form value."),
				default: frm.doc.cost_center || "",
			},
		],
		primary_action_label: __("Load Items"),
		primary_action(values) {
			const from_row = Math.max(1, parseInt(values.from_row, 10) || 1);
			const to_row = Math.min(max_rows, parseInt(values.to_row, 10) || max_rows);

			if (from_row > to_row) {
				frappe.msgprint(__("'From Row' must be less than or equal to 'To Row'."));
				return;
			}

			d.hide();
			const selected_items = items.slice(from_row - 1, to_row);
			show_pr_label_table_dialog(frm, selected_items, values.cost_center || "");
		},
	});

	d.show();
}

function show_pr_label_table_dialog(frm, selected_items, cost_center) {
	const table_id = "pr_label_table_" + frappe.utils.get_random(5);

	const fields = [
		{
			fieldname: "label_table_html",
			fieldtype: "HTML",
			label: "",
			options: build_pr_label_table_html(selected_items, table_id),
		},
	];

	const d2 = new frappe.ui.Dialog({
		title: __("Review & Print Labels"),
		fields: fields,
		size: "extra-large",
		primary_action_label: __("Print All"),
		primary_action() {
			const print_rows = get_pr_print_rows_from_table(table_id, selected_items);
			if (!print_rows.length) {
				frappe.msgprint(__("No items to print."));
				return;
			}
			d2.hide();
			execute_pr_label_print(frm, print_rows, cost_center);
		},
	});

	d2.show();
	$(d2.wrapper).find(".modal-dialog").css("max-width", "900px");
}

function build_pr_label_table_html(selected_items, table_id) {
	const rows = selected_items.map((item, idx) => {
		const row_num = idx + 1;
		const item_code = item.item_code || "";
		const item_name = item.item_name || "";
		const batch_no = item.batch_no || "";
		const qty = flt(item.qty, 0) || 0;

		return `
			<tr data-idx="${idx}" data-item-code="${frappe.utils.escape_html(item_code)}" data-batch-no="${frappe.utils.escape_html(batch_no)}">
				<td style="text-align:center; padding: 6px 8px; font-size:12px; color:#888;">${row_num}</td>
				<td style="padding: 6px 8px; font-size:13px; font-weight:500;">${frappe.utils.escape_html(item_code)}</td>
				<td style="padding: 6px 8px; font-size:13px;">${frappe.utils.escape_html(item_name)}</td>
				<td style="padding: 6px 8px; font-size:13px; font-family:monospace;">${frappe.utils.escape_html(batch_no)}</td>
				<td style="padding: 6px 8px; font-size:13px; text-align:center;">${qty}</td>
				<td style="padding: 6px 8px; text-align:center;">
					<input
						type="number"
						class="print-qty-input form-control"
						data-idx="${idx}"
						value="${qty}"
						min="0"
						step="1"
						style="width:70px; text-align:center; font-size:13px; padding:3px 5px;"
					/>
				</td>
			</tr>
		`;
	}).join("");

	const missing_batch_note = selected_items.some(i => !i.batch_no)
		? `<div style="background:#fff3cd; border:1px solid #ffc107; border-radius:4px; padding:8px 12px; margin-bottom:10px; font-size:12px; color:#856404;">
				<strong>Note:</strong> Some rows have no Batch No — those rows will be skipped during printing.
			</div>`
		: "";

	return `
		${missing_batch_note}
		<div style="overflow-x:auto;">
			<table id="${table_id}" style="width:100%; border-collapse:collapse; font-family:Arial,sans-serif;">
				<thead>
					<tr style="border-bottom:2px solid #dee2e6; background:#f8f9fa;">
						<th style="padding:8px; font-size:12px; color:#6c757d; text-align:center; width:40px;">#</th>
						<th style="padding:8px; font-size:12px; color:#6c757d; text-align:left;">Item Code</th>
						<th style="padding:8px; font-size:12px; color:#6c757d; text-align:left;">Item Name</th>
						<th style="padding:8px; font-size:12px; color:#6c757d; text-align:left;">Batch No</th>
						<th style="padding:8px; font-size:12px; color:#6c757d; text-align:center;">Receipt Qty</th>
						<th style="padding:8px; font-size:12px; color:#6c757d; text-align:center;">Print Qty</th>
					</tr>
				</thead>
				<tbody style="border-top:1px solid #dee2e6;">
					${rows}
				</tbody>
			</table>
		</div>
		<div style="margin-top:10px; font-size:12px; color:#6c757d;">
			Adjust <strong>Print Qty</strong> per row as needed. Rows with 0 qty will be skipped.
		</div>
	`;
}

function get_pr_print_rows_from_table(table_id, selected_items) {
	const print_rows = [];
	const inputs = document.querySelectorAll(`#${table_id} .print-qty-input`);

	inputs.forEach(input => {
		const idx = parseInt(input.getAttribute("data-idx"), 10);
		const print_qty = Math.max(0, parseInt(input.value, 10) || 0);
		const item = selected_items[idx];
		if (item && item.batch_no && print_qty > 0) {
			print_rows.push({
				item_code: item.item_code,
				batch_no: item.batch_no,
				print_qty: print_qty,
			});
		}
	});

	return print_rows;
}

function execute_pr_label_print(frm, print_rows, cost_center) {
	let branch_display = cost_center;

	const resolve_branch = new Promise((resolve) => {
		if (!cost_center) {
			resolve(branch_display);
			return;
		}
		frappe.call({
			method: "frappe.client.get",
			args: { doctype: "Cost Center", name: cost_center },
			async: false,
			callback(cc_response) {
				if (cc_response.message) {
					branch_display = cc_response.message.custom_cr_name || cost_center;
				}
				resolve(branch_display);
			},
		});
	});

	resolve_branch.then((branch) => {
		const unique_batches = [...new Set(print_rows.map(r => r.batch_no))];
		const batch_data_map = {};
		let completed = 0;
		const total = unique_batches.length;

		if (total === 0) {
			frappe.msgprint(__("No batches to print."));
			return;
		}

		frappe.show_progress(__("Loading label data..."), 0, total, __("Please wait..."));

		unique_batches.forEach(batch_name => {
			frappe.call({
				method: "beveren_health.beveren_health.utils.label_printing.get_label_data_for_batch",
				args: { batch_name: batch_name },
				callback(r) {
					completed++;
					frappe.show_progress(__("Loading label data..."), completed, total, __("Please wait..."));

					if (r.message) {
						batch_data_map[batch_name] = r.message;
					}

					if (completed === total) {
						frappe.hide_progress();
						render_pr_labels(print_rows, batch_data_map, branch);
					}
				},
				error() {
					completed++;
					frappe.show_progress(__("Loading label data..."), completed, total, __("Please wait..."));
					if (completed === total) {
						frappe.hide_progress();
						render_pr_labels(print_rows, batch_data_map, branch);
					}
				},
			});
		});
	});
}

function render_pr_labels(print_rows, batch_data_map, branch_display) {
	const labels_html = [];
	const skipped = [];

	print_rows.forEach(row => {
		const data = batch_data_map[row.batch_no];
		if (!data) {
			skipped.push(row.batch_no + " (no label data)");
			return;
		}
		if (!data.barcode_image) {
			skipped.push(row.batch_no + " (no barcode image)");
			return;
		}
		for (let i = 0; i < row.print_qty; i++) {
			labels_html.push(
				'<div class="label-page">' +
				build_pr_label_html(data, branch_display) +
				"</div>"
			);
		}
	});

	if (labels_html.length === 0) {
		frappe.msgprint(
			__("No printable labels found. Ensure barcodes are set for the selected batches.") +
			(skipped.length ? "<br><br>Skipped: " + skipped.join(", ") : "")
		);
		return;
	}

	if (skipped.length) {
		frappe.show_alert({
			message: __("Skipped {0} batch(es) with missing data: {1}", [skipped.length, skipped.join(", ")]),
			indicator: "orange",
		});
	}

	const w = window.open("", "_blank");
	w.document.write(
		"<html><head><style>" + PR_LABEL_CSS + "</style></head><body>" +
		labels_html.join("") +
		'<script>window.onload=function(){window.print();window.onafterprint=function(){window.close();};};<\/script></body></html>'
	);
	w.document.close();
}