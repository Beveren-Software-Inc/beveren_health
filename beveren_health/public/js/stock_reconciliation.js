frappe.ui.form.on("Stock Reconciliation", {
	setup(frm) {
		// Keep Stock Scanner submitted when this reconciliation is cancelled.
		frm.ignore_doctypes_on_cancel_all = frm.ignore_doctypes_on_cancel_all || [];
		if (!frm.ignore_doctypes_on_cancel_all.includes("Serial and Batch Bundle")) {
			frm.ignore_doctypes_on_cancel_all.push("Serial and Batch Bundle");
		}
		if (!frm.ignore_doctypes_on_cancel_all.includes("Stock Scanner")) {
			frm.ignore_doctypes_on_cancel_all.push("Stock Scanner");
		}
	},

	onload: function (frm) {
		frm.current_focused_row = null;

		setTimeout(function () {
			setup_row_click_tracking(frm);
		}, 500);

		// Inject highlight CSS once
		if (!document.getElementById("sr-scanner-style")) {
			let style = document.createElement("style");
			style.id = "sr-scanner-style";
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

	refresh: function (frm) {
		setTimeout(function () {
			setup_row_click_tracking(frm);
		}, 300);

		// Also available on a brand new form, so it stays outside the saved-document block.
		toggle_zero_warehouse_button(frm);

		if (!frm.is_new()) {
			frm.add_custom_button(
				__("Batch Label Print"),
				function () {
					show_batch_range_dialog(frm);
				},
				__("Actions")
			);

			if (frm.doc.docstatus === 0) {
				frm.add_custom_button(
					__("Update Reconciliation"),
					function () {
						show_update_reconciliation_dialog(frm);
					},
					__("Actions")
				);
			}

			if (frm.doc.docstatus === 1) {
				frm.add_custom_button(
					__("Dispensing Lots"),
					function () {
						show_dispensing_lots_for_reconciliation(frm);
					},
					__("Actions")
				);

				frm.add_custom_button(
					__("Zero Unreconciled Batches"),
					function () {
						show_unreconciled_batches_dialog(frm);
					},
					__("Actions")
				);

				setup_dispensing_lot_qty_correction_button(frm);
			}
		}
	},

	set_warehouse: function (frm) {
		beveren_health.warehouse_cost_center.set_from_warehouse(frm, frm.doc.set_warehouse, {
			update_items: false,
		});

		// The button only exists once a Default Warehouse is set.
		toggle_zero_warehouse_button(frm);
	},
});

function show_update_reconciliation_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Update Reconciliation"),
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "help",
				options: __(
					"Upload a spreadsheet with <b>item_code</b> and <b>Valuation rate</b> columns. Matching lines on this Stock Reconciliation will get the new valuation rate."
				),
			},
			{
				fieldname: "file",
				fieldtype: "Attach",
				label: __("Valuation Rate Spreadsheet"),
				reqd: 1,
			},
		],
		primary_action_label: __("Update"),
		primary_action(values) {
			frappe.call({
				method: "beveren_health.beveren_health.customize.stock_reconciliation.update_valuation_rates_from_file",
				args: {
					name: frm.doc.name,
					file_url: values.file,
				},
				freeze: true,
				freeze_message: __("Updating valuation rates..."),
				callback(r) {
					const result = r.message || {};
					frappe.msgprint({
						title: __("Update Reconciliation"),
						indicator: result.updated_count ? "green" : "orange",
						message: result.message || __("Done."),
					});
					dialog.hide();
					frm.reload_doc();
				},
			});
		},
	});
	dialog.show();
}

function setup_row_click_tracking(frm) {
	if (!frm.fields_dict["items"] || !frm.fields_dict["items"].grid) return;
	let wrapper = frm.fields_dict["items"].grid.wrapper;
	if (!wrapper) return;
	wrapper.off("click.sr_scanner", ".grid-row");
	wrapper.on("click.sr_scanner", ".grid-row", function () {
		let idx = $(this).attr("data-idx");
		if (idx) {
			frm.current_focused_row = parseInt(idx) - 1;
		}
	});
}

/** Fetch system stock for a row without overwriting scanned qty. */
function sr_fetch_current_stock(frm, cdt, cdn, callback) {
	const row = locals[cdt][cdn];
	if (!row.item_code || !row.warehouse) {
		callback && callback();
		return;
	}

	frappe.call({
		method: "erpnext.stock.doctype.stock_reconciliation.stock_reconciliation.get_stock_balance_for",
		args: {
			item_code: row.item_code,
			warehouse: row.warehouse,
			posting_date: frm.doc.posting_date,
			posting_time: frm.doc.posting_time,
			batch_no: row.batch_no,
			row: row,
			company: frm.doc.company,
		},
		callback: function (r) {
			if (r.message) {
				const rate = flt(r.message.rate);
				const current_qty = flt(r.message.qty);
				frappe.model.set_value(
					cdt,
					cdn,
					{
						valuation_rate: rate,
						current_qty: current_qty,
						current_valuation_rate: rate,
						current_amount: rate * current_qty,
					},
					() => {
						callback && callback();
					}
				);
			} else {
				callback && callback();
			}
		},
	});
}

/** After scan: load system stock into current_* fields, then qty/difference from lots. */
function sr_finalize_row(frm, cdt, cdn, callback) {
	frappe.after_ajax(() => {
		sr_fetch_current_stock(frm, cdt, cdn, () => {
			beveren_health.dispensing_lot_scan.sync_qty_from_lots(frm, cdt, cdn, callback);
		});
	});
}

/** ERPNext clears batch_no when item/warehouse changes unless scan_mode is on. */
function sr_prepare_for_scan(frm) {
	frm.doc.scan_mode = 1;
}

function sr_ensure_scan_mode(frm, callback) {
	sr_prepare_for_scan(frm);
	if (frm.is_dirty()) {
		frm.set_value("scan_mode", 1, () => callback());
		return;
	}
	callback();
}

