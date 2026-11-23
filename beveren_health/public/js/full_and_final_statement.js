frappe.ui.form.on("Full and Final Statement", {
	refresh(frm) {
		// Override HRMS set_query to restrict reference_document_type to
		// HR/Payroll/Loan Management modules + Indemnity only from Beveren Health
		_override_reference_queries(frm, "payables");
		_override_reference_queries(frm, "receivables");

		// Restrict Indemnity link to the same employee only
		frm.set_query("custom_indemnity", function () {
			return {
				filters: {
					employee: frm.doc.employee,
					docstatus: ["!=", 2],
				},
			};
		});

		if (!frm.is_new() && frm.doc.docstatus === 0 && !frm.doc.custom_indemnity) {
			frm.add_custom_button(
				__("Generate Indemnity"),
				() => _generate_indemnity(frm),
				__("Create")
			);
		}
	},

	custom_indemnity(frm) {
		const name = frm.doc.custom_indemnity;
		const request = (frm.__indemnity_request || 0) + 1;
		frm.__indemnity_request = request;
		if (!name) {
			delete frm.doc.__indemnity_payables_initialized_for;
			return;
		}
		if (frm.doc.__indemnity_payables_initialized_for === name) return;
		return frappe.db.get_doc("Indemnity", name).then((indemnity) => {
			if (frm.doc.custom_indemnity !== name || frm.__indemnity_request !== request) return;
			_populate_indemnity_payables(frm, indemnity);
			frm.doc.__indemnity_payables_initialized_for = name;
		});
	},
});

frappe.ui.form.on("Full and Final Outstanding Statement", {
	payables_remove(frm) {
		frm.trigger("calculate_total_payable_amt");
	},

	reference_document(frm, cdt, cdn) {
		const child = locals[cdt][cdn];
		if (child.reference_document_type === "Indemnity" && child.reference_document) {
			frappe.db
				.get_value("Indemnity", child.reference_document, ["payable_account", "amount"])
				.then((r) => {
					if (r.message) {
						frappe.model.set_value(
							cdt,
							cdn,
							"account",
							r.message.payable_account || ""
						);
						frappe.model.set_value(cdt, cdn, "amount", r.message.amount || 0);
					}
				});
		}
	},
});

function _generate_indemnity(frm) {
	if (frm.is_dirty()) {
		frappe.msgprint({
			title: __("Unsaved Changes"),
			message: __("Please save the statement before generating the Indemnity."),
			indicator: "orange",
		});
		return;
	}

	frappe.call({
		method: "beveren_health.beveren_health.customize.full_and_final_settlement.create_indemnity",
		args: { fnf: frm.doc.name },
		freeze: true,
		freeze_message: __("Generating Indemnity..."),
		callback(r) {
			if (!r.message) return;
			frm.reload_doc().then(() => {
				frappe.show_alert({
					message: __("Indemnity {0} created", [
						`<a href="/app/indemnity/${encodeURIComponent(
							r.message
						)}">${frappe.utils.escape_html(r.message)}</a>`,
					]),
					indicator: "green",
				});
			});
		},
	});
}

function _override_reference_queries(frm, type) {
	frm.set_query("reference_document_type", type, function () {
		return {
			query: "beveren_health.beveren_health.customize.full_and_final_settlement.get_reference_doctypes",
		};
	});
}

function _populate_indemnity_payables(frm, indemnity) {
	const LABEL_BEFORE = "Indemnity Reward (Before Cut-Off Date)";
	const LABEL_AFTER = "Indemnity Reward (After Cut-Off Date)";
	const labels = [LABEL_BEFORE, LABEL_AFTER];
	for (const row of [...(frm.doc.payables || [])]) {
		if (
			labels.includes(row.component) &&
			row.reference_document_type === "Indemnity" &&
			row.reference_document !== indemnity.name
		) {
			frappe.model.clear_doc(row.doctype, row.name);
		}
	}

	function upsert(label, amount, account) {
		let row = (frm.doc.payables || []).find(
			(r) =>
				r.component === label &&
				r.reference_document_type === "Indemnity" &&
				r.reference_document === indemnity.name
		);
		if (!row) {
			if (!flt(amount)) return;
			row = frm.add_child("payables");
		}
		// Set directly on the row object to avoid Dynamic Link clear-on-change
		// and event cascade that corrupts the BEFORE row when AFTER is processed
		row.component = label;
		row.amount = flt(amount, 3);
		row.account = account || "";
		row.reference_document_type = "Indemnity";
		row.reference_document = indemnity.name;
		row.status = row.status || "Unsettled";
		row.paid_via_salary_slip = indemnity.pay_via_salary_slip ? 1 : 0;
	}

	upsert(LABEL_BEFORE, indemnity.indemnity_before, indemnity.payable_account);
	upsert(LABEL_AFTER, indemnity.indemnity_after, indemnity.payable_account);

	frm.refresh_field("payables");
	frm.trigger("calculate_total_payable_amt");
}
