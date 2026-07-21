// Copyright (c) 2026, Beveren Software and contributors
// For license information, please see license.txt

frappe.provide("beveren_health.warehouse_cost_center");

beveren_health.warehouse_cost_center.get_cost_center = function (warehouse) {
	if (!warehouse) {
		return Promise.resolve(null);
	}
	return frappe.db
		.get_value("Warehouse", warehouse, "custom_cost_center")
		.then((r) => (r && r.message && r.message.custom_cost_center) || null);
};

/**
 * Set header (and optionally item) cost_center from Warehouse.custom_cost_center.
 */
beveren_health.warehouse_cost_center.set_from_warehouse = function (frm, warehouse, opts) {
	opts = opts || {};
	const header_field = opts.header_field || "cost_center";
	const update_items = opts.update_items !== false;
	const item_field = opts.item_field || "cost_center";

	if (!warehouse || !frm) {
		return;
	}

	beveren_health.warehouse_cost_center.get_cost_center(warehouse).then((cost_center) => {
		if (!cost_center) {
			return;
		}

		if (frm.fields_dict[header_field]) {
			frm.set_value(header_field, cost_center);
		}

		if (update_items && frm.doc.items && frm.doc.items.length) {
			frm.doc.items.forEach((row) => {
				if (frappe.meta.has_field(row.doctype, item_field)) {
					frappe.model.set_value(row.doctype, row.name, item_field, cost_center);
				}
			});
		}
	});
};

/**
 * Set a single child row's cost_center from a warehouse.
 */
beveren_health.warehouse_cost_center.set_row_from_warehouse = function (
	frm,
	cdt,
	cdn,
	warehouse,
	field
) {
	field = field || "cost_center";
	if (!warehouse || !frappe.meta.has_field(cdt, field)) {
		return;
	}

	beveren_health.warehouse_cost_center.get_cost_center(warehouse).then((cost_center) => {
		if (cost_center) {
			frappe.model.set_value(cdt, cdn, field, cost_center);
		}
	});
};