/** Apply scan fields in PR order (item → batch → lot) so ERPNext handlers do not wipe batch. */
function sr_apply_scan_fields(frm, cdt, cdn, result, warehouse, callback) {
	sr_prepare_for_scan(frm);

	const apply_metadata = () => {
		const meta = {};
		if (result.expiry_date) {
			meta.custom_expiry_date = result.expiry_date;
		}
		if (result.gtin) {
			meta.custom_gstin = result.gtin;
		}
		if (result.mfg_date) {
			meta.custom_manufacturing_date = result.mfg_date;
		}

		if (Object.keys(meta).length) {
			frappe.model.set_value(cdt, cdn, meta, callback);
		} else {
			callback && callback();
		}
	};

	frappe.model.set_value(cdt, cdn, "item_code", result.item_code, () => {
		const base = {
			item_name: result.item_name,
			use_serial_batch_fields: 1,
			warehouse: warehouse,
			allow_zero_valuation_rate: 1,
		};
		if (result.uom) {
			base.stock_uom = result.uom;
		}

		frappe.model.set_value(cdt, cdn, base, () => {
			frappe.model.set_value(cdt, cdn, "batch_no", result.batch_no, () => {
				const row = locals[cdt][cdn];
				if (result.batch_no && !row.batch_no) {
					frappe.msgprint({
						title: __("Batch Not Set"),
						indicator: "orange",
						message: __(
							"Batch {0} could not be linked on the row. It may need to be created first.",
							[result.batch_no]
						),
					});
				}

				if (result.serial_no) {
					frappe.model.set_value(
						cdt,
						cdn,
						"custom_dispensing_lot",
						result.serial_no,
						apply_metadata
					);
				} else {
					frappe.model.set_value(cdt, cdn, "qty", 1, apply_metadata);
				}
			});
		});
	});
}

// ─── Scanner field handler (same flow as Purchase Receipt custom_scanner) ─────

frappe.ui.form.on("Stock Reconciliation Item", {
	warehouse: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		// SR cost center is header-only; set from row warehouse when default is blank
		if (!frm.doc.set_warehouse && row.warehouse) {
			beveren_health.warehouse_cost_center.set_from_warehouse(frm, row.warehouse, {
				update_items: false,
			});
		}
	},

	custom_scanner: function (frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		let barcode = row.custom_scanner;

		if (!barcode) return;

		let warehouse = frm.doc.set_warehouse;
		if (!warehouse) {
			frappe.msgprint(__("Please set a Warehouse on the form before scanning."));
			frappe.model.set_value(cdt, cdn, "custom_scanner", "");
			return;
		}

		let current_row_idx = frm.doc.items.findIndex((r) => r.name === cdn);
		frappe.model.set_value(cdt, cdn, "custom_scanner", "");

		const start_scan = () => {
			sr_ensure_scan_mode(frm, () => {
				if (frm.is_new()) {
					frm.save_or_update({
						callback: function () {
							sr_prepare_for_scan(frm);
							process_scan(
								frm,
								cdt,
								cdn,
								locals[cdt][cdn],
								barcode,
								current_row_idx,
								warehouse
							);
						},
						error: function () {
							frappe.msgprint({
								title: __("Save Error"),
								indicator: "red",
								message: __(
									"Failed to save document. Please save manually and try again."
								),
							});
						},
					});
					return;
				}
				process_scan(frm, cdt, cdn, locals[cdt][cdn], barcode, current_row_idx, warehouse);
			});
		};

		start_scan();
	},
});

function process_scan(frm, cdt, cdn, row, barcode, current_row_idx, warehouse) {
	frappe.call({
		method: "beveren_health.beveren_health.customize.scanner.process_batch_scan",
		args: {
			barcode_data: barcode,
			document_name: frm.doc.name,
			doctype: "Stock Reconciliation",
			current_item_code: row.item_code,
			current_batch_no: row.batch_no || "",
			warehouse: warehouse,
			current_row_name: row.name,
		},
		callback: function (r) {
			if (!r.message || !r.message.success) {
				frappe.msgprint({
					title: __("Scan Error"),
					indicator: "red",
					message: (r.message && r.message.message) || "Failed to process barcode",
				});
				return;
			}

			let result = r.message;
			let final_cdt = cdt;
			let final_cdn = cdn;
			const finish_scan = () => {
				if (result.server_persisted) {
					beveren_health.auto_save_scan.after_successful_scan(
						frm,
						result,
						refocus_scanner_field
					);
					return;
				}
				sr_finalize_row(frm, final_cdt, final_cdn, () => {
					save_and_refocus_scanner(frm, result);
				});
			};

			switch (result.action) {
				case "assign_to_current":
					handle_assign_to_current(
						frm,
						cdt,
						cdn,
						result,
						current_row_idx,
						warehouse,
						finish_scan
					);
					break;
				case "append_serial":
					handle_append_serial(frm, cdt, cdn, result, current_row_idx, finish_scan);
					break;
				case "create_new_row": {
					if (result.server_persisted) {
						handle_create_new_row(frm, result, warehouse, null);
					} else {
						let new_row = handle_create_new_row(frm, result, warehouse, finish_scan);
						final_cdt = new_row.doctype;
						final_cdn = new_row.name;
					}
					break;
				}
				case "move_to_existing": {
					let target = handle_move_to_existing(frm, result, finish_scan);
					if (target) {
						final_cdt = target.cdt;
						final_cdn = target.cdn;
					}
					break;
				}
				default:
					finish_scan();
			}
		},
		error: function (err) {
			console.error("Scan error:", err);
			frappe.msgprint(__("Error processing scan. Check server logs."));
		},
	});
}

// ─── Save and refocus function ───────────────────────────────────────────────

function save_and_refocus_scanner(frm, result) {
	beveren_health.auto_save_scan.save_and_refocus(frm, result, refocus_scanner_field);
}

