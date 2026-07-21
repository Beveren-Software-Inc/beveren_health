/* Stock Scanner — row-focused scanning (same flow as Stock Reconciliation). */

const SS_SCANNER_STYLE_ID = "ss-scanner-style";

function ss_set_lots(cdt, cdn, value, frm) {
	frappe.model.set_value(cdt, cdn, "serial_no", value || "", () => {
		ss_sync_qty_from_lots(frm, cdt, cdn);
	});
}

function ss_append_lot(existing, new_serial) {
	if (!new_serial) {
		return existing || "";
	}
	const lots = (existing || "")
		.split(/\n|,/)
		.map((s) => s.trim())
		.filter(Boolean);
	if (!lots.includes(new_serial)) {
		lots.push(new_serial);
	}
	return lots.join("\n");
}

function ss_count_lots(value) {
	if (!value) {
		return 0;
	}
	return value
		.split(/\n|,/)
		.map((s) => s.trim())
		.filter(Boolean).length;
}

function ss_sync_qty_from_lots(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row) {
		return;
	}
	const lot_count = ss_count_lots(row.serial_no);
	const row_qty = flt(row.qty);
	// One partial pack can have fractional qty (e.g. 0.655); only count lots when qty unset or multiple packs.
	const qty = lot_count > 1 ? lot_count : (row_qty > 0 ? row_qty : lot_count || 0);
	const rate = flt(row.valuation_rate);
	frappe.model.set_value(cdt, cdn, "qty", qty);
	frappe.model.set_value(cdt, cdn, "current_qty", qty);
	frappe.model.set_value(cdt, cdn, "amount", qty * rate);
	frappe.model.set_value(cdt, cdn, "current_amount", qty * rate);
	frappe.model.set_value(cdt, cdn, "allow_zero_valuation_rate", 1);
}

/** Apply GTIN / manufacturing / expiry from barcode parse result onto Stock Scanner Item row. */
function ss_apply_scan_metadata(cdt, cdn, result, existing_row, only_if_empty) {
	if (result.gtin && (!only_if_empty || !existing_row?.gtin)) {
		frappe.model.set_value(cdt, cdn, "gtin", result.gtin);
	}
	if (result.expiry_date && (!only_if_empty || !existing_row?.expiry_date)) {
		frappe.model.set_value(cdt, cdn, "expiry_date", result.expiry_date);
	}
	if (result.mfg_date && (!only_if_empty || !existing_row?.manufacturing_date)) {
		frappe.model.set_value(cdt, cdn, "manufacturing_date", result.mfg_date);
	}
}

