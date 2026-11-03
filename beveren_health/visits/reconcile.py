"""
03_reconcile_visits.py
======================
Compares Oracle visits (VISIT_00_01) with ERPNext visits and imports the ones
missing in ERPNext.

MATCHING IS NOT ID-ONLY. Order of evidence:
  1. exact Oracle id  (ERPNext field holds VISIT_NUM)            -> confidence 100
  2. patient + DATE must both match (hard requirement)
     then scored on: doctor +40, visit type +20, branch +10, day ordinal +20
  3. if a patient has exactly one visit on a date on both sides  -> matched (70)

TIME IS DELIBERATELY IGNORED. Oracle stores 139 074 of 139 075 visits as
00:00:00, so a clock comparison would be meaningless. The date is authoritative.

RUN
    bench --site <site> console
    >>> exec(open("/path/to/03_reconcile_visits.py").read())
    >>> visit_recon(csv_path="/tmp/visits.csv", patient="849995")              # report
    >>> visit_recon(csv_path="/tmp/visits.csv", patient="849995", commit=True) # import
"""

import csv
import os

import frappe

# ===========================================================================
# CONFIG - confirm with 00_discover_erpnext.py
# ===========================================================================
CONFIG = {
    # ERPNext doctype that represents a visit
    "visit_doctype": "Patient Visit",
    "visit_patient_field": "patient",
    "visit_date_field": "encounter_date",
    "visit_practitioner_field": "practitioner",
    # optional: fields that hold the Oracle visit type / branch mirror
    "visit_type_field": "visit_type",
    "visit_branch_field": None,
    # field that stores the Oracle VISIT_NUM (create it if absent).
    # On serene this is "case_no", which is also the autoname field -> the
    # imported doc gets the Oracle visit number as its NAME.
    "visit_oracle_id_field": "case_no",
    # field that stores the Oracle VISIT_PATIENT_SERIAL (order within a day)
    "visit_serial_field": "patient_serial",
    "visit_oracle_type_field": "custom_oracle_visit_type",
    "visit_oracle_branch_field": "custom_oracle_branch",
    # import behaviour
    #   "safe" = skip any visit whose (patient, date) already has an ERPNext visit
    #   "all"  = import every Oracle-only visit
    "import_scope": "safe",
    # values stamped on every imported visit
    "import_defaults": {
        "status": "Completed",
        "encounter_time": "00:00:00",
        "company": "Serene Psychiatry Hospital",
    },
    # link visit_type to a Patient Visit Type when the Oracle name matches
    "map_visit_type_on_import": True,
    # Oracle side: which CSV column to compare visit type on when
    # CONFIG["visit_type_field"] is set - "visit_type_num" or "visit_type_nam"
    "oracle_type_key": "visit_type_nam",
    # patient mapping
    "patient_doctype": "Patient",
    "patient_file_no_field": "name",
    # practitioner mapping: Oracle VISIT_DOCTOR_NUM -> Healthcare Practitioner
    # set to None to skip doctor scoring (weight becomes 0)
    "practitioner_doctype": "Healthcare Practitioner",
    "practitioner_oracle_field": None,
    # True when the visit's practitioner field already holds the Oracle doctor
    # number itself (on serene, Healthcare Practitioner docnames ARE Oracle nums)
    "practitioner_is_oracle_id": True,
}
MIN_SCORE = 40
SINGLE_DAY_CONFIDENCE = 70
# the full result of the last report run (lists, not counts) - for diagnosis
LAST_RESULT = None

# ===========================================================================
# pure matching logic (no frappe calls - unit tested)
# ===========================================================================
WEIGHTS = {"doctor": 40, "type": 20, "branch": 10, "ordinal": 20}


def _n(v):
    return "" if v is None else str(v).strip()


def _norm_txt(v):
    """Case/space-insensitive key: "Daily Auto Visit" == "DAILY AUTO VISIT"."""
    return " ".join(_n(v).upper().split())


