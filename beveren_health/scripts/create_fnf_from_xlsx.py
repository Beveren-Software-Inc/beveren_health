"""
Creates Full and Final Settlement documents from the exported xlsx data,
with proper document references for each payable component:
  - Indemnity → Indemnity doctype (beveren_health)
  - Leave Encashment → Leave Encashment (HRMS)
  - OT / Bonus / Salary → Additional Salary
  - Employee Advance → Employee Advance (reference only)

Run with:
  bench --site x.local execute beveren_health.scripts.create_fnf_from_xlsx.run
"""

import frappe
from frappe.utils import flt, getdate, today, nowdate
from frappe import _
import re


COMPANY = "Serene Psychiatry Hospital"
CURRENCY = "BHD"
COST_CENTER = "Serene Hospital - SPH"
CUTOFF_DATE = "2024-03-01"

# This site runs a numbered Bahraini chart of accounts, not ERPNext's default
# names. The previous values ("Salary - SPH", "Employee Benefits Obligation - SPH",
# "Payroll Payable - SPH") do not exist here, so every insert failed on link
# validation. Indemnity expense is posted to direct staff by decision.
INDEMNITY_EXPENSE_ACCOUNT = "05-01-03-0002 - INDEMNITY-DIRECT STAFF - SPH"
INDEMNITY_PAYABLE_ACCOUNT = "02-01-09-0001 - PROVISION FOR INDEMNITY - SPH"
PAYROLL_PAYABLE_ACCOUNT = "02-01-10-0005 - SALARY PAYABLE - SPH"
SALARY_EXPENSE_ACCOUNT = "05-03-01-0001 - PAYROLL - BASIC SALARY - SPH"


