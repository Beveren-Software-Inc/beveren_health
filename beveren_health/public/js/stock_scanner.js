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
	const qty = lot_count > 1 ? lot_count : row_qty > 0 ? row_qty : lot_count || 0;
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
	wrapper.off("focusin.ss_scanner", ".grid-row");

	const on_row_focus = function () {
		const idx = $(this).attr("data-idx");
		if (!idx) {
			return;
		}
		const new_idx = parseInt(idx, 10) - 1;
		ss_leave_row_if_needed(frm, new_idx);
	};

	wrapper.on("click.ss_scanner", ".grid-row", on_row_focus);
	wrapper.on("focusin.ss_scanner", ".grid-row", on_row_focus);
}

function ss_get_item_flags(frm, item_code) {
	frm._ss_item_flags = frm._ss_item_flags || {};
	if (frm._ss_item_flags[item_code]) {
		return Promise.resolve(frm._ss_item_flags[item_code]);
	}
	return frappe.db
		.get_value("Item", item_code, ["has_batch_no", "custom_has_dispense_lot"])
		.then((r) => {
			const flags = {
				has_batch_no: cint(r.message && r.message.has_batch_no),
				has_dispense_lot: cint(r.message && r.message.custom_has_dispense_lot),
			};
			frm._ss_item_flags[item_code] = flags;
			return flags;
		});
}

function ss_validate_row(frm, row) {
	if (!row || !row.item_code || frm.doc.docstatus === 1) {
		return Promise.resolve([]);
	}

	const issues = [];
	return ss_get_item_flags(frm, row.item_code).then((flags) => {
		const checks = [];

		if (flags.has_batch_no && !(row.batch_no || "").trim()) {
			issues.push(__("Item needs a Batch No."));
		}

		if (flags.has_dispense_lot && !ss_count_lots(row.serial_no)) {
			issues.push(__("Item needs a Dispensing Lot."));
		}

		if ((row.batch_no || "").trim()) {
			checks.push(
				frappe.db.get_value("Batch", row.batch_no, "item").then((r) => {
					const batch_item = r.message && r.message.item;
					if (!batch_item) {
						issues.push(__("Batch {0} was not found.", [row.batch_no]));
					} else if (batch_item !== row.item_code) {
						issues.push(
							__("Batch {0} belongs to Item {1}, not {2}.", [
								row.batch_no,
								batch_item,
								row.item_code,
							])
						);
					}
				})
			);
		}

		return Promise.all(checks).then(() => issues);
	});
}

function ss_show_row_issues(frm, row_idx, issues) {
	const row = frm.doc.items[row_idx];
	if (!row || !issues.length) {
		return;
	}
	ss_highlight_row(frm, row_idx);
	ss_scroll_to_row(frm, row_idx);
	frappe.msgprint({
		title: __("Row {0} needs attention", [row.idx]),
		indicator: "orange",
		message: `
			<p><b>${ss_escape_html(row.item_code || "")}</b>
			${row.item_name ? " — " + ss_escape_html(row.item_name) : ""}</p>
			<ul style="margin:0.5rem 0 0;padding-left:1.25rem;">
				${issues.map((msg) => `<li>${ss_escape_html(msg)}</li>`).join("")}
			</ul>
		`,
	});
}

function ss_leave_row_if_needed(frm, new_idx) {
	const prev_idx = frm.current_focused_row;
	if (prev_idx === null || prev_idx === undefined || prev_idx === new_idx) {
		frm.current_focused_row = new_idx;
		return;
	}

	const prev_row = frm.doc.items[prev_idx];
	if (!prev_row || !prev_row.item_code) {
		frm.current_focused_row = new_idx;
		return;
	}

	// Avoid re-validating the same leave while a dialog is open.
	if (frm._ss_validating_leave) {
		return;
	}
	frm._ss_validating_leave = true;

	ss_validate_row(frm, prev_row)
		.then((issues) => {
			frm._ss_validating_leave = false;
			if (issues.length) {
				ss_show_row_issues(frm, prev_idx, issues);
				frm.current_focused_row = prev_idx;
				return;
			}
			frm.current_focused_row = new_idx;
			ss_highlight_row(frm, new_idx);
		})
		.catch(() => {
			frm._ss_validating_leave = false;
			frm.current_focused_row = new_idx;
		});
}

