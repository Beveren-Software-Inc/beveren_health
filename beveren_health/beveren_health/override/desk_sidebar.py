# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

"""Restrict the desk workspace grid for clinical / healthcare staff.

A user holding any of the healthcare roles below (and who is not exempt) sees
only the "Healthcare" desktop icon and its Healthcare workspace sidebar. Every
other desktop icon and sidebar is pruned from that user's boot payload.

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
        "Pharmacy",
        "Phamarcist",  # (misspelled in the system; kept as-is on purpose)
        # Created by create_restricted_roles() below -- did not exist as roles yet.
        "Psychiatrist",
        "Occupational Therapist",
        "Nutritionist",
        "Insurance",
    }
)

# Roles that keep full access even if the user also holds a restricted role.
# (Administrator is always exempt, separately.)
EXEMPT_ROLES = frozenset({"System Manager"})

# The single desktop icon (and everything nested under it) that stays visible.
KEEP_ICON_ROOT = "Healthcare"

# Workspace Sidebar keys (lowercased titles) that stay in the boot map.
KEEP_SIDEBAR_KEYS = frozenset({"healthcare"})


def restrict_healthcare_sidebar(bootinfo=None):
    """``extend_bootinfo`` hook: prune desk icons/sidebars for healthcare staff."""
    if bootinfo is None:
        return

    if _is_exempt() or not _has_restricted_role():
        return

    bootinfo.desktop_icons = _healthcare_icons_only(bootinfo.get("desktop_icons") or [])
    bootinfo.workspace_sidebar_item = {
        key: value
        for key, value in (bootinfo.get("workspace_sidebar_item") or {}).items()
        if key in KEEP_SIDEBAR_KEYS
    }


def _is_exempt():
    if frappe.session.user == "Administrator":
        return True
    return bool(EXEMPT_ROLES.intersection(frappe.get_roles()))


def _has_restricted_role():
    return bool(RESTRICTED_ROLES.intersection(frappe.get_roles()))


def _healthcare_icons_only(icons):
    """Keep only the Healthcare icon and anything nested beneath it."""
    by_label = {icon.get("label"): icon for icon in icons if icon.get("label")}
    return [icon for icon in icons if _rooted_at_healthcare(icon, by_label)]


def _rooted_at_healthcare(icon, by_label):
    """Walk the parent chain; True if this icon is Healthcare or a descendant."""
    current = icon
    seen = set()
    while current:
        if current.get("label") == KEEP_ICON_ROOT:
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
