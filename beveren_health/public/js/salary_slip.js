frappe.ui.form.on("Salary Slip", {
	onload(frm) {
		frm.trigger("calculate_lwp_absents");
	},
	refresh(frm) {
		frm.trigger("calculate_lwp_absents");
		add_close_observation_button(frm);
	},
	payroll_frequency(frm) {
		frm.trigger("calculate_lwp_absents");
	},
	start_date(frm) {
		frm.trigger("calculate_lwp_absents");
	},
	end_date(frm) {
		frm.trigger("calculate_lwp_absents");
	},
});

function calculate_lwp_absents(frm) {
	if (!frm.doc.start_date || !frm.doc.end_date || !frm.doc.payroll_frequency) return;

	frappe.call({
		method: "beveren_health.beveren_health.customize.salary_slip.get_lwp_absents",
		args: {
			employee: frm.doc.employee,
			start_date: frm.doc.start_date,
			end_date: frm.doc.end_date,
		},
		callback: function (r) {
			if (!r.message) return;
			frm.set_value("total_working_days", 30);
			frm.set_value("leave_without_pay", r.message.total_lwp || 0.0);
			frm.set_value("absent_days", r.message.total_absent || 0.0);
			frm.set_value("payment_days", 30);
			frm.refresh_field("leave_without_pay");
			frm.refresh_field("absent_days");
		},
	});
}

function add_close_observation_button(frm) {
	if (frm.doc.docstatus !== 0) {
		return;
	}
	frm.add_custom_button(__("Calculate Close Observation"), () => {
		const run = () => {
			frappe.call({
				method: "beveren_health.beveren_health.customize.salary_slip.calculate_close_observation",
				args: { salary_slip: frm.doc.name },
				freeze: true,
				freeze_message: __("Calculating Close Observation"),
				callback() {
					frm.reload_doc();
				},
			});
		};
		if (frm.is_new() || frm.is_dirty()) {
			frm.save().then(run);
		} else {
			run();
		}
	});
}