function ss_inject_highlight_style() {
	if (document.getElementById(SS_SCANNER_STYLE_ID)) {
		return;
	}
	const style = document.createElement("style");
	style.id = SS_SCANNER_STYLE_ID;
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

function ss_setup_row_click_tracking(frm) {
	if (!frm.fields_dict.items || !frm.fields_dict.items.grid) {
		return;
	}
	const wrapper = frm.fields_dict.items.grid.wrapper;
	if (!wrapper) {
		return;
	}
	wrapper.off("click.ss_scanner", ".grid-row");
	wrapper.on("click.ss_scanner", ".grid-row", function () {
		const idx = $(this).attr("data-idx");
		if (idx) {
			frm.current_focused_row = parseInt(idx, 10) - 1;
		}
	});
}

function ss_highlight_row(frm, row_idx) {
	setTimeout(function () {
		if (!frm.fields_dict.items || !frm.fields_dict.items.grid) {
			return;
		}
		const $rows = frm.fields_dict.items.grid.wrapper.find(".grid-row");
		$rows.removeClass("row-highlight");
		if ($rows[row_idx]) {
			$($rows[row_idx]).addClass("row-highlight");
		}
	}, 150);
}

function ss_scroll_to_row(frm, row_idx) {
	setTimeout(function () {
		if (!frm.fields_dict.items || !frm.fields_dict.items.grid) {
			return;
		}
		const $rows = frm.fields_dict.items.grid.wrapper.find(".grid-row");
		if ($rows.length > row_idx && $rows[row_idx]) {
			const el = $rows[row_idx];
			const node = el[0] || el;
			if (node && typeof node.scrollIntoView === "function") {
				node.scrollIntoView({ behavior: "smooth", block: "center" });
			}
		}
	}, 200);
}

function ss_refocus_scanner_field(frm, result) {
	let target_row_name = null;
	let target_row_idx = null;

	if (result.action === "create_new_row") {
		const target_row = frm.doc.items.find((r) => r.batch_no === result.batch_no);
		if (target_row) {
			target_row_name = target_row.name;
			target_row_idx = frm.doc.items.findIndex((r) => r.name === target_row.name);
		}
	} else if (result.action === "move_to_existing") {
		target_row_idx = result.existing_row_index;
		if (target_row_idx !== undefined && frm.doc.items[target_row_idx]) {
			target_row_name = frm.doc.items[target_row_idx].name;
		}
	} else if (result.row_name) {
		target_row_name = result.row_name;
		target_row_idx = frm.doc.items.findIndex((r) => r.name === result.row_name);
	}

	if (!target_row_name && result.batch_no) {
		const target_row = frm.doc.items.find((r) => r.batch_no === result.batch_no);
		if (target_row) {
			target_row_name = target_row.name;
			target_row_idx = frm.doc.items.findIndex((r) => r.name === target_row.name);
		}
	}

	if (
		!target_row_name &&
		frm.current_focused_row !== null &&
		frm.doc.items[frm.current_focused_row]
	) {
		target_row_name = frm.doc.items[frm.current_focused_row].name;
		target_row_idx = frm.current_focused_row;
	}

	if (!target_row_name) {
		return;
	}

	setTimeout(function () {
		const grid = frm.fields_dict.items.grid;
		if (!grid || !grid.grid_rows_by_docname) {
			return;
		}
		const grid_row = grid.grid_rows_by_docname[target_row_name];
		if (grid_row && grid_row.columns) {
			const scanner_field = grid_row.columns.find((col) => col.fieldname === "scanner");
			if (scanner_field && scanner_field.$input) {
				scanner_field.$input.focus();
			}
		}
		if (target_row_idx !== null) {
			ss_highlight_row(frm, target_row_idx);
			ss_scroll_to_row(frm, target_row_idx);
		}
	}, 100);
}

function ss_patch_row(cdt, cdn, values) {
	const row = locals[cdt] && locals[cdt][cdn];
	if (!row) {
		return;
	}
	Object.keys(values).forEach((key) => {
		if (values[key] !== undefined) {
			row[key] = values[key];
		}
	});
}

const SS_SAVE_EVERY_N_SCANS_DEFAULT = 10;

function ss_get_auto_save_interval(frm) {
	const n = cint(frm.doc.auto_save_scan_interval);
	return n > 0 ? n : SS_SAVE_EVERY_N_SCANS_DEFAULT;
}

function ss_finish_scan(frm, result, opts) {
	opts = opts || {};
	if (opts.message) {
		frappe.show_alert({
			message: opts.message,
			indicator: opts.indicator || "green",
			timeout: 1.5,
		});
	}
	// Immediate refocus — no full save wait on the fast path
	ss_refocus_scanner_field(frm, result);
}

function ss_save_and_refocus(frm, result) {
	frm.save_or_update({
		callback() {
			frm.ss_scans_since_save = 0;
			frappe.show_alert({
				message: __("Saved"),
				indicator: "green",
				timeout: 1,
			});
			setTimeout(() => ss_refocus_scanner_field(frm, result), 300);
		},
		error() {
			frappe.msgprint({
				title: __("Save Error"),
				indicator: "red",
				message: __("Failed to save. Please save manually and try again."),
			});
		},
	});
}

/** Count successful scans; every N scans do a full document save. Returns true if save started. */
function ss_note_scan_and_maybe_save(frm, result) {
	frm.ss_scans_since_save = (frm.ss_scans_since_save || 0) + 1;
	if (frm.ss_scans_since_save < ss_get_auto_save_interval(frm)) {
		return false;
	}
	ss_save_and_refocus(frm, result);
	return true;
}

function ss_process_scan(frm, cdt, cdn, row, barcode, current_row_idx, warehouse) {
	frappe.call({
		method: "beveren_health.beveren_health.customize.scanner.process_batch_scan",
		args: {
			barcode_data: barcode,
			document_name: frm.doc.name,
			doctype: "Stock Scanner",
			current_item_code: row.item_code,
			current_batch_no: row.batch_no || "",
			warehouse: warehouse,
			current_row_name: row.name,
		},
		callback(r) {
			if (!r.message || !r.message.success) {
				frappe.msgprint({
					title: __("Scan Error"),
					indicator: "red",
					message: (r.message && r.message.message) || __("Failed to process barcode"),
				});
				return;
			}
			const result = r.message;
			switch (result.action) {
				case "assign_to_current":
					ss_handle_assign_to_current(frm, cdt, cdn, result, current_row_idx, warehouse);
					break;
				case "append_serial":
					ss_handle_append_serial(frm, cdt, cdn, result, current_row_idx);
					break;
				case "create_new_row":
					ss_handle_create_new_row(frm, result, warehouse);
					break;
				case "move_to_existing":
					ss_handle_move_to_existing(frm, result);
					break;
			}
			// Fast path: persist per scan on server; full form save every 10 scans
			if (result.server_persisted) {
				if (result.action !== "create_new_row") {
					if (!ss_note_scan_and_maybe_save(frm, result)) {
						ss_finish_scan(frm, result);
					}
				}
			} else {
				ss_save_and_refocus(frm, result);
			}
		},
		error() {
			frappe.msgprint(__("Error processing scan. Check server logs."));
		},
	});
}

function ss_handle_assign_to_current(frm, cdt, cdn, result, row_idx, warehouse) {
	const qty = result.qty || 1;
	const amount = result.amount || 0;
	const rate = result.rate || result.valuation_rate || 0;

	if (result.server_persisted) {
		ss_patch_row(cdt, cdn, {
			item_code: result.item_code,
			item_name: result.item_name,
			use_serial_batch_fields: 1,
			batch_no: result.batch_no,
			warehouse: warehouse,
			allow_zero_valuation_rate: 1,
			valuation_rate: rate,
			serial_no: result.serial_no || "",
			qty: qty,
			current_qty: qty,
			amount: amount,
			current_amount: amount,
			gtin: result.gtin || "",
			expiry_date: result.expiry_date || "",
			manufacturing_date: result.mfg_date || "",
		});
	} else {
		frappe.model.set_value(cdt, cdn, "item_code", result.item_code);
		frappe.model.set_value(cdt, cdn, "item_name", result.item_name);
		frappe.model.set_value(cdt, cdn, "use_serial_batch_fields", 1);
		frappe.model.set_value(cdt, cdn, "batch_no", result.batch_no);
		frappe.model.set_value(cdt, cdn, "warehouse", warehouse);
		frappe.model.set_value(cdt, cdn, "allow_zero_valuation_rate", 1);
		if (rate) {
			frappe.model.set_value(cdt, cdn, "valuation_rate", rate);
		}
		if (result.serial_no) {
			ss_set_lots(cdt, cdn, result.serial_no, frm);
		} else {
			frappe.model.set_value(cdt, cdn, "qty", 1);
			frappe.model.set_value(cdt, cdn, "current_qty", 1);
			frappe.model.set_value(cdt, cdn, "amount", amount);
			frappe.model.set_value(cdt, cdn, "current_amount", amount);
		}
		ss_apply_scan_metadata(cdt, cdn, result, locals[cdt][cdn], false);
	}

	frm.refresh_field("items");
	frm.current_focused_row = row_idx;
	ss_highlight_row(frm, row_idx);
	ss_scroll_to_row(frm, row_idx);

	frappe.show_alert({
		message: `✓ ${result.item_name} | ${result.batch_no}`,
		indicator: "green",
	});
}

function ss_handle_append_serial(frm, cdt, cdn, result, row_idx) {
	const lots = result.all_dispensing_lots || result.all_serials || "";

	if (result.server_persisted) {
		ss_patch_row(cdt, cdn, {
			qty: result.new_qty,
			current_qty: result.new_qty,
			amount: result.new_amount,
			current_amount: result.new_amount,
			serial_no: lots,
			allow_zero_valuation_rate: 1,
		});
	} else {
		frappe.model.set_value(cdt, cdn, "qty", result.new_qty);
		frappe.model.set_value(cdt, cdn, "current_qty", result.new_qty);
		frappe.model.set_value(cdt, cdn, "amount", result.new_amount);
		frappe.model.set_value(cdt, cdn, "current_amount", result.new_amount);
		ss_set_lots(cdt, cdn, lots, frm);
		frappe.model.set_value(cdt, cdn, "allow_zero_valuation_rate", 1);
		ss_apply_scan_metadata(cdt, cdn, result, locals[cdt][cdn], true);
	}

	frm.refresh_field("items");
	frm.current_focused_row = row_idx;
	ss_highlight_row(frm, row_idx);
	ss_scroll_to_row(frm, row_idx);
}

function ss_handle_create_new_row(frm, result, warehouse) {
	if (result.server_persisted) {
		// Row already saved on server — reload once to pick up child name, then refocus
		frm.reload_doc().then(() => {
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
			ss_highlight_row(frm, new_idx);
			ss_scroll_to_row(frm, new_idx);
			if (!ss_note_scan_and_maybe_save(frm, result)) {
				ss_finish_scan(frm, result, {
					message: `✓ ${result.item_name} | ${result.batch_no}`,
					indicator: "green",
				});
			} else {
				frappe.show_alert({
					message: `✓ ${result.item_name} | ${result.batch_no}`,
					indicator: "green",
				});
			}
		});
		return;
	}

	const new_row = frm.add_child("items", {
		item_code: result.item_code,
		item_name: result.item_name,
		warehouse: warehouse,
		qty: result.qty || 1,
		current_qty: result.qty || 1,
		valuation_rate: result.rate || 0,
		amount: result.amount || 0,
		current_amount: result.amount || 0,
		batch_no: result.batch_no,
		serial_no: result.serial_no || "",
		gtin: result.gtin || "",
		manufacturing_date: result.mfg_date || "",
		expiry_date: result.expiry_date || "",
		use_serial_batch_fields: 1,
		allow_zero_valuation_rate: 1,
	});

	frm.refresh_field("items");
	const new_idx = frm.doc.items.findIndex((r) => r.name === new_row.name);
	frm.current_focused_row = new_idx;
	ss_highlight_row(frm, new_idx);
	ss_scroll_to_row(frm, new_idx);
}

function ss_handle_move_to_existing(frm, result) {
	const target_idx = result.existing_row_index;
	const target_row = frm.doc.items[target_idx];
	if (!target_row) {
		return;
	}

	const cdt = target_row.doctype;
	const cdn = target_row.name;

	if (result.server_persisted) {
		const lots = result.all_dispensing_lots || result.all_serials || target_row.serial_no;
		ss_patch_row(cdt, cdn, {
			qty: result.new_qty != null ? result.new_qty : target_row.qty,
			current_qty: result.new_qty != null ? result.new_qty : target_row.current_qty,
			amount: result.new_amount != null ? result.new_amount : target_row.amount,
			current_amount:
				result.new_amount != null ? result.new_amount : target_row.current_amount,
			serial_no: lots,
			allow_zero_valuation_rate: 1,
		});
	} else if (result.serial_no) {
		const updated = ss_append_lot(target_row.serial_no, result.serial_no);
		if (updated !== (target_row.serial_no || "")) {
			ss_set_lots(cdt, cdn, updated, frm);
		}
		ss_apply_scan_metadata(cdt, cdn, result, target_row, true);
	}

	frm.refresh_field("items");
	frm.current_focused_row = target_idx;
	ss_highlight_row(frm, target_idx);
	ss_scroll_to_row(frm, target_idx);

	frappe.show_alert({
		message: __("Added to existing batch: {0}", [result.batch_no]),
		indicator: "blue",
	});
}

function ss_run_scan(frm, cdt, cdn, row, barcode) {
	const warehouse = row.warehouse || frm.doc.set_warehouse;
	if (!warehouse) {
		frappe.msgprint(__("Set Default Warehouse on the form or warehouse on the row before scanning."));
		frappe.model.set_value(cdt, cdn, "scanner", "");
		return;
	}

	const current_row_idx = frm.doc.items.findIndex((r) => r.name === cdn);
	frappe.model.set_value(cdt, cdn, "scanner", "");

	if (frm.is_new()) {
		frm.save_or_update({
			callback() {
				ss_process_scan(frm, cdt, cdn, locals[cdt][cdn], barcode, current_row_idx, warehouse);
			},
			error() {
				frappe.msgprint(__("Save the document first, then scan again."));
			},
		});
	} else {
		ss_process_scan(frm, cdt, cdn, row, barcode, current_row_idx, warehouse);
	}
}

function show_create_stock_recon_dialog(frm) {
	frappe.call({
		method: "beveren_health.beveren_health.customize.stock_scanner.get_eligible_stock_scanners",
		args: { company: frm.doc.company || null },
		callback(r) {
			const scanners = r.message || [];
			if (!scanners.length) {
				frappe.msgprint(
					__(
						"No submitted Stock Scanners are available. Only submitted scanners that are not yet linked to a Stock Reconciliation are listed."
					)
				);
				return;
			}

			const options = scanners.map((s) => ({
				label: `${s.name} — ${frappe.datetime.str_to_user(s.posting_date)} (${s.set_warehouse || __("No warehouse")})`,
				value: s.name,
			}));

			const defaults = [];
			if (frm.doc.name && scanners.some((s) => s.name === frm.doc.name)) {
				defaults.push(frm.doc.name);
			}

			const d = new frappe.ui.Dialog({
				title: __("Create Stock Reconciliation"),
				fields: [
					{
						fieldtype: "MultiCheck",
						fieldname: "scanners",
						label: __("Stock Scanners"),
						options,
						columns: 1,
						default: defaults,
					},
				],
				primary_action_label: __("Create"),
				primary_action(values) {
					const selected = values.scanners || [];
					if (!selected.length) {
						frappe.msgprint(__("Select at least one Stock Scanner."));
						return;
					}
					frappe.call({
						method:
							"beveren_health.beveren_health.customize.stock_scanner.create_stock_reconciliation_from_scanners",
						args: { scanner_names: selected },
						freeze: true,
						freeze_message: __("Creating Stock Reconciliation..."),
						callback(res) {
							d.hide();
							if (res.message) {
								frappe.show_alert({
									message: __(
										"Stock Reconciliation {0} created — review Difference Account and other fields before submit.",
										[res.message]
									),
									indicator: "green",
								});
								frappe.set_route("Form", "Stock Reconciliation", res.message);
								if (frm.doc.name) {
									frm.reload_doc();
								}
							}
						},
						error(r) {
							frappe.msgprint({
								title: __("Could not create Stock Reconciliation"),
								indicator: "red",
								message:
									(r.message && r.message.messages && r.message.messages.join("<br>")) ||
									r.message ||
									__("Unknown error"),
							});
						},
					});
				},
			});
			d.show();
		},
	});
}

frappe.ui.form.on("Stock Scanner", {
	onload(frm) {
		frm.current_focused_row = null;
		frm.ss_scans_since_save = 0;
		ss_inject_highlight_style();
		setTimeout(() => ss_setup_row_click_tracking(frm), 500);
	},

	refresh(frm) {
		setTimeout(() => ss_setup_row_click_tracking(frm), 300);

		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(
				__("Create Stock Reconciliation"),
				() => show_create_stock_recon_dialog(frm),
				__("Actions")
			);
		}

		if (frm.doc.stock_reconciliation) {
			frm.add_custom_button(
				__("Stock Reconciliation"),
				() => frappe.set_route("Form", "Stock Reconciliation", frm.doc.stock_reconciliation),
				__("View")
			);
		}
	},
});

frappe.ui.form.on("Stock Scanner Item", {
	item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item_code) {
			return;
		}
		frappe.db.get_value("Item", row.item_code, "has_batch_no", (r) => {
			if (r && cint(r.has_batch_no)) {
				frappe.model.set_value(cdt, cdn, "use_serial_batch_fields", 1);
			}
		});
	},

	scanner(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const barcode = (row.scanner || "").trim();
		if (!barcode) {
			return;
		}
		if (frm.doc.docstatus === 1) {
			frappe.msgprint(__("Cannot scan on a submitted Stock Scanner. Amend the document to continue scanning."));
			frappe.model.set_value(cdt, cdn, "scanner", "");
			return;
		}
		ss_run_scan(frm, cdt, cdn, row, barcode);
	},

	serial_no(frm, cdt, cdn) {
		ss_sync_qty_from_lots(frm, cdt, cdn);
	},
});
