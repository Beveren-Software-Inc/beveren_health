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

		if (frm.doc.docstatus === 0) {
			if (!frm.doc.custom_indemnity) {
				frm.add_custom_button(
					__("Generate Indemnity"),
					() => _generate_or_update_indemnity(frm),
					__("Create")
				);
			} else {
				frm.add_custom_button(
					__("Update Indemnity"),
					() => _generate_or_update_indemnity(frm),
					__("Actions")
				);
				frm.add_custom_button(
					__("View Indemnity"),
					() => frappe.set_route("Form", "Indemnity", frm.doc.custom_indemnity),
					__("Actions")
				);
			}
		}
	},

	employee(frm) {
		if (!frm.doc.employee) return;
		frappe.call({
			method: "beveren_health.beveren_health.customize.full_and_final_settlement.get_indemnity_configuration",
			args: {
				employee: frm.doc.employee,
				company: frm.doc.company,
			},
			callback(r) {
				if (!r.message) return;
				const d = r.message;
				if (!frm.doc.custom_cutoff_date && d.cutoff_date) {
					frm.set_value("custom_cutoff_date", d.cutoff_date);
				}
				if (d.base_salary) {
					frm.set_value("custom_base_salary", d.base_salary);
				}
				if (d.basic_salary) {
					frm.set_value("custom_basic_salary", d.basic_salary);
				}
				if (d.date_of_joining) {
					frm.set_value("date_of_joining", d.date_of_joining);
				}
				if (d.relieving_date) {
					frm.set_value("relieving_date", d.relieving_date);
				}
				if (d.nationality) {
					frm.set_value("custom_nationality", d.nationality);
				}
				if (d.is_gosi_registered !== undefined) {
					frm.set_value("custom_under_gosi_registered_", d.is_gosi_registered);
				}
				if (d.total_experience) {
					frm.set_value("custom_total_experience", d.total_experience);
				}
				_update_ir_base_and_reward_ui(frm);
			},
		});
	},

	custom_consider_full_salary(frm) {
		_update_ir_base_and_reward_ui(frm);
		if (frm.doc.custom_indemnity && frm.doc.docstatus === 0) {
			_generate_or_update_indemnity(frm);
		}
	},

	custom_consider_full_salary_after_cutoff_date(frm) {
		_update_ir_base_and_reward_ui(frm);
		if (frm.doc.custom_indemnity && frm.doc.docstatus === 0) {
			_generate_or_update_indemnity(frm);
		}
	},

	custom_base_salary(frm) {
		_update_ir_base_and_reward_ui(frm);
	},

	custom_basic_salary(frm) {
		_update_ir_base_and_reward_ui(frm);
	},

	date_of_joining(frm) {
		_compute_total_experience_ui(frm);
	},

	relieving_date(frm) {
		_compute_total_experience_ui(frm);
	},

	custom_indemnity(frm) {
		if (!frm.doc.custom_indemnity) {
			_populate_indemnity_payables(frm, null);
			return;
		}
		frappe.db.get_doc("Indemnity", frm.doc.custom_indemnity).then((indemnity) => {
			_populate_indemnity_payables(frm, indemnity);
		});
	},
});

frappe.ui.form.on("Full and Final Outstanding Statement", {
	reference_document(frm, cdt, cdn) {
		const child = locals[cdt][cdn];
		if (child.reference_document_type === "Indemnity" && child.reference_document) {
			frappe.db
				.get_doc("Indemnity", child.reference_document)
				.then((indemnity) => {
					if (!indemnity) return;
					frappe.model.set_value(cdt, cdn, "account", indemnity.payable_account || "");
					if (child.component === "Indemnity Reward (Before Cut-Off Date)") {
						frappe.model.set_value(cdt, cdn, "amount", flt(indemnity.indemnity_before, 3));
					} else if (child.component === "Indemnity Reward (After Cut-Off Date)") {
						frappe.model.set_value(cdt, cdn, "amount", flt(indemnity.indemnity_after, 3));
					} else {
						frappe.model.set_value(cdt, cdn, "amount", flt(indemnity.amount, 3));
					}
				});
		}
	},
});

