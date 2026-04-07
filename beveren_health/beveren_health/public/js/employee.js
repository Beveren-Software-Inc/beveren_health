frappe.ui.form.on("Employee", {
    refresh: function(frm) {
        if (frm.doc.relieving_date && frm.doc.date_of_joining) {
            let days = frappe.datetime.get_diff(
                frm.doc.relieving_date,
                frm.doc.date_of_joining
            );

            let years = Math.floor(days / 365);
            frm.set_value("custom_years_of_service", years);
        }
    },
    relieving_date: function(frm) {
        if (frm.doc.relieving_date && frm.doc.date_of_joining) {
            let days = frappe.datetime.get_diff(
                frm.doc.relieving_date,
                frm.doc.date_of_joining
            );

            let years = Math.floor(days / 365);
            frm.set_value("custom_years_of_service", years);
        }
    }
});
