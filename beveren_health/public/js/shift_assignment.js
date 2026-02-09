frappe.ui.form.on('Shift Assignment', {
    setup(frm) {
        frm.set_query('shift_type', function () {
            let filters = {};
            if (frm.doc.custom_standard_working_hours) {
                filters.custom_standard_working_hours = frm.custom_doc.standard_working_hours;
            }
            if (frm.doc.custom_weekly_off) {
                filters.custom_weekly_off = frm.doc.custom_weekly_off;
            }
            return { filters };
        });
    },
    custom_standard_working_hours(frm) {
        frm.set_value('shift_type', null);
    },
    custom_weekly_off(frm) {
        frm.set_value('shift_type', null);
    }
});