function _generate_or_update_indemnity(frm) {
	if (!frm.doc.employee) {
		frappe.msgprint({
			title: __("Missing Employee"),
			message: __("Please select an Employee before generating Indemnity."),
			indicator: "orange",
		});
		return;
	}

	if (!frm.doc.date_of_joining || !frm.doc.relieving_date) {
		frappe.msgprint({
			title: __("Missing Dates"),
			message: __("Please ensure Date of Joining and Relieving Date are set."),
			indicator: "orange",
		});
		return;
	}

	const execute_call = () => {
		const action_label = frm.doc.custom_indemnity ? __("Updating Indemnity...") : __("Generating Indemnity...");
		frappe.call({
			method: "beveren_health.beveren_health.customize.full_and_final_settlement.create_or_update_indemnity",
			args: { fnf: frm.doc.name },
			freeze: true,
			freeze_message: action_label,
			callback(r) {
				if (!r.message) return;
				frm.reload_doc().then(() => {
					frappe.show_alert({
						message: __("Indemnity {0} processed successfully", [
							`<a href="/app/indemnity/${encodeURIComponent(
								r.message
							)}">${frappe.utils.escape_html(r.message)}</a>`,
						]),
						indicator: "green",
					});
				});
			},
		});
	};

	if (frm.is_new() || frm.is_dirty()) {
		frm.save().then(() => {
			execute_call();
		});
	} else {
		execute_call();
	}
}

function _override_reference_queries(frm, type) {
	frm.set_query("reference_document_type", type, function () {
		return {
			query: "beveren_health.beveren_health.customize.full_and_final_settlement.get_reference_doctypes",
		};
	});
}

function _compute_total_experience_ui(frm) {
	if (!frm.doc.date_of_joining || !frm.doc.relieving_date) {
		frm.set_value("custom_total_experience", "");
		return;
	}
	let start = moment(frm.doc.date_of_joining);
	let end = moment(frm.doc.relieving_date).add(1, "days");
	if (end.isBefore(start)) {
		frm.set_value("custom_total_experience", "");
		return;
	}
	let years = end.diff(start, "years");
	start.add(years, "years");
	let months = end.diff(start, "months");
	start.add(months, "months");
	let days = end.diff(start, "days");

	frm.set_value(
		"custom_total_experience",
		`${years} years ${months} months and ${days} days`
	);
}

function _update_ir_base_and_reward_ui(frm) {
	const consider_full = frm.doc.custom_consider_full_salary || frm.doc.custom_consider_full_salary_after_cutoff_date;
	const ir_base = consider_full ? frm.doc.custom_base_salary : frm.doc.custom_basic_salary;
	if (ir_base !== undefined && ir_base !== null) {
		frm.set_value("custom_ir_base", flt(ir_base, 3));
	}
}

function _populate_indemnity_payables(frm, indemnity) {
	const LABEL_BEFORE = "Indemnity Reward (Before Cut-Off Date)";
	const LABEL_AFTER = "Indemnity Reward (After Cut-Off Date)";

	function upsert_or_remove(label, amount, account) {
		let row = (frm.doc.payables || []).find((r) => r.component === label);
		if (indemnity && flt(amount, 3) > 0) {
			if (!row) {
				row = frm.add_child("payables");
			}
			row.component = label;
			row.amount = flt(amount, 3);
			row.account = account || "";
			row.reference_document_type = "Indemnity";
			row.reference_document = indemnity.name;
			row.status = row.status || "Unsettled";
			row.paid_via_salary_slip = indemnity.pay_via_salary_slip ? 1 : 0;
		} else if (row) {
			frappe.model.clear_doc(row.doctype, row.name);
		}
	}

	if (indemnity) {
		const consider_full = frm.doc.custom_consider_full_salary || frm.doc.custom_consider_full_salary_after_cutoff_date;
		frm.set_value("custom_indemnity_reward", flt(indemnity.amount, 3));
		frm.set_value("custom_ir_base", flt(consider_full ? indemnity.base_salary : indemnity.basic_salary, 3));

		upsert_or_remove(LABEL_BEFORE, indemnity.indemnity_before, indemnity.payable_account);
		upsert_or_remove(LABEL_AFTER, indemnity.indemnity_after, indemnity.payable_account);
	} else {
		frm.set_value("custom_indemnity_reward", 0);
		frm.set_value("custom_ir_base", 0);

		upsert_or_remove(LABEL_BEFORE, 0, "");
		upsert_or_remove(LABEL_AFTER, 0, "");
	}

	frm.refresh_field("payables");
	if (frm.events.calculate_total_payable_amt) {
		frm.events.calculate_total_payable_amt(frm);
	}
}
