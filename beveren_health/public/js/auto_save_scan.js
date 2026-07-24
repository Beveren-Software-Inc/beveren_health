// Copyright (c) 2026, Beveren Software and contributors
// For license information, please see license.txt

frappe.provide("beveren_health.auto_save_scan");

beveren_health.auto_save_scan.DEFAULT_INTERVAL = 10;

beveren_health.auto_save_scan.get_interval = function (frm) {
	const n = cint(frm.doc.auto_save_scan_interval);
	return n > 0 ? n : beveren_health.auto_save_scan.DEFAULT_INTERVAL;
};

beveren_health.auto_save_scan.patch_row = function (cdt, cdn, values) {
	const row = locals[cdt] && locals[cdt][cdn];
	if (!row) {
		return;
	}
	Object.keys(values || {}).forEach((key) => {
		if (values[key] !== undefined) {
			row[key] = values[key];
		}
	});
};

/**
 * After a successful scan: full form save every N scans when server already
 * persisted the row; otherwise save immediately. create_new_row with
 * server_persisted is handled by the caller (reload path).
 */
beveren_health.auto_save_scan.after_successful_scan = function (frm, result, refocus_fn) {
	if (result.server_persisted) {
		if (result.action === "create_new_row") {
			return;
		}
		if (!beveren_health.auto_save_scan.note_scan_and_maybe_save(frm, result, refocus_fn)) {
			beveren_health.auto_save_scan.finish_scan(frm, result, refocus_fn);
		}
	} else {
		beveren_health.auto_save_scan.save_and_refocus(frm, result, refocus_fn);
	}
};

beveren_health.auto_save_scan.finish_scan = function (frm, result, refocus_fn, opts) {
	opts = opts || {};
	if (opts.message) {
		frappe.show_alert({
			message: opts.message,
			indicator: opts.indicator || "green",
			timeout: 1.5,
		});
	}
	if (typeof refocus_fn === "function") {
		refocus_fn(frm, result);
	}
};

beveren_health.auto_save_scan.save_and_refocus = function (frm, result, refocus_fn) {
	frm.save_or_update({
		callback() {
			frm._scans_since_save = 0;
			frappe.show_alert({
				message: __("Saved"),
				indicator: "green",
				timeout: 1,
			});
			setTimeout(() => {
				if (typeof refocus_fn === "function") {
					refocus_fn(frm, result);
				}
			}, 300);
		},
		error() {
			frappe.msgprint({
				title: __("Save Error"),
				indicator: "red",
				message: __("Failed to save. Please save manually and try again."),
			});
		},
	});
};

/** Count successful scans; every N scans do a full document save. Returns true if save started. */
beveren_health.auto_save_scan.note_scan_and_maybe_save = function (frm, result, refocus_fn) {
	frm._scans_since_save = (frm._scans_since_save || 0) + 1;
	if (frm._scans_since_save < beveren_health.auto_save_scan.get_interval(frm)) {
		return false;
	}
	beveren_health.auto_save_scan.save_and_refocus(frm, result, refocus_fn);
	return true;
};

/**
 * Reload after server-created child row, then apply interval save / refocus.
 */
beveren_health.auto_save_scan.after_server_created_row = function (frm, result, refocus_fn, on_loaded) {
	frm.reload_doc().then(() => {
		if (typeof on_loaded === "function") {
			on_loaded();
		}
		if (!beveren_health.auto_save_scan.note_scan_and_maybe_save(frm, result, refocus_fn)) {
			beveren_health.auto_save_scan.finish_scan(frm, result, refocus_fn, {
				message: `✓ ${result.item_name || ""} | ${result.batch_no || ""}`,
				indicator: "green",
			});
		} else if (result.item_name || result.batch_no) {
			frappe.show_alert({
				message: `✓ ${result.item_name || ""} | ${result.batch_no || ""}`,
				indicator: "green",
			});
		}
	});
};
