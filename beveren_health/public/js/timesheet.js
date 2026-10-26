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
		// A save reloads the form. Do not start another costing preview from
		// here: writing those amounts back marks a saved timesheet Not Saved.
		clearTimeout(frm.__close_observation_timer);
		update_total_days(frm);
		show_close_observation_calculation(frm);
	},

	custom_patient(frm) {
		const previous = frm.__previous_custom_patient || "";
		frm.__previous_custom_patient = frm.doc.custom_patient || "";
		sync_time_logs_patient(frm, previous);
	},

	employee(frm) {
		schedule_close_observation_cost(frm);
	},

	custom_allow_food_allowance_on_close_observation(frm) {
		schedule_close_observation_cost(frm);
	},

	time_logs_add(frm, cdt, cdn) {
		if (frm.doc.docstatus !== 0 || !frm.doc.custom_patient) {
			return;
		}
		set_row_patient(cdt, cdn, frm.doc.custom_patient);
	},

	time_logs_remove(frm) {
		update_total_days(frm);
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

function update_total_days(frm) {
	if (!frm.doc || !frappe.meta.has_field(frm.doc.doctype, "custom_total_days")) {
		return;
	}
	const total = count_total_days(frm);
	if (flt(frm.doc.custom_total_days, 2) === total) {
		return;
	}
	if (frm.doc.docstatus !== 0 || (!frm.is_new() && !frm.is_dirty())) {
		frm.doc.custom_total_days = total;
		frm.refresh_field("custom_total_days");
		return;
	}
	frm.set_value("custom_total_days", total);
}

function count_total_days(frm) {
	// Every calendar day a time log touches counts, the last day included:
	// 21 Sep 00:00 -> 20 Oct 00:00 is 30 days, not 29.
	const days = new Set();
	(frm.doc.time_logs || []).forEach((row) => {
		if (!row.from_time) {
			return;
		}
		const from = frappe.datetime.str_to_obj(row.from_time);
		const to = row.to_time ? frappe.datetime.str_to_obj(row.to_time) : from;
		const start = new Date(from.getFullYear(), from.getMonth(), from.getDate());
		const end = new Date(to.getFullYear(), to.getMonth(), to.getDate());
		const first = start <= end ? start : end;
		const last = start <= end ? end : start;
		for (let day = new Date(first); day <= last; day.setDate(day.getDate() + 1)) {
			days.add(frappe.datetime.obj_to_str(day));
		}
	});
	if (days.size) {
		return days.size;
	}
	// No From Time / To Time on the rows: fall back to working hours / 24.
	let hours = flt(frm.doc.total_hours);
	if (!hours) {
		(frm.doc.time_logs || []).forEach((row) => {
			hours += flt(row.hours);
		});
	}
	return flt(hours / 24, 2);
}

// Close Observation is costed as one allowance per row, from the employee's
// salary structure, not as hours times a costing rate.
const close_observation_activity_cache = {};

frappe.ui.form.on("Timesheet Detail", {
	activity_type(frm) {
		schedule_close_observation_cost(frm);
	},
	from_time(frm) {
		update_total_days(frm);
		schedule_close_observation_cost(frm);
	},
	to_time(frm) {
		update_total_days(frm);
		schedule_close_observation_cost(frm);
	},
	hours(frm) {
		update_total_days(frm);
		schedule_close_observation_cost(frm);
	},
});

function schedule_close_observation_cost(frm) {
	if (frm.__close_observation_applying || frm.doc.docstatus !== 0) {
		return;
	}
	clearTimeout(frm.__close_observation_timer);
	frm.__close_observation_timer = setTimeout(() => {
		refresh_close_observation_cost(frm);
	}, 400);
}

async function refresh_close_observation_cost(frm) {
	if (!frm.doc.employee || frm.__close_observation_applying) {
		return;
	}
	const logs = frm.doc.time_logs || [];
	const observed = [];
	for (const row of logs) {
		if (await activity_is_close_observation(row.activity_type)) {
			observed.push(row);
		}
	}
	if (!observed.length) {
		return;
	}

	const time_logs = observed.map((row) => ({
		name: row.name,
		idx: row.idx,
		activity_type: row.activity_type,
		from_time: row.from_time,
		to_time: row.to_time,
		hours: row.hours,
		costing_rate: row.costing_rate,
		costing_amount: row.costing_amount,
	}));

	frappe.call({
		method: "beveren_health.beveren_health.customize.timesheet.preview_close_observation_costing",
		args: {
			employee: frm.doc.employee,
			time_logs,
			exchange_rate: frm.doc.exchange_rate || 1,
			currency: frm.doc.currency,
			food_applicable: cint(frm.doc.custom_allow_food_allowance_on_close_observation),
		},
		callback(r) {
			const result = r.message || {};
			show_close_observation_calculation(frm);
			// Save already stored the costing. Applying the preview again would
			// change the rate and flip the form back to Not Saved.
			if (frm.doc.docstatus !== 0 || (!frm.is_new() && !frm.is_dirty())) {
				return;
			}
			frm.__close_observation_applying = true;
			(result.rows || [])
				.filter((row) => row.applies)
				.forEach((row) => {
					const grid_row = (frm.doc.time_logs || []).find(
						(log) => log.name === row.name
					);
					if (!grid_row) {
						return;
					}
					set_row_if_changed(grid_row, "costing_rate", row.costing_rate);
					set_row_if_changed(grid_row, "costing_amount", row.costing_amount);
					set_row_if_changed(grid_row, "custom_daily_allowance", row.daily_allowance);
					set_row_if_changed(grid_row, "custom_food_allowance", row.food_allowance);
				});
			if (
				frappe.meta.has_field(frm.doc.doctype, "custom_close_observation_allowance") &&
				flt(frm.doc.custom_close_observation_allowance) !==
					flt(result.close_observation_allowance)
			) {
				frm.set_value(
					"custom_close_observation_allowance",
					result.close_observation_allowance || 0
				);
			}
			setTimeout(() => {
				frm.__close_observation_applying = false;
			}, 500);
		},
	});
}

function set_row_if_changed(row, field, value) {
	if (!frappe.meta.has_field(row.doctype, field)) {
		return;
	}
	if (flt(row[field]) === flt(value)) {
		return;
	}
	frappe.model.set_value(row.doctype, row.name, field, flt(value));
}

function show_close_observation_calculation(frm) {
	if (frm.set_intro) {
		frm.set_intro("");
	}
	if (frappe.meta.has_field(frm.doc.doctype, "custom_close_observation_calculation")) {
		frm.set_df_property("custom_close_observation_calculation", "hidden", 1);
	}
}

function activity_is_close_observation(activity_type) {
	if (!activity_type) {
		return Promise.resolve(false);
	}
	if (String(activity_type).trim().toLowerCase() === "close observation") {
		return Promise.resolve(true);
	}
	if (Object.prototype.hasOwnProperty.call(close_observation_activity_cache, activity_type)) {
		return Promise.resolve(close_observation_activity_cache[activity_type]);
	}
	return frappe.db
		.get_value("Activity Type", activity_type, "custom_is_close_observation")
		.then((r) => {
			const flagged = !!(r && r.message && cint(r.message.custom_is_close_observation));
			close_observation_activity_cache[activity_type] = flagged;
			return flagged;
		})
		.catch(() => {
			close_observation_activity_cache[activity_type] = false;
			return false;
		});
}
