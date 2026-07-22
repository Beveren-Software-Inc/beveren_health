# Copyright (c) 2026, beveren_health contributors
"""Department Wise Expense.

Aggregates expense-account GL entries by the Department accounting dimension.
Rows without a department are kept in a visible "No Department" bucket so the
report never silently understates spend; the Cost Center filter covers the
branch dimension, which is populated on every posting.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

NO_DEPARTMENT = "No Department"


def execute(filters: dict | None = None):
	filters = frappe._dict(filters or {})
	company = filters.get("company") or frappe.defaults.get_user_default("Company")
	from_date = getdate(filters.get("from_date") or getdate(nowdate()).replace(month=1, day=1))
	to_date = getdate(filters.get("to_date") or nowdate())
	group_by_account = bool(filters.get("group_by_account"))

	rows = get_expense_rows(company, from_date, to_date, filters)
	if group_by_account:
		columns = get_detail_columns()
		data = build_detail_data(rows)
	else:
		columns = get_summary_columns()
		data = build_summary_data(rows)

	return columns, data


def get_expense_rows(company, from_date, to_date, filters):
	conditions = ""
	values = {"company": company, "from_date": from_date, "to_date": to_date}

	if filters.get("department"):
		conditions += " AND ge.department = %(department)s"
		values["department"] = filters.department
	if filters.get("cost_center"):
		# Include children when a group cost center is picked.
		lft, rgt = frappe.db.get_value("Cost Center", filters.cost_center, ["lft", "rgt"])
		cost_centers = frappe.get_all(
			"Cost Center", filters={"lft": [">=", lft], "rgt": ["<=", rgt]}, pluck="name"
		)
		conditions += " AND ge.cost_center IN %(cost_centers)s"
		values["cost_centers"] = cost_centers

	return frappe.db.sql(
		f"""
		SELECT
			IFNULL(NULLIF(ge.department, ''), %(no_department)s) AS department,
			ge.account,
			COUNT(*) AS entries,
			SUM(ge.debit - ge.credit) AS expense_amount
		FROM `tabGL Entry` ge
		INNER JOIN `tabAccount` a ON a.name = ge.account
		WHERE a.root_type = 'Expense'
			AND ge.is_cancelled = 0
			AND ge.voucher_type != 'Period Closing Voucher'
			AND ge.company = %(company)s
			AND ge.posting_date BETWEEN %(from_date)s AND %(to_date)s
			{conditions}
		GROUP BY department, ge.account
		ORDER BY department, expense_amount DESC
		""",
		{**values, "no_department": NO_DEPARTMENT},
		as_dict=True,
	)


# ── Summary view: one row per department ─────────────────────────────────────


def get_summary_columns():
	return [
		{
			"fieldname": "department",
			"label": _("Department"),
			"fieldtype": "Link",
			"options": "Department",
			"width": 260,
		},
		{"fieldname": "entries", "label": _("Entries"), "fieldtype": "Int", "width": 90},
		{
			"fieldname": "expense_amount",
			"label": _("Expense Amount"),
			"fieldtype": "Currency",
			"width": 170,
		},
		{"fieldname": "pct_of_total", "label": _("% of Total"), "fieldtype": "Percent", "width": 100},
	]


def build_summary_data(rows):
	by_department = {}
	for row in rows:
		bucket = by_department.setdefault(
			row.department, {"department": row.department, "entries": 0, "expense_amount": 0.0}
		)
		bucket["entries"] += row.entries
		bucket["expense_amount"] += flt(row.expense_amount)

	data = sorted(by_department.values(), key=lambda r: r["expense_amount"], reverse=True)
	total = sum(r["expense_amount"] for r in data)

	for row in data:
		row["pct_of_total"] = (row["expense_amount"] / total * 100) if total else 0
		if row["department"] == NO_DEPARTMENT:
			row["department"] = None
			row["dept_label"] = NO_DEPARTMENT

	if data:
		data.append(
			{
				"department": None,
				"dept_label": _("Total"),
				"entries": sum(r["entries"] for r in data),
				"expense_amount": total,
				"pct_of_total": 100 if total else 0,
				"bold": 1,
			}
		)
	return data


# ── Detail view: department + expense account breakdown ─────────────────────


def get_detail_columns():
	return [
		{
			"fieldname": "department",
			"label": _("Department"),
			"fieldtype": "Data",
			"width": 240,
		},
		{
			"fieldname": "account",
			"label": _("Expense Account"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 300,
		},
		{"fieldname": "entries", "label": _("Entries"), "fieldtype": "Int", "width": 90},
		{
			"fieldname": "expense_amount",
			"label": _("Expense Amount"),
			"fieldtype": "Currency",
			"width": 170,
		},
	]


def build_detail_data(rows):
	data = []
	grand_total = 0.0
	current_department = None

	def close_department(dept, subtotal, count):
		data.append(
			{
				"department": _("{0} Total").format(dept),
				"account": None,
				"entries": count,
				"expense_amount": subtotal,
				"bold": 1,
			}
		)

	subtotal = 0.0
	count = 0
	for row in rows:
		if row.department != current_department:
			if current_department is not None:
				close_department(current_department, subtotal, count)
			current_department = row.department
			subtotal = 0.0
			count = 0
		data.append(
			{
				"department": row.department,
				"account": row.account,
				"entries": row.entries,
				"expense_amount": flt(row.expense_amount),
			}
		)
		subtotal += flt(row.expense_amount)
		count += row.entries
		grand_total += flt(row.expense_amount)

	if current_department is not None:
		close_department(current_department, subtotal, count)
		data.append(
			{
				"department": _("Grand Total"),
				"account": None,
				"entries": sum(r.entries for r in rows),
				"expense_amount": grand_total,
				"bold": 1,
			}
		)
	return data
