"""Cleanup script-created FnF documents before re-run."""
import frappe


def run():
    frappe.set_user("Administrator")

    # Delete child tables first
    frappe.db.sql("DELETE FROM `tabFull and Final Outstanding Statement`")
    frappe.db.sql("DELETE FROM `tabFull and Final Statement`")
    frappe.db.sql("DELETE FROM `tabGL Entry` WHERE voucher_type='Indemnity'")
    frappe.db.sql("DELETE FROM `tabIndemnity`")
    frappe.db.sql("DELETE FROM `tabLeave Encashment` WHERE name LIKE 'HR-ENC%'")
    frappe.db.sql("DELETE FROM `tabAdditional Salary` WHERE name LIKE 'HR-ADS-26-06%'")
    frappe.db.commit()

    print("✓ Cleanup done")
    print(f"  FnF: {frappe.db.count('Full and Final Statement')} remaining")
    print(f"  Indemnity: {frappe.db.count('Indemnity')} remaining")
    print(f"  Leave Encashment: {frappe.db.count('Leave Encashment')} remaining")
    print(f"  Additional Salary: {frappe.db.count('Additional Salary')} remaining")
