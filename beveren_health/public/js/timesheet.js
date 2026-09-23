// Copyright (c) 2026, Beveren Software and contributors
// For license information, please see license.txt

// Timesheet: the Patient picked on the form (custom_patient) is the patient the
// whole sheet is logged against, so every time log row (Timesheet Detail) has
// to carry it too:
//   Timesheet        -> custom_patient / custom_patient_name
//   Timesheet Detail -> custom_patient / custom_patient_name (time_logs)
// custom_patient_name is fetched from Patient.patient_name by Frappe itself
// (fetch_from), so only custom_patient is set here.

frappe.ui.form.on("Timesheet", {
	onload(frm) {
		// Remember the patient the rows were last synced with, so that a header
		// change only rewrites rows that were not given a patient of their own.
		frm.__previous_custom_patient = frm.doc.custom_patient || "";
	},

	refresh(frm) {
		if (frm.__previous_custom_patient === undefined) {
			frm.__previous_custom_patient = frm.doc.custom_patient || "";
		}
	},

	custom_patient(frm) {
		const previous = frm.__previous_custom_patient || "";
		frm.__previous_custom_patient = frm.doc.custom_patient || "";
		sync_time_logs_patient(frm, previous);
	},

	time_logs_add(frm, cdt, cdn) {
		if (frm.doc.docstatus !== 0 || !frm.doc.custom_patient) {
			return;
		}
		set_row_patient(cdt, cdn, frm.doc.custom_patient);
	},
});

/**
 * Push the header Patient down to the time log rows.
 *
 * A row is only touched when it is still empty or when it still holds the
 * patient that was last pushed from the header, so a patient deliberately
 * picked on a single row is preserved. Clearing the header patient clears the
 * rows that were auto-filled from it.
 */
function sync_time_logs_patient(frm, previous_patient) {
	if (frm.doc.docstatus !== 0) {
		return;
	}

	const rows = frm.doc.time_logs || [];
	if (!rows.length) {
		return;
	}

	const patient = frm.doc.custom_patient || "";

	rows.forEach((row) => {
		const was_synced = !row.custom_patient || row.custom_patient === previous_patient;
		if (patient && was_synced && row.custom_patient !== patient) {
			set_row_patient(row.doctype, row.name, patient);
		} else if (!patient && previous_patient && row.custom_patient === previous_patient) {
			set_row_patient(row.doctype, row.name, "");
		}
	});
}

function set_row_patient(cdt, cdn, patient) {
	if (!frappe.meta.has_field(cdt, "custom_patient")) {
		return;
	}
	frappe.model.set_value(cdt, cdn, "custom_patient", patient);
}
