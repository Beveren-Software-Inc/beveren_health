frappe.ui.form.on('Item Group', {
    refresh: function(frm) {
        // Add custom button
        frm.add_custom_button(__('Reverse UOM Conversions'), function() {
            frappe.confirm(
                'This will reverse UOM conversions (PACK↔Unit) for all items in this group. Continue?',
                function() {
                    // User confirmed
                    frappe.call({
                        method: 'your_app.item_group.reverse_uom_conversions',
                        args: {
                            item_group: frm.doc.name
                        },
                        freeze: true,
                        freeze_message: __('Converting UOMs...'),
                        callback: function(r) {
                            if (r.message.success) {
                                frappe.msgprint({
                                    title: __('Conversion Complete'),
                                    indicator: 'green',
                                    message: __('Updated {0} items successfully.', [r.message.updated_count])
                                });
                                
                                if (r.message.errors.length > 0) {
                                    frappe.msgprint({
                                        title: __('Errors'),
                                        indicator: 'red',
                                        message: r.message.errors.join('<br>')
                                    });
                                }
                            }
                        }
                    });
                }
            );
        }, __('Actions'));
    }
});