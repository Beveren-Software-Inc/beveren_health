frappe.ui.form.on('Holiday List', {
    refresh(frm) {
        if (!frm.is_new()) {
            frm.set_df_property('country', 'read_only', 1);
            frm.set_df_property('weekly_off', 'read_only', 1);
        }
    }
});