function refocus_scanner_field(frm, result) {
	let target_row_idx = null;
	let target_row_name = null;

	if (result.action === "create_new_row") {
		// For new row, focus on the newly created row
		let target_row = frm.doc.items.find((r) => r.batch_no === result.batch_no);
		if (target_row) {
			target_row_idx = frm.doc.items.findIndex((r) => r.name === target_row.name);
			target_row_name = target_row.name;
		}
	} else if (result.action === "move_to_existing") {
		// For move to existing, focus on the existing row
		target_row_idx = result.existing_row_index;
		if (target_row_idx !== undefined && frm.doc.items[target_row_idx]) {
			target_row_name = frm.doc.items[target_row_idx].name;
		}
	} else {
		// For assign_to_current and append_serial, focus on the current row
		if (result.row_name) {
			target_row_name = result.row_name;
			target_row_idx = frm.doc.items.findIndex((r) => r.name === result.row_name);
		}
	}

	// If we couldn't determine by row_name, try to find by batch_no
	if (!target_row_name && result.batch_no) {
		let target_row = frm.doc.items.find((r) => r.batch_no === result.batch_no);
		if (target_row) {
			target_row_name = target_row.name;
			target_row_idx = frm.doc.items.findIndex((r) => r.name === target_row.name);
		}
	}

	// If we still don't have a target, use the current focused row
	if (
		!target_row_name &&
		frm.current_focused_row !== null &&
		frm.doc.items[frm.current_focused_row]
	) {
		target_row_name = frm.doc.items[frm.current_focused_row].name;
		target_row_idx = frm.current_focused_row;
	}

	// Focus on the scanner field of the target row
	if (target_row_name) {
		setTimeout(function () {
			let grid = frm.fields_dict["items"].grid;
			if (grid && grid.grid_rows_by_docname) {
				let grid_row = grid.grid_rows_by_docname[target_row_name];
				if (grid_row && grid_row.columns) {
					let scanner_field = grid_row.columns.find(
						(col) => col.fieldname === "custom_scanner"
					);
					if (scanner_field && scanner_field.$input) {
						scanner_field.$input.focus();
						if (target_row_idx !== null) {
							highlight_row(frm, target_row_idx);
							scroll_to_row(frm, target_row_idx);
						}
					} else {
						let $row = grid_row.$row;
						if ($row) {
							$row.find("input:first").focus();
						}
					}
				}
			}
		}, 100);
	}
}

// ─── Case 1 (mirrors Purchase Receipt + SR warehouse / scan_mode fields) ───

function handle_assign_to_current(frm, cdt, cdn, result, row_idx, warehouse, on_complete) {
	if (result.server_persisted) {
		beveren_health.auto_save_scan.patch_row(cdt, cdn, {
			item_code: result.item_code,
			item_name: result.item_name,
			use_serial_batch_fields: 1,
			allow_zero_valuation_rate: 1,
			batch_no: result.batch_no,
			warehouse: warehouse,
			qty: result.qty || 1,
			valuation_rate: result.valuation_rate || result.rate || 0,
			amount: result.amount || 0,
			custom_dispensing_lot: result.serial_no || "",
			custom_expiry_date: result.expiry_date || "",
			custom_manufacturing_date: result.mfg_date || "",
			custom_gstin: result.gtin || "",
		});
		frm.refresh_field("items");
		frm.current_focused_row = row_idx;
		highlight_row(frm, row_idx);
		scroll_to_row(frm, row_idx);
		frappe.show_alert({
			message: `✓ ${result.item_name} | Batch: ${result.batch_no} | SN: ${
				result.serial_no || "N/A"
			}`,
			indicator: "green",
		});
		on_complete && on_complete();
		return;
	}

	sr_apply_scan_fields(frm, cdt, cdn, result, warehouse, () => {
		frm.refresh_field("items");
		frm.current_focused_row = row_idx;
		highlight_row(frm, row_idx);
		scroll_to_row(frm, row_idx);

		frappe.show_alert({
			message: `✓ ${result.item_name} | Batch: ${result.batch_no} | SN: ${
				result.serial_no || "N/A"
			}`,
			indicator: "green",
		});

		on_complete && on_complete();
	});
}

// ─── Case 2 (mirrors Purchase Receipt) ───────────────────────────────────────

function handle_append_serial(frm, cdt, cdn, result, row_idx, on_complete) {
	if (result.server_persisted) {
		beveren_health.auto_save_scan.patch_row(cdt, cdn, {
			qty: result.new_qty,
			amount: result.new_amount,
			allow_zero_valuation_rate: 1,
			custom_dispensing_lot: result.all_dispensing_lots || result.all_serials || "",
			custom_gstin: result.gtin || locals[cdt][cdn].custom_gstin,
		});
		frm.refresh_field("items");
		frm.current_focused_row = row_idx;
		highlight_row(frm, row_idx);
		scroll_to_row(frm, row_idx);
		frappe.show_alert({
			message: `✓ Serial appended | Batch: ${result.batch_no}`,
			indicator: "green",
		});
		on_complete && on_complete();
		return;
	}

	sr_prepare_for_scan(frm);
	beveren_health.dispensing_lot_scan.set_lots(
		cdt,
		cdn,
		result.all_dispensing_lots || result.all_serials,
		frm,
		() => {
			frappe.model.set_value(cdt, cdn, "allow_zero_valuation_rate", 1, () => {
				if (result.gtin) {
					frappe.model.set_value(cdt, cdn, "custom_gstin", result.gtin, after_ui);
				} else {
					after_ui();
				}
			});
		}
	);

	function after_ui() {
		frm.refresh_field("items");
		frm.current_focused_row = row_idx;
		highlight_row(frm, row_idx);
		scroll_to_row(frm, row_idx);

		frappe.show_alert({
			message: `✓ Serial appended | Batch: ${result.batch_no}`,
			indicator: "green",
		});

		on_complete && on_complete();
	}
}

// ─── Case 3 (mirrors Purchase Receipt + SR warehouse) ──────────────────────

function handle_create_new_row(frm, result, warehouse, on_complete) {
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
		return { doctype: "Stock Reconciliation Item", name: result.row_name || "" };
	}

	sr_prepare_for_scan(frm);

	let new_row = frm.add_child("items", {
		use_serial_batch_fields: 1,
		allow_zero_valuation_rate: 1,
		warehouse: warehouse,
	});

	const cdt = new_row.doctype;
	const cdn = new_row.name;

	sr_apply_scan_fields(frm, cdt, cdn, result, warehouse, () => {
		frappe.model.set_value(
			cdt,
			cdn,
			{
				valuation_rate: result.valuation_rate || result.rate || 0,
				qty: result.qty || 1,
			},
			() => {
				frm.refresh_field("items");

				let new_idx = frm.doc.items.findIndex((r) => r.name === cdn);
				frm.current_focused_row = new_idx;
				highlight_row(frm, new_idx);
				scroll_to_row(frm, new_idx);

				frappe.show_alert({
					message: `✓ New row | Batch: ${result.batch_no} | SN: ${
						result.serial_no || "N/A"
					}`,
					indicator: "orange",
				});

				on_complete && on_complete();
			}
		);
	});

	new_row.doctype = cdt;
	new_row.name = cdn;
	return new_row;
}

// ─── Case 4 (mirrors Purchase Receipt) ───────────────────────────────────────

