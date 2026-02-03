frappe.ui.form.on('Shift Type', {
    start_time: function(frm) {
        calculate_standard_hours(frm);
    },
    end_time: function(frm) {
        calculate_standard_hours(frm);
    }
});

function calculate_standard_hours(frm) {
    let startTime = frm.doc.start_time;
    let endTime = frm.doc.end_time;

    if (!startTime || !endTime) return;

    let [startH, startM, startS] = startTime.split(":").map(Number);
    let [endH, endM, endS] = endTime.split(":").map(Number);

    let startSeconds = startH * 3600 + startM * 60 + startS;
    let endSeconds = endH * 3600 + endM * 60 + endS;

    if (endSeconds < startSeconds) {
        endSeconds += 24 * 3600;
    }

    let totalSeconds = endSeconds - startSeconds;
    let totalHours = totalSeconds / 3600;

    frm.set_value('custom_standard_working_hours', totalHours.toFixed(2));
}
