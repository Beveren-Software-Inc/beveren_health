frappe.ui.form.on('Employee Checkin', {
    refresh(frm) {
        if (frm.doc.attendance) {
            frm.set_df_property('employee', 'read_only', 1);
            frm.set_df_property('log_type', 'read_only', 1);
        }
    }
});