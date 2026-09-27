"""Installation and test-environment setup for the Beveren Health site customizations."""

import frappe
from frappe.utils import cint

# Required fields the site customization adds to doctypes whose records the test
# framework creates itself, see beveren_health/beveren_health/beveren_health/custom/:
#   employee.json    -> custom_nationality, custom_religion, employee_number, designation
#   shift_type.json  -> holiday_list
# The synthetic records the framework raises do not fill them in, so none of them can be
# created on a site with this app installed (see before_tests).
MANDATORY_FIELDS_FOR_TEST_RECORDS = {
	"Employee": ("custom_nationality", "custom_religion", "employee_number", "designation"),
	"Shift Type": ("holiday_list",),
}


def before_tests():
	"""Make the site's required fields stop blocking the framework's test records.

	HR wants complete employment records, so the site customization makes Nationality,
	Religion, CPR Number and Designation required on Employee, and a Holiday List
	required on Shift Type. The records the test framework raises for the app are
	synthetic, and it raises them with a handful of fields only:

	* ``erpnext.tests.utils.BootStrapTestData`` inserts ``_Test Employee`` with a
	  company, department, name, gender and joining details only. It runs as soon as
	  any ERPNext test module is imported, i.e. as soon as a test needs any ERPNext
	  test record.
	* ``erpnext.setup.doctype.employee.test_employee.make_employee``, which creates the
	  Employee test records, leaves the same fields empty.
	* HRMS' ``Shift Type`` ``test_records.json`` inserts ``Day Shift`` without a
	  holiday list.

	So on an installed site ``bench run-tests`` aborts before a single test runs:

	    Employee, _T-Employee-00001: custom_nationality, custom_religion,
	    employee_number, designation

	Those rules are HR's rules for live records and the test suite has no use for them,
	so the ``reqd`` flag of the shipped Custom Field / Property Setter rows is cleared
	for the run. ``bench migrate`` (or re-installing the app) applies the customization
	files again and restores them, so nothing is lost by running the tests.

	Called by ``bench run-tests`` through the ``before_tests`` hook in hooks.py, before
	the integration tests - and therefore before the framework creates any of those
	records - run.
	"""
	relaxed = [
		f"{doctype}.{fieldname}"
		for doctype, fieldnames in MANDATORY_FIELDS_FOR_TEST_RECORDS.items()
		for fieldname in fieldnames
		if _clear_required_flag(doctype, fieldname)
	]

	if not relaxed:
		return

	frappe.clear_cache()
	# The integration test classes roll their transaction back when they are torn down,
	# so the cleared flags have to be committed to stay cleared for the rest of the run.
	frappe.db.commit()  # nosemgrep


def _clear_required_flag(doctype, fieldname):
	"""Clear the required flag of a field's Custom Field / Property Setter rows.

	Returns True when at least one row had a required flag to clear.
	"""
	cleared = False

	custom_fields = frappe.get_all(
		"Custom Field", filters={"dt": doctype, "fieldname": fieldname, "reqd": 1}, pluck="name"
	)
	for custom_field in custom_fields:
		frappe.db.set_value("Custom Field", custom_field, "reqd", 0, update_modified=False)
		cleared = True

	property_setters = frappe.get_all(
		"Property Setter",
		filters={"doc_type": doctype, "field_name": fieldname, "property": "reqd"},
		fields=["name", "value"],
	)
	for property_setter in property_setters:
		if not cint(property_setter.value):
			continue

		frappe.db.set_value("Property Setter", property_setter.name, "value", "0", update_modified=False)
		cleared = True

	return cleared
