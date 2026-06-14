frappe.ui.form.on("Appraisal", {
	appraisal_template(frm) {
		if (!frm.doc.appraisal_template) return;
		// HRMS already calls set_kras_and_rating_criteria for appraisal_kra.
		// Wait for that call to complete, then refresh goals and self_ratings too.
		setTimeout(() => {
			frm.refresh_field("goals");
			frm.refresh_field("self_ratings");
		}, 800);
	},
});