def score_pair(o, e, weights=None):
    """Score one Oracle visit against one ERPNext visit (same patient + date)."""
    w = weights or WEIGHTS
    s = 0
    if w.get("doctor") and _n(o.get("doctor")) and _n(o.get("doctor")) == _n(e.get("doctor")):
        s += w["doctor"]
    if w.get("type") and _n(o.get("type")) and _n(o.get("type")) == _n(e.get("type")):
        s += w["type"]
    if w.get("branch") and _n(o.get("branch")) and _n(o.get("branch")) == _n(e.get("branch")):
        s += w["branch"]
    if w.get("ordinal") and _n(o.get("ordinal")) and _n(o.get("ordinal")) == _n(e.get("ordinal")):
        s += w["ordinal"]
    return s


def match_reason(o, e, weights=None):
    w = weights or WEIGHTS
    bits = []
    for key, label in (("doctor", "doctor"), ("type", "type"),
                       ("branch", "branch"), ("ordinal", "order-in-day")):
        if w.get(key) and _n(o.get(key)) and _n(o.get(key)) == _n(e.get(key)):
            bits.append(label)
    return "+".join(bits) or "patient+date"


def match_group(oracle_rows, erp_rows, weights=None, min_score=MIN_SCORE):
    """Match Oracle visits to ERPNext visits that fall on the same patient-day.

    Returns (pairs, oracle_leftover, erpnext_leftover).
    """
    w = weights or WEIGHTS
    oracle_rows = list(oracle_rows)
    erp_rows = list(erp_rows)

    # one visit on each side for this patient-day -> same visit, no ambiguity
    if len(oracle_rows) == 1 and len(erp_rows) == 1:
        o, e = oracle_rows[0], erp_rows[0]
        return [{"o": o, "e": e,
                 "score": max(SINGLE_DAY_CONFIDENCE, score_pair(o, e, w)),
                 "reason": "only visit on this patient-day"}], [], []

    cands = []
    for o in oracle_rows:
        for e in erp_rows:
            s = score_pair(o, e, w)
            if s >= min_score:
                cands.append((s, o, e))

    # strongest first; ties resolved deterministically by order-in-day then name
    cands.sort(key=lambda t: (-t[0], _n(t[1].get("ordinal")), _n(t[2].get("name"))))

    used_o, used_e, pairs = set(), set(), []
    for s, o, e in cands:
        if id(o) in used_o or id(e) in used_e:
            continue
        used_o.add(id(o))
        used_e.add(id(e))
        pairs.append({"o": o, "e": e, "score": s, "reason": match_reason(o, e, w)})

    left_o = [o for o in oracle_rows if id(o) not in used_o]
    left_e = [e for e in erp_rows if id(e) not in used_e]
    return pairs, left_o, left_e


def group_by_patient_day(rows):
    out = {}
    for r in rows:
        out.setdefault((_n(r.get("patient")), _n(r.get("date"))), []).append(r)
    return out


# ===========================================================================
# data loading
# ===========================================================================
def _chunks(seq, n=200):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return [{(k or "").strip(): (v.strip() if isinstance(v, str) else v)
                 for k, v in row.items()} for row in csv.DictReader(fh)]


def _oracle_rows(csv_path):
    rows = []
    type_key = CONFIG.get("oracle_type_key") or "visit_type_num"
    for r in _read_csv(csv_path):
        rows.append({
            "id": _n(r.get("visit_num")),
            "patient": _n(r.get("visit_patient_num")),
            "date": _n(r.get("visit_date"))[:10],
            "doctor": _n(r.get("visit_doctor_num")),
            "type": _norm_txt(r.get(type_key)),
            "branch": _n(r.get("branch_num")),
            "ordinal": _n(r.get("day_ordinal")),
            "type_nam": _n(r.get("visit_type_nam")),
            "serial": _n(r.get("visit_patient_serial")),
            "time": _n(r.get("visit_time_raw"))[:8],
        })
    return rows


