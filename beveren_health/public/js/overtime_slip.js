frappe.ui.form.on("Overtime Slip", {
    onload: function(frm) {
        if (frm.is_new()) {
            frm.set_value('custom_total_over_time_duration', '');
            frm.set_value('total_overtime_duration', '');
        }
    },
    refresh(frm) {
        frm.set_df_property('overtime_details', 'reqd', 0);
        document.querySelectorAll(".btn-new").forEach((el) => {
            if (el.getAttribute("data-doctype") == "Additional Salary") {
                el.style.display = "none";
            }
        });
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