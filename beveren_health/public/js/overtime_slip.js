frappe.ui.form.on("Overtime Slip", {
    refresh(frm) {
        frm.set_df_property('overtime_details', 'reqd', 0);
        document.querySelectorAll(".btn-new").forEach((el) => {
            if (el.getAttribute("data-doctype") == "Additional Salary") {
                el.style.display = "none";
            }
        });
        // if(frm.doc.start_date && frm.doc.end_date && frm.doc.employee) {
        //     frappe.call({
        //         method: "beveren_health.beveren_health.customize.overtime_slip.fetch_less_time_total",
        //         args: {
        //             employee: frm.doc.employee,
        //             start_date: frm.doc.start_date,
        //             end_date: frm.doc.end_date
        //         },
        //         callback: function(r) {
        //             if(r.message) {
        //                 frm.set_value("custom_reference_document", r.message[0]);
        //                 frm.set_value("custom_total_less_time_duration", r.message[1]);
        //             }
        //         }
        //     });
        // }
    },
});