def _patient_map(file_nos):
    field = CONFIG["patient_file_no_field"]
    if field == "name":
        # docname IS the file number (serene: Patient.name = Oracle patient num)
        out = {}
        for chunk in _chunks(file_nos):
            for r in frappe.get_all(CONFIG["patient_doctype"],
                                    filters={"name": ("in", chunk)},
                                    fields=["name"], limit_page_length=0):
                out[_n(r["name"])] = r["name"]
        return out
    meta = frappe.get_meta(CONFIG["patient_doctype"])
    if not meta.has_field(field):
        frappe.throw("Patient has no field %r - fix CONFIG['patient_file_no_field']." % field)
    out = {}
    for chunk in _chunks(file_nos):
        for r in frappe.get_all(CONFIG["patient_doctype"], filters={field: ("in", chunk)},
                                fields=[field, "name"], limit_page_length=0):
            out[_n(r[field])] = r["name"]
    return out


def _practitioner_map():
    field = CONFIG["practitioner_oracle_field"]
    if not field:
        return {}
    meta = frappe.get_meta(CONFIG["practitioner_doctype"])
    if not meta.has_field(field):
        print("  ! practitioner field %r missing - doctor scoring disabled" % field)
        return {}
    out = {}
    for r in frappe.get_all(CONFIG["practitioner_doctype"], fields=["name", field],
                            limit_page_length=0):
        if r.get(field):
            out[r["name"]] = _n(r[field])
    return out


def _weights():
    """Only score on metrics this site can actually provide."""
    w = {"doctor": 0, "type": 0, "branch": 0, "ordinal": 20}
    if CONFIG["practitioner_oracle_field"] or CONFIG.get("practitioner_is_oracle_id"):
        w["doctor"] = WEIGHTS["doctor"]
    w["type"] = WEIGHTS["type"] if CONFIG["visit_type_field"] else 0
    w["branch"] = WEIGHTS["branch"] if CONFIG["visit_branch_field"] else 0
    return w


def _load_erp_visits(patient_names):
    """-> {patient_name: [visit dicts]} with an order-in-day ordinal."""
    out = {}
    fields = ["name", CONFIG["visit_patient_field"], CONFIG["visit_date_field"]]
    for field in (CONFIG["visit_practitioner_field"], CONFIG["visit_oracle_id_field"],
                  CONFIG["visit_type_field"], CONFIG["visit_branch_field"]):
        if field and field not in fields:
            fields.append(field)

    pmap = _practitioner_map()
    direct_doctor = bool(CONFIG.get("practitioner_is_oracle_id"))
    for chunk in _chunks(patient_names):
        for r in frappe.get_all(CONFIG["visit_doctype"],
                                filters={CONFIG["visit_patient_field"]: ("in", chunk)},
                                fields=fields, limit_page_length=0):
            pat = r[CONFIG["visit_patient_field"]]
            raw_doc = r.get(CONFIG["visit_practitioner_field"]) or ""
            out.setdefault(pat, []).append({
                "name": r["name"],
                "patient": pat,
                "date": _n(r[CONFIG["visit_date_field"]])[:10],
                "doctor": _n(raw_doc) if direct_doctor else pmap.get(raw_doc, ""),
                "type": _norm_txt(r.get(CONFIG["visit_type_field"])) if CONFIG["visit_type_field"] else "",
                "branch": _n(r.get(CONFIG["visit_branch_field"])) if CONFIG["visit_branch_field"] else "",
                "oracle_id": _n(r.get(CONFIG["visit_oracle_id_field"])) if CONFIG["visit_oracle_id_field"] else "",
            })

    # order-in-day: by name (deterministic); Oracle order comes from VISIT_NUM
    for visits in out.values():
        visits.sort(key=lambda v: (v["date"], v["name"]))
        counter = {}
        for v in visits:
            counter[v["date"]] = counter.get(v["date"], 0) + 1
            v["ordinal"] = str(counter[v["date"]])
    return out


