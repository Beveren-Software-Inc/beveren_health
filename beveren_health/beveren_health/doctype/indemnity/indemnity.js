frappe.ui.form.on("Indemnity", {
    onload(frm) {
        if (frm.is_new()) {
            frappe.db.get_single_value("HR Settings", "custom_indemnity_expense_account").then(v => {
                if (v && !frm.doc.expense_account) frm.set_value("expense_account", v);
            });
            frappe.db.get_single_value("HR Settings", "custom_indemnity_payable_account").then(v => {
                if (v && !frm.doc.payable_account) frm.set_value("payable_account", v);
            });
        }
    },
    pay_via_salary_slip(frm) {
        frm.refresh_fields(["salary_component", "payroll_date", "expense_account", "payable_account"]);
    },
});