function handle_move_to_existing(frm, result, on_complete) {
	sr_prepare_for_scan(frm);

	let target_idx = result.existing_row_index;
	let target_row = frm.doc.items[target_idx];

	if (!target_row) {
		on_complete && on_complete();
		return null;
	}

	let cdt = target_row.doctype;
	let cdn = target_row.name;

	const finish = () => {
		frm.refresh_field("items");
		frm.current_focused_row = target_idx;
		highlight_row(frm, target_idx);
		scroll_to_row(frm, target_idx);

		frappe.show_alert({
			message: `↗ Moved to existing batch: ${result.batch_no}`,
			indicator: "blue",
		});

		on_complete && on_complete();
	};

	if (result.server_persisted) {
		beveren_health.auto_save_scan.patch_row(cdt, cdn, {
			qty: result.new_qty != null ? result.new_qty : target_row.qty,
			amount: result.new_amount != null ? result.new_amount : target_row.amount,
			allow_zero_valuation_rate: 1,
			custom_dispensing_lot:
				result.all_dispensing_lots ||
				result.all_serials ||
				target_row.custom_dispensing_lot,
		});
		finish();
		return { cdt: cdt, cdn: cdn };
	}

	if (result.serial_no) {
		let updated_lots = beveren_health.dispensing_lot_scan.append_lot(
			target_row.custom_dispensing_lot,
			result.serial_no
		);
		if (updated_lots !== (target_row.custom_dispensing_lot || "")) {
			beveren_health.dispensing_lot_scan.set_lots(cdt, cdn, updated_lots, frm, () => {
				frappe.model.set_value(cdt, cdn, "allow_zero_valuation_rate", 1, apply_meta);
			});
			return { cdt: cdt, cdn: cdn };
		}
	}

	apply_meta();

	function apply_meta() {
		const meta = {};
		if (result.expiry_date && !target_row.custom_expiry_date) {
			meta.custom_expiry_date = result.expiry_date;
		}
		if (result.gtin) {
			meta.custom_gstin = result.gtin;
		}
		if (result.mfg_date && !target_row.custom_manufacturing_date) {
			meta.custom_manufacturing_date = result.mfg_date;
		}

		if (Object.keys(meta).length) {
			frappe.model.set_value(cdt, cdn, meta, finish);
		} else {
			finish();
		}
	}

	return { cdt: cdt, cdn: cdn };
}

// ─── UI helpers ───────────────────────────────────────────────────────────────

function highlight_row(frm, row_idx) {
	setTimeout(function () {
		if (!frm.fields_dict["items"] || !frm.fields_dict["items"].grid) return;
		let $rows = frm.fields_dict["items"].grid.wrapper.find(".grid-row");
		$rows.removeClass("row-highlight");
		if ($rows[row_idx]) {
			$($rows[row_idx]).addClass("row-highlight");
		}
	}, 150);
}

function scroll_to_row(frm, row_idx) {
	setTimeout(function () {
		if (!frm.fields_dict["items"] || !frm.fields_dict["items"].grid) return;

		let $rows = frm.fields_dict["items"].grid.wrapper.find(".grid-row");

		if ($rows.length > row_idx && $rows[row_idx]) {
			let rowElement = $rows[row_idx];

			if (rowElement && typeof rowElement.scrollIntoView === "function") {
				rowElement.scrollIntoView({ behavior: "smooth", block: "center" });
			} else if (
				rowElement &&
				rowElement[0] &&
				typeof rowElement[0].scrollIntoView === "function"
			) {
				rowElement[0].scrollIntoView({ behavior: "smooth", block: "center" });
			} else if (rowElement && rowElement.length && rowElement[0]) {
				rowElement[0].scrollIntoView({ behavior: "smooth", block: "center" });
			}
		}
	}, 200);
}

// ─── Dispensing lots linked to this reconciliation ─────────────────────────────

function setup_dispensing_lot_qty_correction_button(frm) {
	frappe.call({
		method: "beveren_health.beveren_health.customize.dispensing_lot.preview_dispensing_lot_qty_corrections",
		args: {
			source_doctype: frm.doc.doctype,
			source_document: frm.doc.name,
		},
		callback(r) {
			const fixable = (r.message && r.message.fixable) || [];
			const skipped = (r.message && r.message.skipped) || [];
			if (!fixable.length && !skipped.some((s) => s.expected_qty != null)) {
				return;
			}

			frm.add_custom_button(
				__("Correct Lot Quantities"),
				function () {
					run_dispensing_lot_qty_correction(frm);
				},
				__("Actions")
			);
		},
	});
}

function format_lot_qty_change(lot) {
	const uom = lot.uom ? ` ${lot.uom}` : "";
	return `${flt(lot.current_qty)} → ${flt(lot.expected_qty)}${uom}`;
}

function build_lot_correction_table_rows(lots, include_reason) {
	return lots
		.map((lot) => {
			let row = `<tr>
				<td style="padding:4px 8px;">${frappe.utils.escape_html(lot.serial_no || lot.name || "")}</td>
				<td style="padding:4px 8px;">${frappe.utils.escape_html(lot.item || "")}</td>
				<td style="padding:4px 8px; text-align:right;">${frappe.utils.escape_html(
					format_lot_qty_change(lot)
				)}</td>`;
			if (include_reason) {
				row += `<td style="padding:4px 8px;">${frappe.utils.escape_html(
					lot.reason || ""
				)}</td>`;
			}
			row += "</tr>";
			return row;
		})
		.join("");
}

