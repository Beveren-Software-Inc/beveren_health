// visit_reconcile_button_serene.js
// ---------------------------------------------------------------------------
// "Reconcile Visits" buttons for the serene site.
//
// INSTALL (as three Client Scripts, same content is fine - every block below
// is idempotent, so loading it twice cannot duplicate a button):
//   Patient        / Form
//   Patient Visit  / Form
//   Patient Visit  / List
//
// Backend: beveren_health/visits/reconcile.py
//   -> beveren_health.visits.reconcile.visit_recon_counts
//   -> beveren_health.visits.reconcile.visit_recon_import
//   -> beveren_health.visits.reconcile.visit_recon_import_all
//
// Matching is by Oracle VISIT_NUM == Patient Visit.case_no. Nothing is ever
// deleted or merged; Oracle-only rows are added, ERPNext-only rows reported.
// ---------------------------------------------------------------------------

frappe.provide("frappe.visit_recon");

(function () {
	const R = frappe.visit_recon;

	// Patient field holding the Oracle file number (= Patient docname on serene)
	const PATIENT_FILE_FIELD = "file_no";
	// dotted path of beveren_health/visits/reconcile.py
	const METHOD_PREFIX = "beveren_health.visits.reconcile.";
	const VISIT_DOCTYPE = "Patient Visit";

	const M = (name) => METHOD_PREFIX + name;

	if (!R.__ready) {
		R.__ready = 1;

		R.file_no = function (frm) {
			if (frm.doctype === "Patient") {
				return Promise.resolve(frm.doc[PATIENT_FILE_FIELD]);
			}
			const p = frm.doc.patient || frm.doc.file_number;
			if (!p) return Promise.resolve(null);
			return frappe.db
				.get_value("Patient", p, PATIENT_FILE_FIELD)
				.then((r) => (r.message || {})[PATIENT_FILE_FIELD] || p);
		};

		R.report = function (file_no) {
			frappe.dom.freeze(__("Checking Oracle against ERPNext..."));
			return frappe
				.call({ method: M("visit_recon_counts"), args: { patient: file_no } })
				.then((r) => {
					frappe.dom.unfreeze();
					return r.message || {};
				})
				.catch(() => frappe.dom.unfreeze());
		};

		R.run = function (frm) {
			Promise.resolve(R.file_no(frm)).then((file_no) => {
				if (!file_no) {
					frappe.msgprint(__("No Oracle file number on this patient."));
					return;
				}
				R.report(file_no).then((m) => {
					if (!m || m.oracle_only === undefined) return;

					const missing = m.oracle_only;
					let lines = [
						__("Patient file no: {0}", [file_no]),
						__("Matched by Oracle id (case_no): {0}", [m.matched_by_id]),
						__("Matched by patient + date: {0}", [m.matched_by_score]),
						__("In Oracle, missing in ERPNext: {0}", [missing]),
						__("In ERPNext, not in Oracle: {0}", [m.erp_only]),
					];
					if (m.id_conflicts) {
						lines.push(
							__(
								"Visit numbers stored on a DIFFERENT patient (counted as missing, " +
									"must be fixed by hand): {0}",
								[m.id_conflicts]
							)
						);
					}
					lines = lines.join("<br>");

					if (!missing) {
						frappe.msgprint({
							title: __("Visits are in sync"),
							message: lines,
							indicator: "green",
						});
						return;
					}

					frappe.confirm(
						__(
							"{0} Oracle visit(s) are missing in ERPNext.<br><br>{1}<br><br>" +
								"Import them now? (visits whose patient-day already has an " +
								"ERPNext visit are skipped, never duplicated)",
							[missing, lines]
						),
						() => {
							frappe.dom.freeze(__("Importing visits..."));
							frappe
								.call({ method: M("visit_recon_import"), args: { patient: file_no } })
								.then((r) => {
									frappe.dom.unfreeze();
									const res = r.message || {};
									const bits = [
										lines,
										"<br><b>" + __("Imported: {0}", [res.imported || 0]) + "</b>",
									];
									if (res.skipped) bits.push(__("Already present: {0}", [res.skipped]));
									if (res.skipped_same_day)
										bits.push(
											__("Skipped, another visit exists that day: {0}", [
												res.skipped_same_day,
											])
										);
									if (res.skipped_no_patient)
										bits.push(
											__("Skipped, patient missing in ERPNext: {0}", [
												res.skipped_no_patient,
											])
										);
									if (res.skipped_id_conflict)
										bits.push(
											__(
												"Not imported, visit number belongs to another patient: {0}",
												[res.skipped_id_conflict]
											)
										);
									if (res.failed) bits.push(__("Failed: {0}", [res.failed]));
									frappe.msgprint({
										title: __("Visit reconcile finished"),
										message: bits.join("<br>"),
										indicator: res.failed ? "orange" : "green",
									});
									frm.reload_doc && frm.reload_doc();
								})
								.catch(() => frappe.dom.unfreeze());
						}
					);
				});
			});
		};

		R.all = function () {
			frappe.confirm(
				__(
					"Check every patient in Oracle and import all missing visits? " +
						"This runs as a background job and can take a few minutes."
				),
				() => {
					frappe.call({ method: M("visit_recon_import_all") }).then(() => {
						frappe.msgprint(
							__("Reconcile queued as a background job. Progress: RQ Job / Error Log.")
						);
					});
				}
			);
		};
	}

	// --- Patient form ------------------------------------------------------
	if (!R.__bound_patient) {
		R.__bound_patient = 1;
		frappe.ui.form.on("Patient", {
			refresh(frm) {
				if (frm.is_new()) return;
				frm.add_custom_button(__("Reconcile Visits"), () => R.run(frm));
			},
		});
	}

	// --- Patient Visit form ------------------------------------------------
	if (!R.__bound_visit) {
		R.__bound_visit = 1;
		frappe.ui.form.on(VISIT_DOCTYPE, {
			refresh(frm) {
				if (frm.is_new()) return;
				frm.add_custom_button(__("Reconcile Visits"), () => R.run(frm));
			},
		});
	}

	// --- Patient Visit list ------------------------------------------------
	if (!R.__bound_list) {
		R.__bound_list = 1;
		frappe.listview_settings[VISIT_DOCTYPE] = frappe.listview_settings[VISIT_DOCTYPE] || {};
		const _onload = frappe.listview_settings[VISIT_DOCTYPE].onload;
		frappe.listview_settings[VISIT_DOCTYPE].onload = function (listview) {
			if (_onload) _onload.call(this, listview);
			listview.page.add_inner_button(__("Reconcile All Visits"), () => R.all());
		};
	}
})();