# ===========================================================================
# reconciliation
# ===========================================================================
def reconcile(csv_path, patient=None, commit=False, limit=None):
    global LAST_RESULT
    if not os.path.exists(csv_path):
        frappe.throw("CSV not found: %s (export with sql/03_visit_export.sql)" % csv_path)

    oracle = _oracle_rows(csv_path)
    if patient:
        oracle = [o for o in oracle if o["patient"] == _n(patient)]
    if limit:
        oracle = oracle[:int(limit)]
    if not oracle:
        print("No Oracle visits in scope.")
        return {}

    file_to_name = _patient_map(sorted({o["patient"] for o in oracle}))
    name_to_file = {v: k for k, v in file_to_name.items()}
    erp_visits = _load_erp_visits(list(file_to_name.values()))

    erp_rows = []
    for pname, visits in erp_visits.items():
        fno = name_to_file.get(pname)
        if not fno:
            continue
        for v in visits:
            v["file"] = fno
            erp_rows.append(v)

    print("Oracle visits in scope: %d | patients: %d | ERPNext visits found: %d"
          % (len(oracle), len(file_to_name), len(erp_rows)))

    pmap_rev = {v: k for k, v in _practitioner_map().items()}

    res = {"matched_by_id": [], "matched_by_score": [], "oracle_only": [], "erp_only": [],
           "id_conflicts": []}
    used = set()
    by_id = {}
    for v in erp_rows:
        if v.get("oracle_id"):
            by_id.setdefault(v["oracle_id"], v)

    pending = []
    for o in oracle:
        ev = by_id.get(o["id"])
        # An Oracle visit number belongs to ONE patient. If ERPNext stores that
        # number on a visit of a different patient, the two are NOT the same
        # visit - matching them would hide a missing visit and fake a match.
        # Leave both free and remember the clash for the report.
        if ev is not None and ev["file"] != o["patient"]:
            res["id_conflicts"].append({
                "oracle": o, "erp": ev,
                "reason": "ERPNext visit %s (patient %s, %s) carries Oracle visit "
                          "number %s but Oracle gives patient %s (%s)"
                          % (ev["name"], ev["file"], ev["date"], o["id"],
                             o["patient"], o["date"]),
            })
            ev = None
        if ev is not None and id(ev) not in used:
            used.add(id(ev))
            res["matched_by_id"].append({"o": o, "e": ev, "score": 100, "reason": "oracle id"})
        else:
            pending.append(o)

    w = _weights()
    o_groups = group_by_patient_day(pending)
    e_groups = {}
    for v in erp_rows:
        if id(v) in used:
            continue
        e_groups.setdefault((v["file"], v["date"]), []).append(v)

    for key, orows in o_groups.items():
        pairs, left_o, _left_e = match_group(orows, e_groups.get(key, []), w)
        for p in pairs:
            used.add(id(p["e"]))
            res["matched_by_score"].append(p)
        res["oracle_only"].extend(left_o)

    for v in erp_rows:
        if id(v) not in used:
            res["erp_only"].append(v)

    LAST_RESULT = res

    print("\nMatch result:")
    print("  matched by Oracle id     : %d" % len(res["matched_by_id"]))
    print("  matched by patient+date  : %d" % len(res["matched_by_score"]))
    print("  in Oracle, MISSING in ERP: %d  <-- these get imported" % len(res["oracle_only"]))
    print("  in ERPNext, not in Oracle: %d  <-- reported only, never deleted"
          % len(res["erp_only"]))
    print("  import scope             : %s%s"
          % (CONFIG.get("import_scope") or "safe",
             "  (visits whose patient-day already has an ERPNext visit are skipped)"
             if (CONFIG.get("import_scope") or "safe") != "all" else ""))

    if res["matched_by_score"]:
        buckets = {}
        for p in res["matched_by_score"]:
            buckets[p["reason"]] = buckets.get(p["reason"], 0) + 1
        print("\n  how the patient+date matches were decided:")
        for reason, n in sorted(buckets.items(), key=lambda x: -x[1]):
            print("     %-40s %d" % (reason, n))

    if res["oracle_only"]:
        by_type = {}
        for o in res["oracle_only"]:
            k = o["type_nam"] or o["type"]
            by_type[k] = by_type.get(k, 0) + 1
        print("\n  missing visits by Oracle visit type:")
        for t, n in sorted(by_type.items(), key=lambda x: -x[1]):
            print("     %-30s %d" % (t, n))

    if res.get("id_conflicts"):
        print("\n  WARNING - %d Oracle visit number(s) sit on an ERPNext visit of a "
              "DIFFERENT patient:" % len(res["id_conflicts"]))
        for c in res["id_conflicts"][:10]:
            print("     %s" % c["reason"])
        if len(res["id_conflicts"]) > 10:
            print("     ... %d more" % (len(res["id_conflicts"]) - 10))
        print("     (these are NOT counted as matched; fix the wrong case_no in ERPNext "
              "or import by hand)")

    if not commit:
        print("\nREPORT ONLY - nothing written. Re-run with commit=True to import.")
        return _summary(res)
    return _do_import(res, file_to_name, pmap_rev, erp_rows)


