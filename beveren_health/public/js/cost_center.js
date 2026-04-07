frappe.ui.form.on('Cost Center', {
    onload: function(frm) {
        frm.set_query('custom_address', function() {
            return {
                filters: [
                    ['Dynamic Link', 'link_doctype', '=', 'Cost Center'],
                    ['Dynamic Link', 'link_name', '=', frm.doc.name]
                ]
            };
        });
    },

    refresh: function(frm) {
        frappe.dynamic_link = {
            doc: frm.doc,
            fieldname: 'custom_address',
            doctype: 'Cost Center'
        };

        if (frm.doc.custom_address) {
            frm.fields_dict['custom_address_display'].$wrapper
                .html(frm.doc.custom_address_display || '');
        }
    },

    custom_address: function(frm) {
        erpnext.utils.get_address_display(
            frm,
            'custom_address',
            'custom_address_display',
            false
        );
    }
});