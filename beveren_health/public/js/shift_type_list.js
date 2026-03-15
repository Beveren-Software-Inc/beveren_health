frappe.listview_settings['Shift Type'] = {
    onload: function(listview) {
        listview.page.add_inner_button('Update Last Sync For All Shifts', function() {
            frappe.confirm(
                'This will manually update Last Sync of Checkin based on last checkin records for all Shift Types. HRMS will then mark attendance automatically. Continue?',
                function() {
                    frappe.call({
                        method: 'beveren_health.beveren_health.utils.attendance.trigger_manual_last_sync',
                        freeze: true,
                        freeze_message: 'Updating Last Sync for all shifts...',
                        callback: function(r) {
                            if (!r.exc) {
                                frappe.msgprint({
                                    title: 'Done',
                                    message: r.message,
                                    indicator: 'green'
                                });
                            }
                        }
                    });
                }
            );
        });
    }
};