function ss_validate_current_row_fields(frm, cdt, cdn) {
	if (frm.doc.docstatus === 1) {
		return;
	}
	const row = locals[cdt][cdn];
	if (!row || !row.item_code) {
		return;
	}
	const row_idx = (frm.doc.items || []).findIndex((r) => r.name === cdn);
	ss_validate_row(frm, row).then((issues) => {
		if (!issues.length) {
			return;
		}
		// Soft alert while editing fields — full block happens when leaving the row.
		frappe.show_alert({
			message: __("Row {0}: {1}", [row.idx, issues[0]]),
			indicator: "orange",
		});
		if (row_idx >= 0) {
			ss_highlight_row(frm, row_idx);
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
	return beveren_health.auto_save_scan.get_interval(frm);
}

function ss_finish_scan(frm, result, opts) {
	beveren_health.auto_save_scan.finish_scan(frm, result, ss_refocus_scanner_field, opts);
}

function ss_save_and_refocus(frm, result) {
	beveren_health.auto_save_scan.save_and_refocus(frm, result, ss_refocus_scanner_field);
}

/** Count successful scans; every N scans do a full document save. Returns true if save started. */
function ss_note_scan_and_maybe_save(frm, result) {
	return beveren_health.auto_save_scan.note_scan_and_maybe_save(
		frm,
		result,
		ss_refocus_scanner_field
	);
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
		frappe.msgprint(
			__("Set Default Warehouse on the form or warehouse on the row before scanning.")
		);
		frappe.model.set_value(cdt, cdn, "scanner", "");
		return;
	}

	const current_row_idx = frm.doc.items.findIndex((r) => r.name === cdn);
	frappe.model.set_value(cdt, cdn, "scanner", "");

	if (frm.is_new()) {
		frm.save_or_update({
			callback() {
				ss_process_scan(
					frm,
					cdt,
					cdn,
					locals[cdt][cdn],
					barcode,
					current_row_idx,
					warehouse
				);
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
				label: `${s.name} — ${frappe.datetime.str_to_user(s.posting_date)} (${
					s.set_warehouse || __("No warehouse")
				})`,
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
						method: "beveren_health.beveren_health.customize.stock_scanner.create_stock_reconciliation_from_scanners",
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
									(r.message &&
										r.message.messages &&
										r.message.messages.join("<br>")) ||
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

function ss_refocus_header_scan(frm) {
	setTimeout(() => {
		const field = frm.fields_dict.scan_barcode;
		if (field && field.$input) {
			field.$input.focus();
		}
	}, 150);
}

/** Look up an item barcode and put it on its own line, even if that item is already listed. */
function ss_add_item_line_from_barcode(frm, barcode, source_row) {
	frappe.call({
		method: "erpnext.stock.utils.scan_barcode",
		args: {
			search_value: barcode,
			ctx: {
				set_warehouse: frm.doc.set_warehouse || "",
				company: frm.doc.company || "",
			},
		},
		callback(r) {
			const data = r.message || {};
			if (!data.item_code) {
				frappe.show_alert({
					message: __("Cannot find Item with this Barcode"),
					indicator: "red",
				});
				ss_refocus_header_scan(frm);
				return;
			}

			frappe.db.get_value(
				"Item",
				data.item_code,
				["item_name", "stock_uom", "item_group"],
				(item) => {
					item = item || {};
					let cdt;
					let cdn;
					const row_is_empty = source_row && !source_row.item_code;
					if (row_is_empty) {
						cdt = source_row.doctype;
						cdn = source_row.name;
					} else {
						const new_row = frm.add_child("items");
						cdt = new_row.doctype;
						cdn = new_row.name;
					}

					const values = {
						item_code: data.item_code,
						item_name: item.item_name || "",
						item_group: item.item_group || "",
						barcode: data.barcode || barcode,
						qty: 1,
						current_qty: 1,
						warehouse:
							(locals[cdt][cdn] && locals[cdt][cdn].warehouse) ||
							frm.doc.set_warehouse ||
							"",
						stock_uom: data.uom || item.stock_uom || "",
						use_serial_batch_fields: 1,
						allow_zero_valuation_rate: 1,
						scan_barcode: "",
					};
					if (data.batch_no) {
						values.batch_no = data.batch_no;
					}

					frappe.model.set_value(cdt, cdn, values).then(() => {
						if (item.item_name) {
							frappe.model.set_value(cdt, cdn, "item_name", item.item_name);
						}
						frm.refresh_field("items");
						const idx = (frm.doc.items || []).findIndex((row) => row.name === cdn);
						if (idx >= 0) {
							frm.current_focused_row = idx;
							ss_highlight_row(frm, idx);
							ss_scroll_to_row(frm, idx);
						}
						frappe.show_alert({
							message: __("Added {0}", [item.item_name || data.item_code]),
							indicator: "green",
						});
						ss_refocus_header_scan(frm);
					});
				}
			);
		},
	});
}

function ss_escape_html(value) {
	return frappe.utils.escape_html(String(value == null ? "" : value));
}

function ss_show_validation_result(title, result, columns) {
	const rows = (result && result.rows) || [];
	if (!rows.length) {
		frappe.msgprint({
			title: title,
			indicator: "green",
			message: (result && result.message) || __("All lines look good."),
		});
		return;
	}

	const header = columns
		.map(
			(col) =>
				`<th style="padding:6px 8px;text-align:left;">${ss_escape_html(col.label)}</th>`
		)
		.join("");
	const body = rows
		.map((row) => {
			const cells = columns
				.map(
					(col) =>
						`<td style="padding:6px 8px;">${ss_escape_html(row[col.field] ?? "")}</td>`
				)
				.join("");
			return `<tr>${cells}</tr>`;
		})
		.join("");

	frappe.msgprint({
		title: title,
		indicator: "orange",
		message: `
			<p>${ss_escape_html(result.message || "")}</p>
			<div style="max-height:360px;overflow:auto;">
				<table class="table table-bordered" style="margin:0;">
					<thead><tr>${header}</tr></thead>
					<tbody>${body}</tbody>
				</table>
			</div>
		`,
	});
}

function ss_run_validation(frm, method, title, columns) {
	if (frm.is_new()) {
		frappe.msgprint(__("Save the Stock Scanner first."));
		return;
	}

	const run = () => {
		frappe.call({
			method: method,
			args: { name: frm.doc.name },
			freeze: true,
			freeze_message: __("Checking lines..."),
			callback(r) {
				ss_show_validation_result(title, r.message || {}, columns);
			},
		});
	};

	if (frm.is_dirty()) {
		frappe.confirm(
			__("Save the document first so validation uses the latest lines?"),
			() => {
				frm.save().then(run);
			},
			() => {
				run();
			}
		);
		return;
	}

	run();
}

frappe.ui.form.on("Stock Scanner", {
	scan_barcode(frm) {
		const barcode = (frm.doc.scan_barcode || "").trim();
		if (!barcode) {
			return;
		}
		frm.set_value("scan_barcode", "");
		if (frm.doc.docstatus === 1) {
			frappe.msgprint(
				__(
					"Cannot scan on a submitted Stock Scanner. Amend the document to continue scanning."
				)
			);
			return;
		}
		ss_add_item_line_from_barcode(frm, barcode);
	},

	onload(frm) {
		frm.current_focused_row = null;
		frm.ss_scans_since_save = 0;
		frm._ss_item_flags = {};
		frm._ss_validating_leave = false;
		ss_inject_highlight_style();
		setTimeout(() => ss_setup_row_click_tracking(frm), 500);
	},

	refresh(frm) {
		frm.set_query("batch_no", "items", function (doc, cdt, cdn) {
			const row = locals[cdt][cdn];
			if (!row || !row.item_code) {
				return { filters: { name: ["in", []] } };
			}
			return {
				filters: {
					item: row.item_code,
				},
			};
		});

		setTimeout(() => ss_setup_row_click_tracking(frm), 300);

		if (!frm.is_new()) {
			frm.add_custom_button(
				__("Validate Batch Items"),
				() =>
					ss_run_validation(
						frm,
						"beveren_health.beveren_health.customize.stock_scanner.validate_missing_batches",
						__("Missing Batches"),
						[
							{ field: "idx", label: __("Row") },
							{ field: "item_code", label: __("Item") },
							{ field: "item_name", label: __("Item Name") },
							{ field: "warehouse", label: __("Warehouse") },
							{ field: "qty", label: __("Qty") },
						]
					),
				__("Validate")
			);
			frm.add_custom_button(
				__("Validate Dispensing Lots"),
				() =>
					ss_run_validation(
						frm,
						"beveren_health.beveren_health.customize.stock_scanner.validate_missing_dispensing_lots",
						__("Missing Dispensing Lots"),
						[
							{ field: "idx", label: __("Row") },
							{ field: "item_code", label: __("Item") },
							{ field: "item_name", label: __("Item Name") },
							{ field: "batch_no", label: __("Batch") },
							{ field: "warehouse", label: __("Warehouse") },
							{ field: "qty", label: __("Qty") },
						]
					),
				__("Validate")
			);
			frm.add_custom_button(
				__("Validate Batch Belongs to Item"),
				() =>
					ss_run_validation(
						frm,
						"beveren_health.beveren_health.customize.stock_scanner.validate_batch_item_mismatch",
						__("Batch / Item Mismatch"),
						[
							{ field: "idx", label: __("Row") },
							{ field: "item_code", label: __("Item") },
							{ field: "item_name", label: __("Item Name") },
							{ field: "batch_no", label: __("Batch") },
							{ field: "batch_item", label: __("Batch Belongs To") },
							{ field: "reason", label: __("Reason") },
						]
					),
				__("Validate")
			);
		}

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
				() =>
					frappe.set_route("Form", "Stock Reconciliation", frm.doc.stock_reconciliation),
				__("View")
			);
		}
	},
});

frappe.ui.form.on("Stock Scanner Item", {
	item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item_code) {
			if (row.batch_no) {
				frappe.model.set_value(cdt, cdn, "batch_no", "");
			}
			return;
		}
		if (frm._ss_item_flags) {
			delete frm._ss_item_flags[row.item_code];
		}
		if (row.batch_no) {
			frappe.db.get_value("Batch", row.batch_no, "item", (r) => {
				if (r && r.item && r.item !== row.item_code) {
					frappe.model.set_value(cdt, cdn, "batch_no", "");
				}
			});
		}
		frappe.db.get_value("Item", row.item_code, "has_batch_no", (r) => {
			if (r && cint(r.has_batch_no)) {
				frappe.model.set_value(cdt, cdn, "use_serial_batch_fields", 1);
			}
		});
		ss_validate_current_row_fields(frm, cdt, cdn);
	},

	batch_no(frm, cdt, cdn) {
		ss_validate_current_row_fields(frm, cdt, cdn);
	},

	scan_barcode(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const barcode = (row.scan_barcode || "").trim();
		if (!barcode) {
			return;
		}
		frappe.model.set_value(cdt, cdn, "scan_barcode", "");
		if (frm.doc.docstatus === 1) {
			frappe.msgprint(
				__(
					"Cannot scan on a submitted Stock Scanner. Amend the document to continue scanning."
				)
			);
			return;
		}
		ss_add_item_line_from_barcode(frm, barcode, row);
	},

	scanner(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const barcode = (row.scanner || "").trim();
		if (!barcode) {
			return;
		}
		if (frm.doc.docstatus === 1) {
			frappe.msgprint(
				__(
					"Cannot scan on a submitted Stock Scanner. Amend the document to continue scanning."
				)
			);
			frappe.model.set_value(cdt, cdn, "scanner", "");
			return;
		}
		ss_run_scan(frm, cdt, cdn, row, barcode);
	},

	serial_no(frm, cdt, cdn) {
		ss_sync_qty_from_lots(frm, cdt, cdn);
		ss_validate_current_row_fields(frm, cdt, cdn);
	},

	add_new_batch(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (frm.doc.docstatus === 1) {
			frappe.msgprint(__("Cannot add a batch on a submitted Stock Scanner."));
			return;
		}
		if (!row.item_code) {
			frappe.msgprint(__("Select an Item before adding a batch."));
			return;
		}

		frappe.model.with_doctype("Batch", () => {
			const batch = frappe.model.get_new_doc("Batch");
			batch.item = row.item_code;
			frappe.ui.form.make_quick_entry(
				"Batch",
				(doc) => {
					if (!doc || !doc.name) {
						return;
					}
					frappe.model.set_value(cdt, cdn, "batch_no", doc.name);
					frappe.model.set_value(cdt, cdn, "use_serial_batch_fields", 1);
				},
				null,
				batch
			);
		});
	},
});
