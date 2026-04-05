from frappe.utils import date_diff

def calculate_years_of_service(doc):
    if doc.relieving_date and doc.date_of_joining:
        days = date_diff(doc.relieving_date, doc.date_of_joining)
        years = int(days / 365)
        doc.custom_years_of_service = years

def before_save(doc, method):
    calculate_years_of_service(doc)