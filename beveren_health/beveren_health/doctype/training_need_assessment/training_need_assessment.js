// Copyright (c) 2026, Beveren Software and contributors
// For license information, please see license.txt

frappe.ui.form.on("Training Need Assessment", {
	onload(frm) {
        frm.call({
            method: "get_instructions",
            callback: function(r) {
                frm.set_value("rating_instruction", r.message[0]);
                frm.set_value("text1", r.message[1])
            }
	    });
        frm.call({
            method: "frappe.client.get_list",
            args: {
                doctype: "TNA Template",
                fields: ["title", "description"],
                limit_page_length: 1000
            },
            callback: function(r) {
                frm.clear_table("assessments");
                r.message.forEach(row => {
                let child = frm.add_child("assessments");
                child.title = row.title;
                child.description = row.description
            });
            frm.refresh_field("assessments");}
	    });
        frm.fields_dict['assessments'].grid.get_field('title').get_query = function(doc, cdt, cdn) {
            const selected_title = frm.doc.assessments
                .map(r => r.title)
                .filter(e => e);
            return {
                filters: [
                    ['name', 'not in', selected_title]
                ]
            };
        };
    },
    refresh(frm) {
        frm.fields_dict['assessments'].grid.get_field('title').get_query(frm.doc);
    }
});


