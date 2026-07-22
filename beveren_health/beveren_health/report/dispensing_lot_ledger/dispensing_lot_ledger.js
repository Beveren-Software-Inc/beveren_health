// Copyright (c) 2026, Beveren Software and contributors
// For license information, please see license.txt

frappe.query_reports["Dispensing Lot Ledger"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "item",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
			get_query: function () {
				return {
					filters: {
						custom_has_dispense_lot: 1,
					},
				};
			},
		},
		{
			fieldname: "batch_no",
			label: __("Batch"),
			fieldtype: "Link",
			options: "Batch",
			get_query: function () {
				const item = frappe.query_report.get_filter_value("item");
				if (item) {
					return { filters: { item: item } };
				}
			},
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
		},
		{
			fieldname: "cost_center",
			label: __("Cost Center"),
			fieldtype: "Link",
			options: "Cost Center",
		},
		{
			fieldname: "dispensing_lot",
			label: __("Dispensing Lot"),
			fieldtype: "Link",
			options: "Dispensing Lot",
		},
		{
			fieldname: "movement",
			label: __("Movement"),
			fieldtype: "Select",
			options: "\nIn\nOut\nTransfer",
		},
		{
			fieldname: "transaction_doctype",
			label: __("Transaction DocType"),
			fieldtype: "Link",
			options: "DocType",
			get_query: function () {
				return {
					filters: {
						name: [
							"in",
							[
								"Purchase Receipt",
								"Stock Entry",
								"Stock Reconciliation",
								"Sales Invoice",
							],
						],
					},
				};
			},
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nActive\nPartially Sold\nDelivered\nInactive",
		},
	],
};