def _do_import(res, file_to_name, pmap_rev, erp_rows=None):
    id_field = CONFIG["visit_oracle_id_field"]
    meta = frappe.get_meta(CONFIG["visit_doctype"])
    scope = CONFIG.get("import_scope") or "safe"

    def _has(field):
        return bool(field) and meta.has_field(field)

    # one bulk lookup instead of one exists() per row (13 908 rows on a full run).
    # keep the owning patient: the same Oracle number on another patient is a clash,
    # not "already imported".
    existing = {}   # oracle id -> patient docname that holds it in ERPNext
    if id_field and res["oracle_only"]:
        ids = [o["id"] for o in res["oracle_only"]]
        for chunk in _chunks(ids, 500):
            for r in frappe.get_all(CONFIG["visit_doctype"],
                                    filters={id_field: ("in", chunk)},
                                    fields=[id_field, CONFIG["visit_patient_field"]],
                                    limit_page_length=0):
                existing.setdefault(_n(r.get(id_field)),
                                    r.get(CONFIG["visit_patient_field"]))

    # "safe" mode never puts a second visit on a patient-day that already has one
    busy_days = {(v["file"], v["date"]) for v in (erp_rows or [])} if scope != "all" else set()

    # only link to practitioners / visit types that really exist
    valid_pract = set()
    if (CONFIG["practitioner_oracle_field"] or CONFIG.get("practitioner_is_oracle_id")):
        valid_pract = {_n(r["name"]) for r in frappe.get_all(
            CONFIG["practitioner_doctype"], fields=["name"], limit_page_length=0)}
    type_map = {}
    type_field = CONFIG.get("visit_type_field")
    if CONFIG.get("map_visit_type_on_import") and _has(type_field):
        field_obj = meta.get_field(type_field) if hasattr(meta, "get_field") else None
        type_doctype = getattr(field_obj, "options", None)
        if type_doctype and frappe.db.exists("DocType", type_doctype):
            for r in frappe.get_all(type_doctype, fields=["name"], limit_page_length=0):
                type_map[_norm_txt(r["name"])] = r["name"]

    created, failed, skipped, no_patient, same_day, id_conflict = 0, 0, 0, 0, 0, 0
    for o in res["oracle_only"]:
        pname = file_to_name.get(o["patient"])
        if not pname:
            no_patient += 1
            continue
        if id_field and o["id"] in existing:
            if existing[o["id"]] == pname:
                skipped += 1
            else:
                # the number is taken by another patient's visit - inserting would
                # create a second document with the same name (or worse, a duplicate)
                id_conflict += 1
            continue
        if busy_days and (o["patient"], o["date"]) in busy_days:
            same_day += 1
            continue
        try:
            values = {"doctype": CONFIG["visit_doctype"],
                      CONFIG["visit_patient_field"]: pname,
                      CONFIG["visit_date_field"]: o["date"]}
            values.update(CONFIG.get("import_defaults") or {})
            if _has(id_field):
                values[id_field] = o["id"]
            if _has(CONFIG["visit_oracle_type_field"]):
                values[CONFIG["visit_oracle_type_field"]] = o["type_nam"] or o["type"]
            if _has(CONFIG["visit_oracle_branch_field"]):
                values[CONFIG["visit_oracle_branch_field"]] = o["branch"]
            if _has(CONFIG.get("visit_serial_field")) and o.get("serial"):
                values[CONFIG["visit_serial_field"]] = o["serial"]
            if type_map and o.get("type_nam"):
                vt = type_map.get(_norm_txt(o["type_nam"]))
                if vt:
                    values[CONFIG["visit_type_field"]] = vt
            pract = o["doctor"] if CONFIG.get("practitioner_is_oracle_id") \
                else pmap_rev.get(o["doctor"])
            if pract and CONFIG["visit_practitioner_field"] and _has(CONFIG["visit_practitioner_field"]) \
                    and (not valid_pract or pract in valid_pract):
                values[CONFIG["visit_practitioner_field"]] = pract
            doc = frappe.get_doc(values)
            doc.flags.ignore_permissions = True
            doc.flags.from_legacy_import = True
            doc.insert(ignore_permissions=True)
            if id_field:
                existing[o["id"]] = pname
            created += 1
        except Exception:
            failed += 1
            frappe.log_error(frappe.get_traceback(), "visit reconcile %s" % o["id"])
        if created and created % 500 == 0:
            frappe.db.commit()
            print("  ... %d visits imported" % created)

    frappe.db.commit()
    print("\nDONE - %d imported, %d already there, %d skipped (patient already has a visit "
          "that day), %d patient missing, %d visit number taken by another patient, "
          "%d failed."
          % (created, skipped, same_day, no_patient, id_conflict, failed))
    out = _summary(res)
    out.update({"imported": created, "skipped": skipped, "failed": failed,
                "skipped_same_day": same_day, "skipped_no_patient": no_patient,
                "skipped_id_conflict": id_conflict})
    return out


