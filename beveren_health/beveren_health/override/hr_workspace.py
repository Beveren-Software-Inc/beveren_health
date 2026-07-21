# Copyright (c) 2026, Beveren Software and contributors
"""Keep beveren_health's HR additions on the standard HR workspaces.

HR Setup is shipped by hrms and re-synced from that app's JSON on every migrate,
so editing it in place would both dirty a third-party repo and be lost on the
next hrms upgrade. This re-applies our links after each migrate instead, which
keeps the customisation inside beveren_health where HR work belongs.
"""

from __future__ import annotations

import frappe

# workspace -> (card label, doctype to add, the link it should follow)
WORKSPACE_LINKS = [
	("HR Setup", "Attendance", "Employee Checkin Request", "Employee Checkin"),
	("Shift & Attendance", "Attendance", "Employee Checkin Request", "Employee Checkin"),
]

# Desktop icons we keep hidden. "People" points at a Workspace Sidebar that does
# not exist on this site, so it renders as a dead tile if shown. The hidden flag
# used to live in an untracked people.json inside the hrms app; it belongs here.
HIDDEN_DESKTOP_ICONS = ["People"]


def add_hr_workspace_links() -> None:
	for workspace, card, doctype, after in WORKSPACE_LINKS:
		try:
			_ensure_link(workspace, card, doctype, after)
		except Exception:
			# A missing workspace or a renamed card must never break a migration.
			frappe.log_error(
				title="beveren_health: HR workspace link skipped",
				message=f"{workspace} / {card} / {doctype}\n{frappe.get_traceback()}",
			)

	hide_desktop_icons()


def hide_desktop_icons() -> None:
	"""Keep our hidden desk tiles hidden after hrms re-syncs its icons.

	Uses db.set_value rather than a document save: saving a standard Desktop Icon
	in developer_mode would export it straight back into the hrms app, which is
	how the stray people.json got there in the first place.
	"""
	changed = False
	for icon in HIDDEN_DESKTOP_ICONS:
		if not frappe.db.exists("Desktop Icon", icon):
			continue
		if not frappe.db.get_value("Desktop Icon", icon, "hidden"):
			frappe.db.set_value("Desktop Icon", icon, "hidden", 1)
			changed = True

	if changed:
		frappe.db.commit()
		# Desktop icons are cached per user; drop it so the change actually boots.
		frappe.cache.delete_key("desktop_icons")


def _ensure_link(workspace: str, card: str, doctype: str, after: str) -> None:
	if not frappe.db.exists("Workspace", workspace):
		return
	if not frappe.db.exists("DocType", doctype):
		return

	ws = frappe.get_doc("Workspace", workspace)
	if any(l.link_to == doctype for l in ws.links):
		return

	rows = []
	for link in ws.links:
		row = link.as_dict()
		for key in ("name", "parent", "parentfield", "parenttype", "creation", "modified",
		            "modified_by", "owner", "docstatus", "idx"):
			row.pop(key, None)
		rows.append(row)

	# Place it inside the right card: after the named link, else at the card's end.
	insert_at, in_card = None, False
	for i, row in enumerate(rows):
		if row.get("type") == "Card Break":
			if in_card and insert_at is None:
				insert_at = i
			in_card = row.get("label") == card
			continue
		if in_card and row.get("link_to") == after:
			insert_at = i + 1
	if insert_at is None:
		insert_at = len(rows)

	rows.insert(insert_at, {
		"type": "Link",
		"label": doctype,
		"link_type": "DocType",
		"link_to": doctype,
		"onboard": 0,
		"is_query_report": 0,
		"hidden": 0,
	})

	ws.links = []
	for row in rows:
		ws.append("links", row)
	ws.flags.ignore_permissions = True
	ws.flags.ignore_links = True

	# Workspace.on_update exports the record back to its owning app's JSON when
	# developer_mode is on. That would write our link into hrms/ - dirtying a
	# third-party repo and losing it on the next hrms upgrade. The DB change is
	# what we want; the export is not.
	developer_mode = frappe.conf.developer_mode
	try:
		frappe.conf.developer_mode = 0
		ws.save(ignore_permissions=True)
	finally:
		frappe.conf.developer_mode = developer_mode

	frappe.db.commit()
