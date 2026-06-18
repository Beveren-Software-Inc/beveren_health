frappe.ui.form.on("Full and Final Statement", {
    refresh(frm) {
        // Override HRMS set_query to restrict reference_document_type to
        // HR/Payroll/Loan Management modules + Indemnity only from Beveren Health
        _override_reference_queries(frm, "payables");
        _override_reference_queries(frm, "receivables");

        // Restrict Indemnity link to the same employee only
        frm.set_query("custom_indemnity", function () {
            return {
                filters: {
                    employee: frm.doc.employee,
                    docstatus: ["!=", 2],
                },
            };
        });
    },

    custom_indemnity(frm) {
        if (!frm.doc.custom_indemnity) return;
        frappe.db.get_doc("Indemnity", frm.doc.custom_indemnity).then(indemnity => {
            _populate_indemnity_payables(frm, indemnity);
        });
    },
});

frappe.ui.form.on("Full and Final Outstanding Statement", {
    reference_document(frm, cdt, cdn) {
        const child = locals[cdt][cdn];
        if (child.reference_document_type === "Indemnity" && child.reference_document) {
            frappe.db.get_value(
                "Indemnity",
                child.reference_document,
                ["payable_account", "amount"]
            ).then(r => {
                if (r.message) {
                    frappe.model.set_value(cdt, cdn, "account", r.message.payable_account || "");
                    frappe.model.set_value(cdt, cdn, "amount", r.message.amount || 0);
                }
            });
        }
    },
});

function _override_reference_queries(frm, type) {
    frm.set_query("reference_document_type", type, function () {
        return {
            query: "beveren_health.beveren_health.customize.full_and_final_settlement.get_reference_doctypes",
        };
    });
}

function _populate_indemnity_payables(frm, indemnity) {
    const LABEL_BEFORE = "Indemnity Reward (Before Cut-Off Date)";
    const LABEL_AFTER = "Indemnity Reward (After Cut-Off Date)";

    function upsert(label, amount, account) {
        let row = (frm.doc.payables || []).find(r => r.component === label);
        if (!row) {
            row = frm.add_child("payables");
        }
        // Set directly on the row object to avoid Dynamic Link clear-on-change
        // and event cascade that corrupts the BEFORE row when AFTER is processed
        row.component = label;
        row.amount = flt(amount, 3);
        row.account = account || "";
        row.reference_document_type = "Indemnity";
        row.reference_document = indemnity.name;
        row.status = row.status || "Unsettled";
        row.paid_via_salary_slip = indemnity.pay_via_salary_slip ? 1 : 0;
    }

    if (flt(indemnity.indemnity_before)) {
        upsert(LABEL_BEFORE, indemnity.indemnity_before, indemnity.payable_account);
    }
    if (flt(indemnity.indemnity_after)) {
        upsert(LABEL_AFTER, indemnity.indemnity_after, indemnity.payable_account);
    }

    frm.refresh_field("payables");
}