function build_lot_correction_summary_html(fixable, skipped, unchanged, full_detail) {
	const sections = [];

	if (fixable.length) {
		sections.push(`<p><strong>${__("Will update")}</strong></p>
			<table class="table table-bordered" style="font-size:12px;">
				<thead><tr><th>${__("Serial")}</th><th>${__("Item")}</th><th style="text-align:right;">${__(
			"Qty change"
		)}</th></tr></thead>
				<tbody>${build_lot_correction_table_rows(fixable, false)}</tbody>
			</table>`);
	}

	const skipped_with_qty = skipped.filter((s) => s.expected_qty != null);
	if (skipped_with_qty.length && full_detail) {
		sections.push(`<p style="margin-top:12px;"><strong>${__(
			"Cannot update (already used or not Active)"
		)}</strong></p>
			<table class="table table-bordered" style="font-size:12px;">
				<thead><tr><th>${__("Serial")}</th><th>${__("Item")}</th><th style="text-align:right;">${__(
			"Qty change"
		)}</th><th>${__("Reason")}</th></tr></thead>
				<tbody>${build_lot_correction_table_rows(skipped_with_qty, true)}</tbody>
			</table>`);
	} else if (skipped_with_qty.length) {
		sections.push(
			`<p class="text-muted" style="margin-top:12px;">${__(
				"{0} lot(s) need changes but cannot be updated (already used or not Active). Open Dispensing Lots to review.",
				[skipped_with_qty.length]
			)}</p>`
		);
	}

	if (full_detail && unchanged.length) {
		const mismatched_unchanged = unchanged.filter(
			(lot) => flt(lot.current_qty) !== flt(lot.expected_qty)
		);
		const show_unchanged = mismatched_unchanged.length ? mismatched_unchanged : unchanged;
		sections.push(`<p style="margin-top:12px;"><strong>${__("Already matches expected")} (${
			show_unchanged.length
		})</strong></p>
			<table class="table table-bordered" style="font-size:12px;">
				<thead><tr><th>${__("Serial")}</th><th>${__("Item")}</th><th style="text-align:right;">${__(
			"Qty"
		)}</th></tr></thead>
				<tbody>${show_unchanged
					.map(
						(lot) =>
							`<tr><td>${frappe.utils.escape_html(
								lot.serial_no || lot.name || ""
							)}</td>` +
							`<td>${frappe.utils.escape_html(lot.item || "")}</td>` +
							`<td style="text-align:right;">${flt(
								lot.current_qty
							)} ${frappe.utils.escape_html(lot.uom || "")}</td></tr>`
					)
					.join("")}</tbody>
			</table>`);
	}

	if (!fixable.length && !sections.length) {
		return `<p>${__(
			"All dispensing lot quantities already match this Stock Reconciliation."
		)}</p>`;
	}

	if (fixable.length) {
		sections.push(
			`<p class="text-muted" style="margin-top:8px;">${__(
				"Only unused Active lots are updated."
			)}</p>`
		);
	}

	return sections.join("");
}

function run_dispensing_lot_qty_correction(frm) {
	frappe.call({
		method: "beveren_health.beveren_health.customize.dispensing_lot.preview_dispensing_lot_qty_corrections",
		args: {
			source_doctype: frm.doc.doctype,
			source_document: frm.doc.name,
		},
		callback(r) {
			const fixable = (r.message && r.message.fixable) || [];
			const skipped = (r.message && r.message.skipped) || [];
			const unchanged = (r.message && r.message.unchanged) || [];

			if (!fixable.length) {
				frappe.msgprint({
					title: __("No lots to correct"),
					indicator: "orange",
					message: build_lot_correction_summary_html(fixable, skipped, unchanged, true),
				});
				return;
			}

			frappe.confirm(
				`<p>${__(
					"Update {0} dispensing lot(s) to match quantities on this Stock Reconciliation?",
					[fixable.length]
				)}</p>
				${build_lot_correction_summary_html(fixable, skipped, unchanged, false)}`,
				() => {
					frappe.call({
						method: "beveren_health.beveren_health.customize.dispensing_lot.correct_dispensing_lot_quantities",
						args: {
							source_doctype: frm.doc.doctype,
							source_document: frm.doc.name,
						},
						freeze: true,
						freeze_message: __("Correcting dispensing lot quantities..."),
						callback(res) {
							const corrected = (res.message && res.message.corrected) || [];
							const skipped = (res.message && res.message.skipped) || [];

							if (!corrected.length) {
								frappe.msgprint(__("No dispensing lots were updated."));
								return;
							}

							let message = __("Updated {0} dispensing lot(s).", [corrected.length]);
							if (skipped.length) {
								message +=
									"<br><br>" +
									__("Skipped {0} lot(s) (already used or linked elsewhere).", [
										skipped.length,
									]);
							}

							frappe.msgprint({
								title: __("Correction complete"),
								indicator: "green",
								message: message,
							});

							frm.refresh();
						},
					});
				}
			);
		},
	});
}

function show_dispensing_lots_for_reconciliation(frm) {
	frappe.call({
		method: "beveren_health.beveren_health.customize.dispensing_lot.get_dispensing_lots_for_stock_document",
		args: {
			source_doctype: frm.doc.doctype,
			source_document: frm.doc.name,
		},
		callback(r) {
			const lots = r.message || [];
			if (!lots.length) {
				frappe.msgprint(
					__("No dispensing lots were created from this Stock Reconciliation.")
				);
				return;
			}

			const rows = lots
				.map((lot) => {
					const qty_label = `${flt(lot.remaining_qty)} / ${flt(lot.initial_qty)} ${
						lot.uom || ""
					}`.trim();
					return `
						<tr>
							<td style="padding:6px 8px;">${frappe.utils.escape_html(lot.item || "")}</td>
							<td style="padding:6px 8px;">${frappe.utils.escape_html(lot.serial_no || lot.name)}</td>
							<td style="padding:6px 8px;">${frappe.utils.escape_html(lot.batch_no || "")}</td>
							<td style="padding:6px 8px; text-align:right;">${frappe.utils.escape_html(qty_label)}</td>
							<td style="padding:6px 8px;">${frappe.utils.escape_html(lot.status || "")}</td>
							<td style="padding:6px 8px; text-align:center;">
								<button type="button" class="btn btn-xs btn-default open-dl-lot" data-lot="${frappe.utils.escape_html(
									lot.name
								)}">
									${__("Open")}
								</button>
							</td>
						</tr>
					`;
				})
				.join("");

			const d = new frappe.ui.Dialog({
				title: __("Dispensing Lots"),
				size: "large",
				fields: [
					{
						fieldtype: "HTML",
						options: `
							<p class="text-muted">${__(
								"Lots created when this document was submitted. Open a lot to amend quantities if needed."
							)}</p>
							<div style="overflow-x:auto;">
								<table class="table table-bordered" style="margin:0; font-size:12px;">
									<thead>
										<tr>
											<th>${__("Item")}</th>
											<th>${__("Serial")}</th>
											<th>${__("Batch")}</th>
											<th style="text-align:right;">${__("Remaining / Initial")}</th>
											<th>${__("Status")}</th>
											<th style="text-align:center;">${__("Action")}</th>
										</tr>
									</thead>
									<tbody>${rows}</tbody>
								</table>
							</div>
						`,
					},
				],
			});

			d.show();

			d.$wrapper.on("click", ".open-dl-lot", function () {
				const lot_name = $(this).attr("data-lot");
				if (lot_name) {
					frappe.set_route("Form", "Dispensing Lot", lot_name);
				}
			});
		},
	});
}

