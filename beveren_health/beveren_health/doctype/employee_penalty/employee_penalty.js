frappe.ui.form.on('Employee Penalty', {
    onload(frm) {
        calculate_days(frm);
    },
    refresh(frm) {
        calculate_days(frm);
    },
    from_date(frm) {
        calculate_days(frm);
    },
    to_date(frm) {
        calculate_days(frm);
    }
});

function calculate_days(frm) {
    if (frm.doc.from_date && frm.doc.to_date) {
        let days = frappe.datetime.get_day_diff(
            frm.doc.to_date,
            frm.doc.from_date
        ) + 1;

        frm.set_value("no_of_days", days);
    }
}

