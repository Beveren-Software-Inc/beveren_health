frappe.ui.form.on("Employee Visa Renewal Consent", {
	refresh(frm) {
		frm.set_query("hod", function () {
			return {
				filters: {
					status: "Active",
				},
			};
		});
	},

	renewal_decision(frm) {
		if (frm.doc.renewal_decision === "Not Renew") {
			frm.set_value("renewal_period", null);
		}
	},
});