// ─── Zero un-reconciled batches ────────────────────────────────────────────────

function show_unreconciled_batches_dialog(frm) {
	frappe.call({
		method: "beveren_health.beveren_health.customize.stock_reconciliation.get_unreconciled_batches",
		args: { name: frm.doc.name },
		freeze: true,
		freeze_message: __("Checking batch balances..."),
		callback(r) {
			const data = r.message || {};
			const lines = data.lines || [];

			if (!data.total_lines) {
				frappe.msgprint({
					title: __("Nothing to zero"),
					indicator: "green",
					message: __(
						"Every batch still holding stock in this document's warehouses is already on this Stock Reconciliation."
					),
				});
				return;
			}

			const dialog = new frappe.ui.Dialog({
				title: __("Zero Unreconciled Batches"),
				size: "extra-large",
				fields: [
					{
						fieldtype: "HTML",
						fieldname: "summary",
						options: build_unreconciled_summary_html(data),
					},
					{
						fieldtype: "Date",
						fieldname: "posting_date",
						label: __("Posting Date"),
						default: frappe.datetime.get_today(),
						reqd: 1,
					},
					{
						fieldtype: "HTML",
						fieldname: "lines",
						options: build_unreconciled_lines_html(data),
					},
				],
				primary_action_label: __("Create Draft Reconciliation"),
				primary_action(values) {
					dialog.hide();
					frappe.call({
						method: "beveren_health.beveren_health.customize.stock_reconciliation.create_unreconciled_batch_reconciliation",
						args: {
							name: frm.doc.name,
							posting_date: values.posting_date,
						},
						freeze: true,
						freeze_message: __("Creating Stock Reconciliation..."),
						callback(res) {
							if (!res.message) return;
							frappe.show_alert({
								message: __("Draft {0} created", [res.message]),
								indicator: "green",
							});
							frappe.set_route("Form", "Stock Reconciliation", res.message);
						},
					});
				},
			});

			dialog.show();
		},
	});
}

// `format_currency` is a window global provided by the desk bundle (number_format.js),
// not `frappe.utils.format_currency`. Guard it so a missing/renamed global degrades to a
// plain number instead of throwing and leaving the dialog unrendered.
function format_unreconciled_value(value, currency) {
	const amount = flt(value, 2);
	if (currency && typeof format_currency === "function") {
		return format_currency(amount, currency);
	}
	return amount;
}

function build_unreconciled_summary_html(data) {
	const warnings = [];
	if (data.warning_lines) {
		warnings.push(
			__(
				"{0} line(s) have no unused dispensing lot for their batch. Add a lot to those lines before submitting, otherwise submit will be blocked.",
				[data.warning_lines]
			)
		);
	}

	return `
		<p>${__(
			"These batch/warehouse combinations are not on this Stock Reconciliation. A draft Stock Reconciliation will be created with one zero-quantity line per combination."
		)}</p>
		<p>${__(
			"Submitting that draft counts those batches down to zero and sets their dispensing lots to Inactive; cancelling it puts the lots back in stock."
		)}</p>
		${build_batch_summary_table_html(data)}
		${build_batch_summary_warning_html(warnings)}
	`;
}

function build_batch_summary_table_html(data) {
	const rows = [
		`<tr><td>${__(
			"Warehouse(s)"
		)}</td><td style="text-align:right;"><b>${frappe.utils.escape_html(
			(data.warehouses || []).join(", ")
		)}</b></td></tr>`,
		`<tr><td>${__("Lines to zero")}</td><td style="text-align:right;"><b>${
			data.total_lines
		}</b></td></tr>`,
		`<tr><td>${__("Total quantity on hand")}</td><td style="text-align:right;"><b>${flt(
			data.total_qty
		)}</b></td></tr>`,
		`<tr><td>${__(
			"Value to write off"
		)}</td><td style="text-align:right;"><b>${format_unreconciled_value(
			data.total_value,
			data.currency
		)}</b></td></tr>`,
	];

	if (data.lot_lines) {
		rows.push(
			`<tr><td>${__("Lines with dispensing lots")}</td><td style="text-align:right;"><b>${
				data.lot_lines
			}</b> ${__("({0} lot(s) will be set to Inactive)", [data.lot_count])}</td></tr>`
		);
	}

	return `
		<table class="table table-bordered" style="font-size:12px; margin-bottom:8px;">
			<tbody>${rows.join("")}</tbody>
		</table>
	`;
}

function build_batch_summary_warning_html(messages) {
	return messages
		.filter(Boolean)
		.map((message) => `<p class="text-danger" style="margin:8px 0 0;">${message}</p>`)
		.join("");
}

function build_unreconciled_lines_html(data) {
	const lines = data.lines || [];
	const rows = lines
		.map((line) => {
			const item = line.item_name
				? `${frappe.utils.escape_html(
						line.item_name
				  )}<br><span class="text-muted">${frappe.utils.escape_html(
						line.item_code
				  )}</span>`
				: frappe.utils.escape_html(line.item_code);

			const lot_cell = line.needs_dispensing_lot
				? line.lot_count
					? `${line.lot_count}`
					: `<span class="text-danger">${__("None found")}</span>`
				: `<span class="text-muted">—</span>`;

			return `
				<tr>
					<td style="padding:4px 8px;">${frappe.utils.escape_html(line.warehouse || "")}</td>
					<td style="padding:4px 8px;">${item}</td>
					<td style="padding:4px 8px;">${frappe.utils.escape_html(line.batch_no || "")}</td>
					<td style="padding:4px 8px; text-align:right;">${flt(line.qty)}</td>
					<td style="padding:4px 8px; text-align:right;">${flt(line.valuation_rate)}</td>
					<td style="padding:4px 8px; text-align:right;">${format_unreconciled_value(
						line.value,
						data.currency
					)}</td>
					<td style="padding:4px 8px; text-align:right;">${lot_cell}</td>
				</tr>
			`;
		})
		.join("");

	const footer = data.truncated
		? `<p class="text-muted" style="margin-top:8px;">${__(
				"Showing the first {0} of {1} line(s).",
				[lines.length, data.total_lines]
		  )}</p>`
		: "";

	return `
		<div style="overflow-x:auto; max-height:300px; overflow-y:auto;">
			<table class="table table-bordered" style="margin:0; font-size:12px;">
				<thead>
					<tr>
						<th>${__("Warehouse")}</th>
						<th>${__("Item")}</th>
						<th>${__("Batch")}</th>
						<th style="text-align:right;">${__("Qty on hand")}</th>
						<th style="text-align:right;">${__("Valuation Rate")}</th>
						<th style="text-align:right;">${__("Value")}</th>
						<th style="text-align:right;">${__("Lots")}</th>
					</tr>
				</thead>
				<tbody>${rows}</tbody>
			</table>
		</div>
		${footer}
	`;
}

