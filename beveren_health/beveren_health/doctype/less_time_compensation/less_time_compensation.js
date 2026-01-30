frappe.ui.form.on('Less Time Compensation', {
    onload: function(frm) {
        frm.set_query("employee", function() {
            return {
                filters: {
                    "custom_is_less_time_deductible_": 0
                }
            };
        });
        set_period_dates(frm);
    },
    posting_date: function(frm) {
        frm.clear_table("less_time_compensation_details");
        frm.refresh_field("less_time_compensation_details");
        set_period_dates(frm);
    },
    compensation_frequency: function(frm) {
        frm.clear_table("less_time_compensation_details");
        frm.refresh_field("less_time_compensation_details");
        set_period_dates(frm);
    },
    refresh: function(frm) {
        if (frm.doc.docstatus == 0) {
            frm.add_custom_button('Fetch LT-OT Data', function() {
                fetch_compensation_data(frm);
            });
        }
    }
});

function set_period_dates(frm) {
    if (!frm.doc.posting_date || !frm.doc.compensation_frequency) {
        return;
    }

    const posting_date = frappe.datetime.str_to_obj(frm.doc.posting_date);
    const year = posting_date.getFullYear();
    const month = posting_date.getMonth() + 1;

    let from_date, to_date;

    switch (frm.doc.compensation_frequency) {
        case "Monthly":
            from_date = frappe.datetime.month_start(frm.doc.posting_date);
            to_date = frappe.datetime.month_end(frm.doc.posting_date);
            break;

        case "Bi-Monthly":
            let start_month = month % 2 === 0 ? month - 1 : month;
            let start_date = new Date(year, start_month - 1, 1);
            let end_date = new Date(year, start_month + 1, 0);

            from_date = frappe.datetime.obj_to_str(start_date);
            to_date = frappe.datetime.obj_to_str(end_date);
            break;

        case "Quarterly":
            if (month <= 3) {
                from_date = `${year}-01-01`;
                to_date = `${year}-03-31`;
            } else if (month <= 6) {
                from_date = `${year}-04-01`;
                to_date = `${year}-06-30`;
            } else if (month <= 9) {
                from_date = `${year}-07-01`;
                to_date = `${year}-09-30`;
            } else {
                from_date = `${year}-10-01`;
                to_date = `${year}-12-31`;
            }
            break;

        case "Half-Yearly":
            if (month <= 6) {
                from_date = `${year}-01-01`;
                to_date = `${year}-06-30`;
            } else {
                from_date = `${year}-07-01`;
                to_date = `${year}-12-31`;
            }
            break;

        case "Yearly":
            from_date = `${year}-01-01`;
            to_date = `${year}-12-31`;
            break;

        default:
            return;
    }

    frm.set_value('from_date', from_date);
    frm.set_value('to_date', to_date);
}


function fetch_compensation_data(frm) {
    if (!frm.doc.from_date || !frm.doc.to_date || !frm.doc.employee) {
        frappe.msgprint("Please select Employee, From Date and To Date first");
        return;
    }

    frappe.call({
        method: "beveren_health.beveren_health.doctype.less_time_compensation.less_time_compensation.get_compensation_data",
        args: {
            from_date: frm.doc.from_date,
            to_date: frm.doc.to_date,
            employee: frm.doc.employee
        },
        callback: function(r) {
    if (!r.message || !r.message.length) return;
    frm.clear_table("less_time_compensation_details");
    r.message.forEach(row => {
        let child = frm.add_child("less_time_compensation_details");
        child.reference_doctype = row.reference_doctype; 
        child.reference_name = row.reference_name;
        child.start_date = row.from_date;
        child.end_date = row.to_date;
        child.less_time_duration = row.less_time_duration;
        child.overtime_duration = row.overtime_duration;
    });

    frm.refresh_field("less_time_compensation_details");
}


    });
}