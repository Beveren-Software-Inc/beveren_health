# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

"""Restrict the desk workspace grid for clinical / healthcare staff.

A user holding any of the healthcare roles below (and who is not exempt) sees
only the "Healthcare" desktop icon and its Healthcare workspace sidebar. Users
who also hold the "Employee" role additionally keep the "Frappe HR" icon and
its nested workspaces (Leaves, Expenses, Payroll, ...) so every employee can
reach HR self-service. Every other desktop icon and sidebar is pruned from
that user's boot payload.

Wired through the ``extend_bootinfo`` hook, which frappe runs on every boot --
including cached ones -- so the prune is applied consistently even though
``bootinfo.desktop_icons`` is built and cached earlier in ``get_bootinfo``.
"""

import frappe

# Roles whose users are locked to the Healthcare app only.
RESTRICTED_ROLES = frozenset(
    {
        "Doctor",
        "Physician",
        "Nurse",
        "Nursing User",
        "Psychologist",
        "Anesthesiologist",
        "Receptionist",
        "Reception",
        "Laboratory User",
        "LabTest Approver",
        "Psychiatrist",
        "Occupational Therapist",
        "Nutritionist",
        "Insurance",
    }
)

# Roles that keep full access even if the user also holds a restricted role.
# (Administrator is always exempt, separately.)
EXEMPT_ROLES = frozenset({"System Manager"})

# The desktop icon (and everything nested under it) that always stays visible.
KEEP_ICON_ROOT = "Healthcare"

# Users holding this role additionally keep the Frappe HR icon tree.
EMPLOYEE_ROLE = "Employee"
HR_ICON_ROOT = "Frappe HR"

# Workspace Sidebar keys (lowercased titles) that always stay in the boot map.
# Keys for kept icons (e.g. Frappe HR children) are derived from their labels.
KEEP_SIDEBAR_KEYS = frozenset({"healthcare"})


def restrict_healthcare_sidebar(bootinfo=None):
    """``extend_bootinfo`` hook: prune desk icons/sidebars for healthcare staff."""
    if bootinfo is None:
        return

    if _is_exempt() or not _has_restricted_role():
        return

    keep_roots = {KEEP_ICON_ROOT}
    if EMPLOYEE_ROLE in frappe.get_roles():
        keep_roots.add(HR_ICON_ROOT)

    kept_icons = _icons_rooted_at(bootinfo.get("desktop_icons") or [], keep_roots)
    bootinfo.desktop_icons = kept_icons

    keep_sidebar_keys = set(KEEP_SIDEBAR_KEYS) | {
        (icon.get("label") or "").lower() for icon in kept_icons
    }
    bootinfo.workspace_sidebar_item = {
        key: value
        for key, value in (bootinfo.get("workspace_sidebar_item") or {}).items()
        if key in keep_sidebar_keys
    }


def _is_exempt():
    if frappe.session.user == "Administrator":
        return True
    return bool(EXEMPT_ROLES.intersection(frappe.get_roles()))


def _has_restricted_role():
    return bool(RESTRICTED_ROLES.intersection(frappe.get_roles()))


def _icons_rooted_at(icons, keep_roots):
    """Keep only icons whose parent chain reaches one of ``keep_roots``."""
    by_label = {icon.get("label"): icon for icon in icons if icon.get("label")}
    return [icon for icon in icons if _rooted_at(icon, by_label, keep_roots)]


def _rooted_at(icon, by_label, keep_roots):
    """Walk the parent chain; True if this icon is a keep-root or a descendant."""
    current = icon
    seen = set()
    while current:
        if current.get("label") in keep_roots:
            return True
        parent = current.get("parent_icon")
        if not parent or parent in seen:
            return False
        seen.add(parent)
        current = by_label.get(parent)
    return False


def create_restricted_roles():
    """Create the healthcare roles that don't ship with any installed app.

    Idempotent; safe to run repeatedly (e.g. from ``after_migrate``).
    """
    for role_name in ("Psychiatrist", "Occupational Therapist", "Nutritionist", "Insurance"):
        if frappe.db.exists("Role", role_name):
            continue
        frappe.get_doc(
            {
                "doctype": "Role",
                "role_name": role_name,
                "desk_access": 1,
            }
        ).insert(ignore_permissions=True)
    frappe.db.commit()