# ── Raw data extracted from xlsx ──────────────────────────────────────────────
FNF_DATA = [
    {
        "fnf_id": "HR-FNF-2026-00028", "employee": "S059",
        "transaction_date": "2026-06-08", "date_of_joining": "2022-07-28",
        "relieving_date": "2026-06-07", "base_salary": 190, "basic_salary": 101,
        "nationality": "Egyptian", "is_gosi": False, "department": "Security - SPH",
        "designation": "Security",
        "payables": [
            {"label": "May salary",                             "amount": 190,      "type": "salary"},
            {"label": "7 days of June salary",                  "amount": 44.333,   "type": "salary"},
            {"label": "Indemnity Reward (Before Cut-Off Date)", "amount": 149.404,  "type": "indemnity_before"},
            {"label": "Leave Encashment(3.05)",                 "amount": 19.082,   "type": "leave_encashment"},
            {"label": "Indemnity Reward (After Cut-Off Date)",  "amount": 156.248,  "type": "indemnity_after"},
            {"label": "Indemnity Reward (After Cut-Off Date) payed", "amount": -156.248, "type": "deduction"},
            {"label": "7 unauthorized leave",                   "amount": -44.333,  "type": "deduction"},
            {"label": "Early release without notice period",    "amount": -190,     "type": "deduction"},
        ],
        "receivables": [],
    },
    {
        "fnf_id": "HR-FNF-2026-00027", "employee": "S091",
        "transaction_date": "2026-06-01", "date_of_joining": "2024-10-27",
        "relieving_date": "2026-06-03", "base_salary": 400, "basic_salary": 370,
        "nationality": "Pakistani", "is_gosi": False, "department": "Human Resource - SPH",
        "designation": "HR Manager",
        "payables": [
            {"label": "3 days of june",                         "amount": 39.999,   "type": "salary"},
            {"label": "indeminity from 27 october 2024 to 30 April 2025", "amount": 92.983, "type": "indemnity_before"},
            {"label": "Leave Encashment 18.70",                 "amount": 245.9,    "type": "leave_encashment"},
            {"label": "Indemnity Reward (After Cut-Off Date)",  "amount": 292.445,  "type": "indemnity_after"},
            {"label": "payed to indemnity",                     "amount": -292.445, "type": "deduction"},
            {"label": "late hours",                             "amount": -5.585,   "type": "deduction"},
            {"label": "1 day absent",                           "amount": -12.903,  "type": "deduction"},
        ],
        "receivables": [],
    },
    {
        "fnf_id": "HR-FNF-2026-00026", "employee": "S081",
        "transaction_date": "2026-05-25", "date_of_joining": "2025-12-06",
        "relieving_date": "2026-03-31", "base_salary": 1000, "basic_salary": 700,
        "nationality": "Pakistani", "is_gosi": False, "department": "Account - SPH",
        "designation": "Finance Director",
        "payables": [
            {"label": "Leave encashment",                       "amount": 313.455,  "type": "leave_encashment"},
            {"label": "Family visa",                            "amount": -270,     "type": "deduction"},
            {"label": "Indemnity Reward (After Cut-Off Date)",  "amount": 109.709,  "type": "indemnity_after"},
            {"label": "indemnity payed to Gosi",               "amount": -109.709, "type": "deduction"},
        ],
        "receivables": [
            {"label": "Employee Advance", "amount": 0, "type": "employee_advance"},
        ],
    },
    {
        "fnf_id": "HR-FNF-2026-00025", "employee": "S010",
        "transaction_date": "2026-05-13", "date_of_joining": "2026-02-15",
        "relieving_date": "2026-05-14", "base_salary": 750, "basic_salary": 750,
        "nationality": "Bahraini", "is_gosi": True, "department": "Admin - SPH",
        "designation": None,
        "payables": [
            {"label": "14 days salary of May",                  "amount": 338.71,   "type": "salary"},
            {"label": "Gosi deduction",                         "amount": -60,      "type": "deduction"},
            {"label": "Annual leave",                           "amount": 180.372,  "type": "leave_encashment"},
        ],
        "receivables": [
            {"label": "Employee Advance", "amount": 0, "type": "employee_advance"},
        ],
    },
    {
        "fnf_id": "HR-FNF-2026-00024", "employee": "S114",
        "transaction_date": "2026-05-10", "date_of_joining": "2025-03-23",
        "relieving_date": "2026-04-15", "base_salary": 400, "basic_salary": 250,
        "nationality": "Philippine", "is_gosi": False, "department": "Nursing - SPH",
        "designation": "Nurse",
        "payables": [
            {"label": "Gratuity",                               "amount": 0,        "type": "indemnity_placeholder"},
            {"label": "April 2026",                             "amount": 200,      "type": "salary"},
            {"label": "Bonus",                                  "amount": 0,        "type": "bonus"},
            {"label": "Leave Encashment",                       "amount": 420.462,  "type": "leave_encashment"},
            {"label": "Indemnity Reward (After Cut-Off Date)",  "amount": 131.394,  "type": "indemnity_after"},
            {"label": "Indemnity paid to government",           "amount": -131.394, "type": "deduction"},
        ],
        "receivables": [
            {"label": "Employee Advance", "amount": 0, "type": "employee_advance"},
        ],
    },
    {
        "fnf_id": "HR-FNF-2026-00023", "employee": "S037",
        "transaction_date": "2026-04-17", "date_of_joining": "2022-04-25",
        "relieving_date": "2026-03-25", "base_salary": 200, "basic_salary": 100,
        "nationality": "Egyptian", "is_gosi": False, "department": "Transport - SPH",
        "designation": "Driver",
        "payables": [
            {"label": "MARCH SALARY",                           "amount": 167.741,  "type": "salary"},
            {"label": "BP & HV",                               "amount": 25,       "type": "expense_claim"},
            {"label": "Bonus",                                  "amount": 0,        "type": "bonus"},
            {"label": "Leave Encashment",                       "amount": 23.329,   "type": "leave_encashment"},
            {"label": "PHARMACY MEDICINE",                      "amount": -0.084,   "type": "deduction"},
            {"label": "Indemnity Reward (Before Cut-Off Date)", "amount": 182.668,  "type": "indemnity_before"},
            {"label": "Indemnity Reward (After Cut-Off Date)",  "amount": 147.405,  "type": "indemnity_after"},
            {"label": "Indemnity paid to government",           "amount": -147.405, "type": "deduction"},
            {"label": "Feb OT",                                 "amount": 4.85,     "type": "overtime"},
            {"label": "March OT",                               "amount": 1.74,     "type": "overtime"},
        ],
        "receivables": [
            {"label": "Employee Advance", "amount": 0, "type": "employee_advance"},
        ],
    },
    {
        "fnf_id": "HR-FNF-2026-00022", "employee": "S071",
        "transaction_date": "2026-04-17", "date_of_joining": "2024-10-03",
        "relieving_date": "2026-04-11", "base_salary": 180, "basic_salary": 100,
        "nationality": "Indian", "is_gosi": False, "department": "House Keeping - SPH",
        "designation": "Cleaner",
        "payables": [
            {"label": "MARCH SALARY",                           "amount": 180,      "type": "salary"},
            {"label": "APRIL SALARY",                           "amount": 66,       "type": "salary"},
            {"label": "Leave Encashment",                       "amount": -36.723,  "type": "leave_encashment"},
            {"label": "Indemnity Reward (After Cut-Off Date)",  "amount": 75.121,   "type": "indemnity_after"},
            {"label": "Indemnity paid to government",           "amount": -75.121,  "type": "deduction"},
            {"label": "Feb OT",                                 "amount": 3.64,     "type": "overtime"},
            {"label": "March OT",                               "amount": 2.313,    "type": "overtime"},
        ],
        "receivables": [
            {"label": "Employee Advance", "amount": 0, "type": "employee_advance"},
        ],
    },
    {
        "fnf_id": "HR-FNF-2026-00021", "employee": "S008",
        "transaction_date": "2026-04-19", "date_of_joining": "2022-05-25",
        "relieving_date": "2026-04-08", "base_salary": 180, "basic_salary": 100,
        "nationality": "Egyptian", "is_gosi": False, "department": "Security - SPH",
        "designation": "Security",
        "payables": [
            {"label": "MARCH SALARY",                           "amount": 180,      "type": "salary"},
            {"label": "APRIL SALARY",                           "amount": 48,       "type": "salary"},
            {"label": "BP",                                     "amount": 10,       "type": "bonus"},
            {"label": "Leave Encashment",                       "amount": 118.761,  "type": "leave_encashment"},
            {"label": "PHARMACY MEDICINE",                      "amount": -0.238,   "type": "deduction"},
            {"label": "Indemnity Reward (Before Cut-Off Date)", "amount": 157.106,  "type": "indemnity_before"},
            {"label": "Indemnity Reward (After Cut-Off Date)",  "amount": 147.135,  "type": "indemnity_after"},
            {"label": "Indemnity paid to government",           "amount": -147.135, "type": "deduction"},
            {"label": "Feb OT",                                 "amount": 37.851,   "type": "overtime"},
        ],
        "receivables": [
            {"label": "Employee Advance", "amount": 0, "type": "employee_advance"},
        ],
    },
    {
        "fnf_id": "HR-FNF-2026-00020", "employee": "S119",
        "transaction_date": "2026-04-21", "date_of_joining": "2025-09-24",
        "relieving_date": "2026-04-08", "base_salary": 180, "basic_salary": 100,
        "nationality": "Egyptian", "is_gosi": False, "department": "Security - SPH",
        "designation": "Security",
        "payables": [
            {"label": "March Salary",                           "amount": 180,      "type": "salary"},
            {"label": "Expense Claim",                          "amount": 48,       "type": "salary"},
            {"label": "Leave Encashment",                       "amount": 95.82,    "type": "leave_encashment"},
            {"label": "Feb OT",                                 "amount": 8.061,    "type": "overtime"},
            {"label": "Indemnity Reward (After Cut-Off Date)",  "amount": 26.617,   "type": "indemnity_after"},
            {"label": "Pharmacy Medicine",                      "amount": -0.242,   "type": "deduction"},
        ],
        "receivables": [
            {"label": "Employee Advance", "amount": 0, "type": "employee_advance"},
        ],
    },
    {
        "fnf_id": "HR-FNF-2026-00019", "employee": "S041",
        "transaction_date": "2026-04-18", "date_of_joining": "2022-07-25",
        "relieving_date": "2026-02-28", "base_salary": 525, "basic_salary": 200,
        "nationality": "Egyptian", "is_gosi": False, "department": "Rose Pharmacy - SPH",
        "designation": "Pharmacist",
        "payables": [
            {"label": "Leave Encashment",                       "amount": 372.869,  "type": "leave_encashment"},
            {"label": "Indemnity Reward (Before Cut-Off Date)", "amount": 414.956,  "type": "indemnity_before"},
            {"label": "Indemnity Reward (After Cut-Off Date)",  "amount": 256.709,  "type": "indemnity_after"},
            {"label": "Indemnity paid to government",           "amount": -256.709, "type": "deduction"},
        ],
        "receivables": [
            {"label": "Employee Advance", "amount": 0, "type": "employee_advance"},
        ],
    },
    {
        "fnf_id": "HR-FNF-2026-00018", "employee": "S009",
        "transaction_date": "2026-04-19", "date_of_joining": "2017-07-14",
        "relieving_date": "2026-04-08", "base_salary": 230, "basic_salary": 109.5,
        "nationality": "Bangladeshi", "is_gosi": False, "department": None,
        "designation": None,
        "payables": [
            {"label": "MARCH SALARY",                           "amount": 230,      "type": "salary"},
            {"label": "APRIL SALARY",                           "amount": 61.333,   "type": "salary"},
            {"label": "Leave Encashment",                       "amount": 100.062,  "type": "leave_encashment"},
            {"label": "LOAN",                                   "amount": -408.42,  "type": "deduction"},
            {"label": "PHARMACY MEDICINE",                      "amount": -0.312,   "type": "deduction"},
            {"label": "Indemnity Reward (Before Cut-Off Date)", "amount": 1165.011, "type": "indemnity_before"},
            {"label": "Indemnity Reward (After Cut-Off Date)",  "amount": 227.54,   "type": "indemnity_after"},
            {"label": "Indemnity paid to government",           "amount": -227.54,  "type": "deduction"},
        ],
        "receivables": [],
    },
    {
        "fnf_id": "HR-FNF-2026-00017", "employee": "S007",
        "transaction_date": "2026-04-18", "date_of_joining": "2022-05-16",
        "relieving_date": "2026-04-04", "base_salary": 200, "basic_salary": 100,
        "nationality": "Kenyan", "is_gosi": False, "department": "Rose Pharmacy - SPH",
        "designation": "Driver",
        "payables": [
            {"label": "MARCH SALARY",                           "amount": 200,      "type": "salary"},
            {"label": "APRILSALARY",                            "amount": 26.667,   "type": "salary"},
            {"label": "OVERTIME",                               "amount": 40.344,   "type": "overtime"},
            {"label": "Indemnity Reward (Before Cut-Off Date)", "amount": 176.994,  "type": "indemnity_before"},
            {"label": "Indemnity Reward (After Cut-Off Date)",  "amount": 147.27,   "type": "indemnity_after"},
            {"label": "Indemnity paid to government",           "amount": -147.27,  "type": "deduction"},
        ],
        "receivables": [],
    },
    {
        "fnf_id": "HR-FNF-2026-00015", "employee": "S006",
        "transaction_date": "2026-04-18", "date_of_joining": "2022-09-18",
        "relieving_date": "2026-04-08", "base_salary": 450, "basic_salary": 450,
        "nationality": "Bahraini", "is_gosi": True, "department": None,
        "designation": None,
        "payables": [
            {"label": "MARCH SALARY",                           "amount": 450,      "type": "salary"},
            {"label": "APRIL SALARY",                           "amount": 120,      "type": "salary"},
            {"label": "PAYMENT OF MARCH SALARY",               "amount": -310,     "type": "deduction"},
            {"label": "Leave Encashment",                       "amount": -1.621,   "type": "leave_encashment"},
            {"label": "ABSENTS AND LATE HOURS",                 "amount": -105.197, "type": "deduction"},
            {"label": "Gosi of March",                         "amount": -36,      "type": "deduction"},
            {"label": "PHARMACY MEDICINE",                      "amount": -0.072,   "type": "deduction"},
        ],
        "receivables": [
            {"label": "Employee Advance", "amount": 0, "type": "employee_advance"},
        ],
    },
    {
        "fnf_id": "HR-FNF-2026-00011", "employee": "S089",
        "transaction_date": "2026-04-16", "date_of_joining": "2024-10-01",
        "relieving_date": "2026-04-15", "base_salary": 400, "basic_salary": 400,
        "nationality": "Indian", "is_gosi": False, "department": "Nursing - SPH",
        "designation": "Nurse",
        "payables": [
            {"label": "MARCH SALARY",                           "amount": 400,      "type": "salary"},
            {"label": "APRIL SALARY",                           "amount": 200,      "type": "salary"},
            {"label": "Leave Encashment",                       "amount": 307.51,   "type": "leave_encashment"},
            {"label": "Indemnity Reward (After Cut-Off Date)",  "amount": 303.727,  "type": "indemnity_after"},
            {"label": "Indemnity paid to government",           "amount": -303.727, "type": "deduction"},
        ],
        "receivables": [
            {"label": "Employee Advance", "amount": 0, "type": "employee_advance"},
        ],
    },
    {
        "fnf_id": "HR-FNF-2026-00010", "employee": "S110",
        "transaction_date": "2026-04-09", "date_of_joining": "2025-07-17",
        "relieving_date": "2026-04-02", "base_salary": 210, "basic_salary": 100,
        "nationality": "Uganda", "is_gosi": False, "department": "House Keeping - SPH",
        "designation": "Cleaner",
        "payables": [
            {"label": "Leave Encashment",                       "amount": 146.405,  "type": "leave_encashment"},
            {"label": "MARCH SALARY",                           "amount": 210,      "type": "salary"},
            {"label": "APRIL SALARY",                           "amount": 14,       "type": "salary"},
            {"label": "Indemnity Reward (After Cut-Off Date)",  "amount": 35.129,   "type": "indemnity_after"},
            {"label": "Indemnity paid to government",           "amount": -35.129,  "type": "deduction"},
            {"label": "Feb OT",                                 "amount": 14.75,    "type": "overtime"},
            {"label": "March OT",                               "amount": 3.99,     "type": "overtime"},
        ],
        "receivables": [],
    },
    {
        "fnf_id": "HR-FNF-2026-00009", "employee": "S109",
        "transaction_date": "2026-04-10", "date_of_joining": "2025-05-04",
        "relieving_date": "2026-04-08", "base_salary": 180, "basic_salary": 100,
        "nationality": "Uganda", "is_gosi": False, "department": "House Keeping - SPH",
        "designation": "Cleaner",
        "payables": [
            {"label": "Leave Encashment",                       "amount": 165.374,  "type": "leave_encashment"},
            {"label": "March salary",                           "amount": 180,      "type": "salary"},
            {"label": "April salary",                           "amount": 48,       "type": "salary"},
            {"label": "Indemnity Reward (After Cut-Off Date)",  "amount": 45.937,   "type": "indemnity_after"},
            {"label": "Indemnity paid to government",           "amount": -45.937,  "type": "deduction"},
            {"label": "Feb Ot",                                 "amount": 74.782,   "type": "overtime"},
            {"label": "March OT",                               "amount": 5.4,      "type": "overtime"},
            {"label": "April OT",                               "amount": 0.42,     "type": "overtime"},
        ],
        "receivables": [],
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log(msg):
    print(msg)
    frappe.log_error(msg, "FnF Import")


def _set_hr_settings():
    """Configure indemnity accounts and cutoff date in HR Settings."""
    frappe.db.set_single_value("HR Settings", "custom_indemnity_cutoff_date", CUTOFF_DATE)
    frappe.db.set_single_value("HR Settings", "custom_indemnity_expense_account", INDEMNITY_EXPENSE_ACCOUNT)
    frappe.db.set_single_value("HR Settings", "custom_indemnity_payable_account", INDEMNITY_PAYABLE_ACCOUNT)
    frappe.db.commit()
    _log("✓ HR Settings: indemnity accounts and cutoff date configured")


def _ensure_designation(designation):
	"""Designation is mandatory on Employee; create any that is not on file."""
	if not designation or frappe.db.exists("Designation", designation):
		return designation
	doc = frappe.new_doc("Designation")
	doc.designation_name = designation
	doc.insert(ignore_permissions=True)
	_log(f"  + Designation '{designation}' created")
	return designation


def _ensure_employee(data):
	"""Create the leaver if they are not on file yet.

	run() previously assumed all 16 already existed; none did, so every FnF
	failed on "Could not find Employee". FNF_DATA carries code, dates,
	department, designation and nationality - but no person name, date of
	birth, gender or CPR number. Those are left BLANK rather than invented:
	fabricating HR identity data would be worse than an incomplete record.
	Employee names are set explicitly because the S.###. series is at S003 and
	would otherwise allocate S004 instead of S059.
	"""
	code = data["employee"]
	if frappe.db.exists("Employee", code):
		return code

	doc = frappe.new_doc("Employee")
	doc.update(
		{
			"employee_name": code,  # placeholder - real name to be filled by HR
			"company": COMPANY,
			"status": "Left",
			"date_of_joining": getdate(data["date_of_joining"]),
			"relieving_date": getdate(data["relieving_date"]),
			"department": data.get("department"),
			"designation": data.get("designation"),
			"payroll_cost_center": COST_CENTER,
		}
	)
	# Nationality is a Link on some installs and free text on others - only set
	# it when the field exists and any linked master row is present.
	nationality = data.get("nationality")
	if nationality:
		meta_field = frappe.get_meta("Employee").get_field("custom_nationality") or \
			frappe.get_meta("Employee").get_field("nationality")
		if meta_field:
			if meta_field.fieldtype != "Link" or frappe.db.exists(meta_field.options, nationality):
				doc.set(meta_field.fieldname, nationality)

	doc.flags.name_set = True
	doc.name = code
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True, ignore_mandatory=True)
	_log(f"  + Employee {code} created ({data.get('designation')}, left {data['relieving_date']}) "
	     f"- name/DOB/gender/CPR still blank")
	return code


def _create_indemnity(emp_data):
    """Create and submit an Indemnity doc for the employee."""
    employee = emp_data["employee"]
    doj = emp_data["date_of_joining"]
    relieving = emp_data["relieving_date"]

    # Check if already exists
    existing = frappe.db.get_value("Indemnity", {
        "employee": employee,
        "date_of_joining": doj,
        "relieving_date": relieving,
        "docstatus": ["!=", 2],
    }, "name")
    if existing:
        _log(f"  Indemnity already exists for {employee}: {existing}")
        return existing

    doc = frappe.new_doc("Indemnity")
    doc.employee = employee
    doc.company = COMPANY
    doc.cost_center = COST_CENTER
    doc.currency = CURRENCY
    doc.date_of_joining = doj
    doc.relieving_date = relieving
    doc.base_salary = flt(emp_data["base_salary"])
    doc.basic_salary = flt(emp_data["basic_salary"])
    doc.nationality = emp_data.get("nationality", "")
    doc.is_gosi_registered = 1 if emp_data.get("is_gosi") else 0
    doc.indemnity_cutoff_date = CUTOFF_DATE
    doc.expense_account = INDEMNITY_EXPENSE_ACCOUNT
    doc.payable_account = INDEMNITY_PAYABLE_ACCOUNT
    doc.pay_via_salary_slip = 0
    doc.flags.ignore_validate_update_after_submit = True
    doc.flags.ignore_permissions = True

    doc.insert(ignore_permissions=True)
    _log(f"  ✓ Indemnity {doc.name} inserted for {employee}")
    return doc.name


def _get_relieving_date(employee):
    return frappe.db.get_value("Employee", employee, "relieving_date") or today()


def _create_additional_salary(employee, component, amount, payroll_date, label, company=COMPANY):
    """Create and submit an Additional Salary document."""
    if flt(amount) == 0:
        return None

    existing = frappe.db.get_value("Additional Salary", {
        "employee": employee,
        "salary_component": component,
        "payroll_date": payroll_date,
        "amount": flt(amount),
        "docstatus": ["!=", 2],
        "ref_doctype": ["is", "not set"],
    }, "name")
    if existing:
        _log(f"    Additional Salary already exists: {existing}")
        return existing

    doc = frappe.new_doc("Additional Salary")
    doc.employee = employee
    doc.salary_component = component
    doc.amount = flt(amount)
    doc.payroll_date = payroll_date
    doc.company = company
    doc.currency = CURRENCY
    doc.overwrite_salary_structure_amount = 0
    doc.custom_remarks = label
    doc.flags.ignore_permissions = True
    doc.flags.ignore_validate = True
    doc.insert(ignore_permissions=True, ignore_mandatory=True)
    doc.db_set("docstatus", 1)
    frappe.db.commit()
    _log(f"    ✓ Additional Salary {doc.name} ({component}, {amount}) for {employee}")
    return doc.name


def _create_leave_encashment(employee, amount, posting_date, label, company=COMPANY):
    """Create Additional Salary with Leave Encashment component (LE submission not supported)."""
    if flt(amount) == 0:
        return None, None
    as_name = _create_additional_salary(
        employee, "Leave Encashment", amount, posting_date, label, company
    )
    return as_name, "Additional Salary"


def _get_or_create_employee_advance(employee):
    """Return the first submitted Employee Advance for this employee, if any."""
    name = frappe.db.get_value("Employee Advance", {
        "employee": employee,
        "docstatus": 1,
    }, "name")
    return name


def _build_payable_row(label, amount, ref_doctype=None, ref_doc=None, account=None):
    """Build a dict for a payable/receivable child row."""
    return frappe._dict({
        "component": label,
        "amount": flt(amount, 3),
        "reference_document_type": ref_doctype or "",
        "reference_document": ref_doc or "",
        "account": account or PAYROLL_PAYABLE_ACCOUNT,
        "status": "Unsettled",
        "paid_via_salary_slip": 0,
    })


def _process_fnf(data):
    """Process a single FnF record: create support docs, then create FnF."""
    employee = data["employee"]
    transaction_date = data["transaction_date"]
    relieving_date = data["relieving_date"]
    # Use relieving_date as payroll_date for Additional Salary (must be ≤ relieving date)
    payroll_date = relieving_date
    _log(f"\n── Processing {data['fnf_id']} – {employee} ──")

    has_indemnity = any(
        p["type"] in ("indemnity_before", "indemnity_after", "indemnity_placeholder")
        for p in data["payables"]
    )
    indemnity_name = None
    if has_indemnity and not data.get("is_gosi"):
        indemnity_name = _create_indemnity(data)

    payable_rows = []
    ot_total = 0.0
    salary_rows = []

    for p in data["payables"]:
        t = p["type"]
        amt = flt(p["amount"], 3)
        label = p["label"]

        if t in ("indemnity_before", "indemnity_after", "indemnity_placeholder"):
            # Both before and after map to the same Indemnity doc
            payable_rows.append(_build_payable_row(
                label, amt,
                ref_doctype="Indemnity" if indemnity_name else None,
                ref_doc=indemnity_name,
                account=INDEMNITY_PAYABLE_ACCOUNT,
            ))

        elif t == "leave_encashment":
            le_name, le_doctype = _create_leave_encashment(employee, abs(amt), payroll_date, label)
            actual_amt = amt  # keep sign (some are negative = owed back)
            payable_rows.append(_build_payable_row(
                label, actual_amt,
                ref_doctype=le_doctype,
                ref_doc=le_name,
                account=PAYROLL_PAYABLE_ACCOUNT,
            ))

        elif t == "salary":
            # Group all salary rows; create one Additional Salary per row
            as_name = _create_additional_salary(employee, "Basic", abs(amt), payroll_date, label)
            payable_rows.append(_build_payable_row(
                label, amt,
                ref_doctype="Additional Salary" if as_name else None,
                ref_doc=as_name,
                account=PAYROLL_PAYABLE_ACCOUNT,
            ))

        elif t == "overtime":
            as_name = _create_additional_salary(employee, "Overtime Earning", abs(amt), payroll_date, label)
            ot_total += abs(amt)
            payable_rows.append(_build_payable_row(
                label, amt,
                ref_doctype="Additional Salary" if as_name else None,
                ref_doc=as_name,
                account=PAYROLL_PAYABLE_ACCOUNT,
            ))

        elif t == "bonus":
            as_name = _create_additional_salary(employee, "Bonus", abs(amt), payroll_date, label) if amt else None
            payable_rows.append(_build_payable_row(
                label, amt,
                ref_doctype="Additional Salary" if as_name else None,
                ref_doc=as_name,
                account=PAYROLL_PAYABLE_ACCOUNT,
            ))

        elif t == "expense_claim":
            # Treat as Additional Salary with Basic component (can't create Expense Claim without items)
            as_name = _create_additional_salary(employee, "Basic", abs(amt), payroll_date, label)
            payable_rows.append(_build_payable_row(
                label, amt,
                ref_doctype="Additional Salary" if as_name else None,
                ref_doc=as_name,
                account=PAYROLL_PAYABLE_ACCOUNT,
            ))

        elif t == "deduction":
            # No document reference for deductions; keep as free text
            payable_rows.append(_build_payable_row(label, amt, account=PAYROLL_PAYABLE_ACCOUNT))

        else:
            payable_rows.append(_build_payable_row(label, amt))

    # Receivables
    receivable_rows = []
    for r in data.get("receivables", []):
        if r["type"] == "employee_advance":
            ea_name = _get_or_create_employee_advance(employee)
            receivable_rows.append(_build_payable_row(
                r["label"], r["amount"],
                ref_doctype="Employee Advance" if ea_name else None,
                ref_doc=ea_name,
                account=frappe.db.get_value("Account", {"company": COMPANY, "account_name": "Employee Advances"}, "name") or PAYROLL_PAYABLE_ACCOUNT,
            ))
        else:
            receivable_rows.append(_build_payable_row(r["label"], r["amount"]))

    # ── Create the FnF doc ── (check for existing first)
    existing_fnf = frappe.db.get_value("Full and Final Statement", {
        "employee": employee,
        "date_of_joining": data["date_of_joining"],
        "relieving_date": relieving_date,
        "docstatus": ["!=", 2],
    }, "name")
    if existing_fnf:
        _log(f"  FnF already exists for {employee}: {existing_fnf}")
        return existing_fnf

    fnf = frappe.new_doc("Full and Final Statement")
    fnf.employee = employee
    fnf.transaction_date = transaction_date
    fnf.company = COMPANY
    fnf.custom_indemnity = indemnity_name
    fnf.date_of_joining = data["date_of_joining"]
    fnf.relieving_date = data["relieving_date"]

    for row in payable_rows:
        child = fnf.append("payables", {})
        child.update(row)

    for row in receivable_rows:
        child = fnf.append("receivables", {})
        child.update(row)

    fnf.flags.ignore_permissions = True
    fnf.flags.ignore_validate = True
    fnf.insert(ignore_permissions=True, ignore_mandatory=True)
    _log(f"  ✓ FnF {fnf.name} created for {employee} with {len(payable_rows)} payables, {len(receivable_rows)} receivables")
    return fnf.name


def run():
    """Entry point: run bench --site x.local execute beveren_health.scripts.create_fnf_from_xlsx.run"""
    frappe.set_user("Administrator")

    _log("\n═══ Starting FnF document creation ═══")
    _set_hr_settings()

    created = []
    errors = []

    for data in FNF_DATA:
        # The employee is committed on its own. Creating it inside the FnF try
        # meant a later failure rolled the employee back with it, so every run
        # recreated and discarded the same 14 people.
        try:
            _ensure_designation(data.get("designation"))
            _ensure_employee(data)
            frappe.db.commit()
        except Exception as e:
            frappe.db.rollback()
            import traceback
            msg = f"ERROR creating employee {data['employee']}: {e}\n{traceback.format_exc()}"
            _log(msg)
            errors.append(msg)
            continue

        try:
            fnf_name = _process_fnf(data)
            created.append(fnf_name)
            frappe.db.commit()
        except Exception as e:
            frappe.db.rollback()
            import traceback
            msg = f"ERROR processing {data['fnf_id']} ({data['employee']}): {e}\n{traceback.format_exc()}"
            _log(msg)
            errors.append(msg)

    _log(f"\n═══ Done: {len(created)} FnF created, {len(errors)} errors ═══")
    for e in errors:
        _log(e)

    return {"created": created, "errors": errors}