// ─── Zero every batch of the chosen warehouse ───────────────────────────────────
//
// On a draft reconciliation the Default Warehouse picks the location; this button fills
// the form with one line per batch holding stock in it — quantity 0, the valuation rate
// the ledger holds and the dispensing lots of the batch — so a whole warehouse can be
// written off and submitted without scanning. The button writes nothing: the lines land
// in the grid for review, and submitting the reconciliation counts the batches down to
// zero and sets their dispensing lots to Inactive (cancelling puts them back in stock).

const ZERO_WAREHOUSE_REPLACE = "Replace existing lines";
const ZERO_WAREHOUSE_APPEND = "Add to existing lines";
const ZERO_WAREHOUSE_LARGE_LINE_LIMIT = 2000;

function zero_warehouse_button_label() {
	return __("Zero Batch from Chosen Warehouse");
}

function toggle_zero_warehouse_button(frm) {
	const group = __("Actions");
	frm.remove_custom_button(zero_warehouse_button_label(), group);

	if (frm.doc.docstatus === 0 && frm.doc.set_warehouse) {
		frm.add_custom_button(
			zero_warehouse_button_label(),
			function () {
				show_zero_warehouse_dialog(frm);
			},
			group
		);
	}
}

function show_zero_warehouse_dialog(frm) {
	if (!frm.doc.set_warehouse) {
		frappe.msgprint(__("Set the Default Warehouse on this Stock Reconciliation first."));
		return;
	}

	frappe.call({
		method: "beveren_health.beveren_health.customize.stock_reconciliation.get_warehouse_zeroing_lines",
		args: {
			warehouse: frm.doc.set_warehouse,
			company: frm.doc.company,
			purpose: frm.doc.purpose,
		},
		freeze: true,
		freeze_message: __("Reading batch balances of {0}...", [frm.doc.set_warehouse]),
		callback(r) {
			const data = r.message || {};

			if (!data.total_lines) {
				frappe.msgprint({
					title: __("Nothing to zero"),
					indicator: "green",
					message: __(
						"No batch holds stock in {0}. Every batch there is already counted to zero.",
						[frappe.utils.escape_html(data.warehouse || frm.doc.set_warehouse)]
					),
				});
				return;
			}

			const existing = (frm.doc.items || []).length;
			const fields = [
				{
					fieldtype: "HTML",
					fieldname: "summary",
					options: build_zero_warehouse_summary_html(data, existing),
				},
			];

			if (existing) {
				fields.push({
					fieldtype: "Select",
					fieldname: "mode",
					label: __("Existing lines"),
					options: [__(ZERO_WAREHOUSE_REPLACE), __(ZERO_WAREHOUSE_APPEND)],
					default: __(ZERO_WAREHOUSE_REPLACE),
					reqd: 1,
				});
			}

			fields.push({
				fieldtype: "HTML",
				fieldname: "lines",
				options: build_unreconciled_lines_html(data),
			});

			const dialog = new frappe.ui.Dialog({
				title: __("Zero Batch from Chosen Warehouse"),
				size: "extra-large",
				fields: fields,
				primary_action_label: __("Fill the lines"),
				primary_action(values) {
					dialog.hide();
					apply_zero_warehouse_lines(frm, data, values);
				},
			});

			dialog.show();
		},
	});
}

function apply_zero_warehouse_lines(frm, data, values) {
	const replacing = (values && values.mode) !== __(ZERO_WAREHOUSE_APPEND);
	const grid_rows = data.grid_rows || [];
	const has_lot_field = frappe.meta.has_field(
		"Stock Reconciliation Item",
		"custom_dispensing_lot"
	);

	const existing_keys = new Set();
	if (!replacing) {
		(frm.doc.items || []).forEach((row) => {
			existing_keys.add(zero_warehouse_line_key(row));
		});
	} else {
		frm.clear_table("items");
	}

	let added = 0;
	let skipped = 0;

	grid_rows.forEach((row) => {
		if (existing_keys.has(zero_warehouse_line_key(row))) {
			skipped += 1;
			return;
		}

		const line = Object.assign({}, row);
		if (!has_lot_field) {
			delete line.custom_dispensing_lot;
		}

		frm.add_child("items", line);
		added += 1;
	});

	const defaults = data.defaults || {};
	if (defaults.expense_account && !frm.doc.expense_account) {
		frm.set_value("expense_account", defaults.expense_account);
	}
	if (defaults.cost_center && !frm.doc.cost_center) {
		frm.set_value("cost_center", defaults.cost_center);
	}
	if (!frm.doc.posting_date) {
		frm.set_value("posting_date", frappe.datetime.get_today());
	}
	if (!frm.doc.posting_time) {
		frm.set_value("posting_time", frappe.datetime.now_time());
	}

	frm.refresh_field("items");
	frm.dirty();

	frappe.show_alert({
		message: skipped
			? __("{0} line(s) added, {1} line(s) were already on the form.", [added, skipped])
			: __("{0} zero-quantity line(s) added. Review them and submit when ready.", [added]),
		indicator: "green",
	});
}

function zero_warehouse_line_key(row) {
	return [row.item_code || "", row.batch_no || "", row.warehouse || ""].join("::");
}

