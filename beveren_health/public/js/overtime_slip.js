frappe.ui.form.on("Overtime Slip", {
    refresh(frm) {
        document.querySelectorAll(".btn-new").forEach((el) => {
            if (el.getAttribute("data-doctype") == "Additional Salary") {
                el.style.display = "none";
            }
        });
    }
});