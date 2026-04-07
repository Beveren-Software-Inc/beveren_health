// Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Less Time Entry", {
	refresh: async (frm) => {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Fetch Less Time Details"), () => {
				if (!frm.doc.employee || !frm.doc.posting_date || !frm.doc.company) {
					frappe.msgprint({
						title: __("Missing Fields"),
						message: __(
							"Please fill in Employee, Posting Date, and Company before fetching lesstime details.",
						),
						indicator: "orange",
					});
				} else {
					frm.events.get_emp_details_and_lesstime_duration(frm);
				}
			});
		}
        frm.set_df_property('overtime_details', 'reqd', 0);
        document.querySelectorAll(".btn-new").forEach((el) => {
            if (el.getAttribute("data-doctype") == "Additional Salary") {
                el.style.display = "none";
            }
        });
	},

	employee(frm) {
		frm.events.set_frequency_and_dates(frm);
	},
	posting_date(frm) {
		frm.events.set_frequency_and_dates(frm);
	},
	set_frequency_and_dates: function (frm) {
		if (frm.doc.employee && frm.doc.posting_date) {
			return frappe.call({
				method: "get_frequency_and_dates",
				doc: frm.doc,
				callback: function () {
					frm.refresh();
				},
			});
		}
	},
	get_emp_details_and_lesstime_duration: function (frm) {
		if (frm.doc.employee) {
			return frappe.call({
				method: "get_emp_and_lesstime_details",
				doc: frm.doc,
				callback: function () {
					frm.refresh();
				},
			});
		}
	},
	start_date: function(frm) {
        if (frm.doc.start_date) {
            let end_date = frappe.datetime.add_days(
                frappe.datetime.add_months(frm.doc.start_date, 1),
                -1
            );
            frm.set_value('end_date', end_date);
        }
    },

    end_date: function(frm) {
        if (frm.doc.end_date) {
            let start_date = frappe.datetime.add_days(
                frappe.datetime.add_months(frm.doc.end_date, -1),
                1
            );
            frm.set_value('start_date', start_date);
        }
    }
});