def _summary(res):
    return {
        "matched_by_id": len(res["matched_by_id"]),
        "matched_by_score": len(res["matched_by_score"]),
        "oracle_only": len(res["oracle_only"]),
        "erp_only": len(res["erp_only"]),
        "id_conflicts": len(res.get("id_conflicts") or []),
    }


visit_recon = reconcile


# ===========================================================================
# button endpoints (called by visit_reconcile_button.js)
# ===========================================================================
def _csv_path(csv_path=None):
    return (csv_path or frappe.conf.get("oracle_visit_csv")
            or os.path.join(frappe.get_site_path("private", "visits"),
                            "visits.csv"))


@frappe.whitelist()
def visit_recon_counts(csv_path=None, patient=None):
    """Dry run - counts only, nothing written."""
    return reconcile(_csv_path(csv_path), patient=patient, commit=False)


@frappe.whitelist()
def visit_recon_import(csv_path=None, patient=None, limit=None):
    """Import the Oracle visits that are missing in ERPNext."""
    return reconcile(_csv_path(csv_path), patient=patient, commit=True, limit=limit)


def visit_recon_job(csv_path=None):
    """Background entry point for a whole-database run."""
    return reconcile(_csv_path(csv_path), commit=True)


@frappe.whitelist()
def visit_recon_import_all(csv_path=None):
    # pass the dotted path, not the function object: RQ needs to resolve it by name
    frappe.enqueue("%s.visit_recon_job" % __name__, queue="long", timeout=7200,
                   csv_path=_csv_path(csv_path))
    return {"queued": True}
