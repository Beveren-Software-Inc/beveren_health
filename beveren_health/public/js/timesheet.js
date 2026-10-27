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
		remember_payroll_period(frm);
	},

	refresh(frm) {
		if (frm.__previous_custom_patient === undefined) {
			frm.__previous_custom_patient = frm.doc.custom_patient || "";
		}
		// A save reloads the form. Do not start another costing preview from
		// here: writing those amounts back marks a saved timesheet Not Saved.
		clearTimeout(frm.__close_observation_timer);
		remember_payroll_period(frm);
		sync_payroll_period(frm);
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

	// Typing a payroll date means the user is taking over the period: the
	// automatic 21st -> 20th dates stop following the time logs from then on.
	custom_payroll_start_date(frm) {
		schedule_close_observation_cost(frm);
	},

	custom_payroll_end_date(frm) {
		schedule_close_observation_cost(frm);
	},

	time_logs_add(frm, cdt, cdn) {
		if (frm.doc.docstatus === 0 && frm.doc.custom_patient) {
			set_row_patient(cdt, cdn, frm.doc.custom_patient);
		}
		sync_payroll_period(frm);
	},

	time_logs_remove(frm) {
		update_total_days(frm);
		sync_payroll_period(frm);
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

// Payroll normally runs from the 21st of a month to the 20th of the next. The
// payroll dates on a Timesheet follow the sheet's first From Time: a time log
// that starts on 26 Jul puts the sheet in the 21 Jul -> 20 Aug period, and
// moving that From Time to another month moves the dates with it. The dates are
// what the Salary Slip divides the close observation allowance by, so a period
// that spans two calendar months (21 Sep -> 20 Oct) is costed as one period,
// not two months.
//
// The automatic dates only follow the time logs while they are still the
// standard 21st -> 20th period. Once the user types their own payroll start or
// end date, their dates are kept as they are.
const PAYROLL_PERIOD_START_DAY = 21;
const PAYROLL_PERIOD_END_DAY = 20;

/**
 * Fill the payroll dates from the earliest From Time.
 *
 * A date is written when it is empty, or when it still holds the value this
 * function last wrote for the same period. A date the user typed is left alone,
 * and the missing date is filled in around it.
 */
function sync_payroll_period(frm) {
	if (!frm.doc || frm.doc.docstatus !== 0) {
		return;
	}
	if (
		!frappe.meta.has_field(frm.doc.doctype, "custom_payroll_start_date") ||
		!frappe.meta.has_field(frm.doc.doctype, "custom_payroll_end_date")
	) {
		return;
	}
	const on_date = payroll_period_source_date(frm);
	if (!on_date) {
		return;
	}
	const period = payroll_period_for_date(on_date);
	const auto_start = frappe.datetime.obj_to_str(period.start);
	const auto_end = frappe.datetime.obj_to_str(period.end);
	const start = frm.doc.custom_payroll_start_date || "";
	const end = frm.doc.custom_payroll_end_date || "";
	const auto = frm.__payroll_period_auto;
	const start_is_auto = !start || (!!auto && auto.start === start);
	const end_is_auto = !end || (!!auto && auto.end === end);
	if (!start_is_auto && !end_is_auto) {
		// The user has taken over the period: do not move either date.
		return;
	}
	if (start_is_auto) {
		set_payroll_period_date(frm, "custom_payroll_start_date", auto_start);
	}
	if (end_is_auto) {
		set_payroll_period_date(frm, "custom_payroll_end_date", auto_end);
	}
	// Only keep following the time logs while both dates are the standard ones.
	const final_start = start_is_auto ? auto_start : start;
	const final_end = end_is_auto ? auto_end : end;
	frm.__payroll_period_auto =
		final_start === auto_start && final_end === auto_end
			? { start: auto_start, end: auto_end }
			: undefined;
}

/**
 * Remember whether the dates on the loaded document are the standard period.
 * Only then may a From Time change move them again. A period the user typed
 * (or that does not match the current From Time) is left alone.
 */
function remember_payroll_period(frm) {
	if (!frm.doc || frm.doc.docstatus !== 0) {
		frm.__payroll_period_auto = undefined;
		return;
	}
	const start = frm.doc.custom_payroll_start_date || "";
	const end = frm.doc.custom_payroll_end_date || "";
	const on_date = payroll_period_source_date(frm);
	if (!start || !end || !on_date) {
		// Half filled (or empty) dates: sync_payroll_period completes them.
		frm.__payroll_period_auto = undefined;
		return;
	}
	const period = payroll_period_for_date(on_date);
	const auto_start = frappe.datetime.obj_to_str(period.start);
	const auto_end = frappe.datetime.obj_to_str(period.end);
	frm.__payroll_period_auto =
		start === auto_start && end === auto_end ? { start, end } : undefined;
}

/**
 * The date the payroll period is derived from: the earliest From Time in the
 * time logs, then the sheet Start Date, then today for a sheet being created.
 */
function payroll_period_source_date(frm) {
	let earliest = null;
	(frm.doc.time_logs || []).forEach((row) => {
		if (!row.from_time) {
			return;
		}
		const from_time = frappe.datetime.str_to_obj(row.from_time);
		if (!from_time || isNaN(from_time.getTime())) {
			return;
		}
		const day = new Date(from_time.getFullYear(), from_time.getMonth(), from_time.getDate());
		if (!earliest || day < earliest) {
			earliest = day;
		}
	});
	if (earliest) {
		return earliest;
	}
	if (frm.doc.start_date) {
		return frappe.datetime.str_to_obj(frm.doc.start_date);
	}
	if (frm.is_new()) {
		return frappe.datetime.str_to_obj(frappe.datetime.get_today());
	}
	return null;
}

function set_payroll_period_date(frm, field, value) {
	if ((frm.doc[field] || "") === value) {
		return;
	}
	frm.set_value(field, value);
}

function payroll_period_for_date(date) {
	if (date.getDate() >= PAYROLL_PERIOD_START_DAY) {
		return {
			start: new Date(date.getFullYear(), date.getMonth(), PAYROLL_PERIOD_START_DAY),
			end: new Date(date.getFullYear(), date.getMonth() + 1, PAYROLL_PERIOD_END_DAY),
		};
	}
	return {
		start: new Date(date.getFullYear(), date.getMonth() - 1, PAYROLL_PERIOD_START_DAY),
		end: new Date(date.getFullYear(), date.getMonth(), PAYROLL_PERIOD_END_DAY),
	};
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
		sync_payroll_period(frm);
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
			payroll_start_date: frm.doc.custom_payroll_start_date,
			payroll_end_date: frm.doc.custom_payroll_end_date,
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