function build_zero_warehouse_summary_html(data, existing_lines) {
	const warnings = [];

	if (existing_lines) {
		warnings.push(
			__(
				"This form already has {0} line(s). Replacing them keeps only the batch lines below.",
				[existing_lines]
			)
		);
	}
	if (data.warning_lines) {
		warnings.push(
			__(
				"{0} line(s) have no unused dispensing lot for their batch. Add a lot to those lines before submitting, otherwise submit will be blocked.",
				[data.warning_lines]
			)
		);
	}
	if (data.defaults && data.defaults.perpetual_inventory && !data.defaults.expense_account) {
		warnings.push(
			__(
				"No Difference Account could be resolved for this company. Set a Stock Adjustment Account on the Company before submitting."
			)
		);
	}
	if (data.total_lines > ZERO_WAREHOUSE_LARGE_LINE_LIMIT) {
		warnings.push(
			__("This warehouse is large: {0} lines will be added and the form may become slow.", [
				data.total_lines,
			])
		);
	}

	return `
		<p>${__(
			"Every batch holding stock in {0} is added to this reconciliation with quantity <b>0</b>, so submitting it counts the whole warehouse down to zero.",
			[frappe.utils.escape_html(data.warehouse || "")]
		)}</p>
		<p>${__(
			"The valuation rate comes from the ledger and the Current Qty column shows what is being written off. Nothing is saved by this button — review the lines and submit when ready. Submitting sets the dispensing lots of those batches to Inactive; cancelling puts them back in stock."
		)}</p>
		${build_batch_summary_table_html(data)}
		${build_batch_summary_warning_html(warnings)}
	`;
}

// Batch printing
const RECON_LABEL_CSS = `
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

function build_recon_label_html(data, branch_display) {
	const item_code = data.item_code || "N/A";
	const item_name_line_val = data.item_name_line || "N/A";
	const standard_selling_price =
		data.standard_selling_price != null ? data.standard_selling_price : "N/A";
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

function show_batch_range_dialog(frm) {
	// Determine max possible row count
	const items = frm.doc.items || [];
	const max_rows = items.length;

	if (max_rows === 0) {
		frappe.msgprint(__("No items found in this Stock Reconciliation."));
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
			// {
			// 	fieldtype: "Section Break",
			// 	label: __("Branch (Cost Center)"),
			// },
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
			show_label_table_dialog(frm, selected_items, values.cost_center || "");
		},
	});

	d.show();
}

function show_label_table_dialog(frm, selected_items, cost_center) {
	// Build table HTML for the dialog
	const table_id = "recon_label_table_" + frappe.utils.get_random(5);

	const fields = [
		{
			fieldname: "label_table_html",
			fieldtype: "HTML",
			label: "",
			options: build_label_table_html(selected_items, table_id),
		},
	];

	const d2 = new frappe.ui.Dialog({
		title: __("Review & Print Labels"),
		fields: fields,
		size: "extra-large",
		primary_action_label: __("Print All"),
		primary_action() {
			// Collect print quantities from inputs
			const print_rows = get_print_rows_from_table(table_id, selected_items);
			if (!print_rows.length) {
				frappe.msgprint(__("No items to print."));
				return;
			}
			d2.hide();
			execute_label_print(frm, print_rows, cost_center);
		},
	});

	d2.show();
	// Style the dialog body for better table display
	$(d2.wrapper).find(".modal-dialog").css("max-width", "900px");
}

function build_label_table_html(selected_items, table_id) {
	const rows = selected_items
		.map((item, idx) => {
			const row_num = idx + 1;
			const item_code = item.item_code || "";
			const item_name = item.item_name || "";
			const batch_no = item.batch_no || "";
			const qty = flt(item.qty, 0) || 0;

			return `
			<tr data-idx="${idx}" data-item-code="${frappe.utils.escape_html(
				item_code
			)}" data-batch-no="${frappe.utils.escape_html(batch_no)}">
				<td style="text-align:center; padding: 6px 8px; font-size:12px; color:#888;">${row_num}</td>
				<td style="padding: 6px 8px; font-size:13px; font-weight:500;">${frappe.utils.escape_html(
					item_code
				)}</td>
				<td style="padding: 6px 8px; font-size:13px;">${frappe.utils.escape_html(item_name)}</td>
				<td style="padding: 6px 8px; font-size:13px; font-family:monospace;">${frappe.utils.escape_html(
					batch_no
				)}</td>
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
		})
		.join("");

	const missing_batch_note = selected_items.some((i) => !i.batch_no)
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
						<th style="padding:8px; font-size:12px; color:#6c757d; text-align:center;">Recon Qty</th>
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

function get_print_rows_from_table(table_id, selected_items) {
	const print_rows = [];
	const inputs = document.querySelectorAll(`#${table_id} .print-qty-input`);

	inputs.forEach((input) => {
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

function execute_label_print(frm, print_rows, cost_center) {
	// Resolve branch display name, then fetch label data for each batch
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
		// Fetch label data for all unique batches in parallel
		const unique_batches = [...new Set(print_rows.map((r) => r.batch_no))];
		const batch_data_map = {};
		let completed = 0;
		const total = unique_batches.length;

		if (total === 0) {
			frappe.msgprint(__("No batches to print."));
			return;
		}

		frappe.show_progress(__("Loading label data..."), 0, total, __("Please wait..."));

		unique_batches.forEach((batch_name) => {
			frappe.call({
				method: "beveren_health.beveren_health.utils.label_printing.get_label_data_for_batch",
				args: { batch_name: batch_name },
				callback(r) {
					completed++;
					frappe.show_progress(
						__("Loading label data..."),
						completed,
						total,
						__("Please wait...")
					);

					if (r.message) {
						batch_data_map[batch_name] = r.message;
					}

					if (completed === total) {
						frappe.hide_progress();
						render_labels(print_rows, batch_data_map, branch);
					}
				},
				error() {
					completed++;
					frappe.show_progress(
						__("Loading label data..."),
						completed,
						total,
						__("Please wait...")
					);
					if (completed === total) {
						frappe.hide_progress();
						render_labels(print_rows, batch_data_map, branch);
					}
				},
			});
		});
	});
}

function render_labels(print_rows, batch_data_map, branch_display) {
	const labels_html = [];
	const skipped = [];

	print_rows.forEach((row) => {
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
					build_recon_label_html(data, branch_display) +
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
			message: __("Skipped {0} batch(es) with missing data: {1}", [
				skipped.length,
				skipped.join(", "),
			]),
			indicator: "orange",
		});
	}

	const w = window.open("", "_blank");
	w.document.write(
		"<html><head><style>" +
			RECON_LABEL_CSS +
			"</style></head><body>" +
			labels_html.join("") +
			"<script>window.onload=function(){window.print();window.onafterprint=function(){window.close();};};</script></body></html>"
	);
	w.document.close();
}
