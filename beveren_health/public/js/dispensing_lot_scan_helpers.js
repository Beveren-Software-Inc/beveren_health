// Copyright (c) 2026, Beveren Software and contributors
// For license information, please see license.txt

frappe.provide("beveren_health.dispensing_lot_scan");

beveren_health.dispensing_lot_scan.DISPENSING_LOT_FIELD = "custom_dispensing_lot";

beveren_health.dispensing_lot_scan.append_lot = function (existing, new_serial) {
	if (!new_serial) {
		return existing || "";
	}
	const lots = beveren_health.dispensing_lot_scan.split_lots(existing);
	if (!lots.includes(new_serial)) {
		lots.push(new_serial);
	}
	return lots.join("\n");
};

beveren_health.dispensing_lot_scan.split_lots = function (value) {
	if (!value) {
		return [];
	}
	return value
		.split(/\n|,/)
		.map((s) => s.trim())
		.filter(Boolean);
};

beveren_health.dispensing_lot_scan.count_lots = function (value) {
	return beveren_health.dispensing_lot_scan.split_lots(value).length;
};

beveren_health.dispensing_lot_scan.set_lots = function (cdt, cdn, value, frm) {
	frappe.model.set_value(
		cdt,
		cdn,
		beveren_health.dispensing_lot_scan.DISPENSING_LOT_FIELD,
		value || "",
		() => {
			const form = frm || frappe.get_cur_frm?.() || (typeof cur_frm !== "undefined" ? cur_frm : null);
			if (form) {
				beveren_health.dispensing_lot_scan.sync_qty_from_lots(form, cdt, cdn);
			}
		}
	);
};

/** Recalculate row qty from the number of dispensing lots (like standard serial_no). */
beveren_health.dispensing_lot_scan.sync_qty_from_lots = function (frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row) {
		return;
	}

	let qty = beveren_health.dispensing_lot_scan.count_lots(row.custom_dispensing_lot);
	const rate = flt(row.rate);
	const basic_rate = flt(row.basic_rate);

	// Material Transfer: one serial = one full pack (no unit breakdown on the line)
	if (
		frm &&
		frm.doc.doctype === "Stock Entry" &&
		frm.doc.purpose === "Material Transfer"
	) {
		qty = qty > 0 ? 1 : 0;
	}

	if (cdt === "Stock Reconciliation Item") {
		frappe.model.set_value(cdt, cdn, "qty", qty);
		frappe.model.set_value(cdt, cdn, "current_qty", qty);
		frappe.model.set_value(cdt, cdn, "amount", qty * rate);
		frappe.model.set_value(cdt, cdn, "current_amount", qty * rate);
		frappe.model.set_value(cdt, cdn, "allow_zero_valuation_rate", 1);
	} else if (cdt === "Stock Entry Detail") {
		frappe.model.set_value(cdt, cdn, "qty", qty);
		frappe.model.set_value(cdt, cdn, "transfer_qty", qty);
		frappe.model.set_value(cdt, cdn, "amount", qty * (basic_rate || rate));
		frappe.model.set_value(cdt, cdn, "basic_amount", qty * basic_rate);
	} else if (cdt === "Purchase Receipt Item") {
		frappe.model.set_value(cdt, cdn, "qty", qty);
		frappe.model.set_value(cdt, cdn, "amount", qty * rate);
	}
};

function register_dispensing_lot_qty_sync(child_doctype) {
	frappe.ui.form.on(child_doctype, {
		custom_dispensing_lot(frm, cdt, cdn) {
			beveren_health.dispensing_lot_scan.sync_qty_from_lots(frm, cdt, cdn);
		},
	});
}

register_dispensing_lot_qty_sync("Stock Reconciliation Item");
register_dispensing_lot_qty_sync("Stock Entry Detail");
register_dispensing_lot_qty_sync("Purchase Receipt Item");
