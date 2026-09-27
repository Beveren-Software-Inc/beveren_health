# Beveren Health — Operations Guide

Install, configure, run and maintain the app on a site.

* Process manuals: [user_manual.md](user_manual.md), [user_manual_stock.md](user_manual_stock.md),
  [user_manual_accounts.md](user_manual_accounts.md)
* Technical reference: [reference/hooks_and_api.md](reference/hooks_and_api.md),
  [reference/customizations.md](reference/customizations.md)

## 1. Install and upgrade

```bash
# first install
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/<org>/beveren_health --branch develop
bench --site <site> install-app beveren_health
bench --site <site> migrate
bench build

# upgrade an installed site
cd apps/beveren_health && git pull
cd ../.. && bench --site <site> migrate && bench build
```

Requirements: `frappe`/`erpnext` v16, `hrms`, `healthcare`, Python ≥ 3.10 and
`python-barcode == 0.15.1` (declared in `pyproject.toml`).

Everything the app adds is re-applied on every `bench migrate`:

* **Custom Fields / Property Setters** from `beveren_health/beveren_health/custom/*.json`
  (Frappe's `sync_customizations`).
* **Fixtures** — `TNA Template`, the *Employee* naming-series Property Setter, the Appraisal /
  feedback grid Property Setters and 47 scanning/label/GTIN Custom Fields. (Note:
  `fixtures/property_setter.json` is currently empty — the Property Setters that matter live in
  `custom/*.json`.)
* **`after_migrate` hooks** — HR workspace links, Klik POS artwork, the VAT custom fields and
  the Full-and-Final import helper (see [section 6](#6-full-and-final-import-helpers)).

## 2. Configuration after install

| # | Where | What to set |
| --- | --- | --- |
| 1 | **HR Settings → Indemnity Settings** | *Indemnity Cutoff Date*, *Default Indemnity Expense Account*, *Default Indemnity Payable Account* |
| 2 | **Payroll Settings → GOSI Settings** | *GOSI Salary Component* (a Deduction component) |
| 3 | **Healthcare Settings** | *Default Expiry Warehouse*, *auto_apply_patient_price_list* (tick to switch OP/IP price lists), *add_outstanding_balance_to_full_and_final_settlement* (tick to recover outstanding invoices on FnF), *outstanding_balance_salary_component* (a **Deduction** component) |
| 4 | **Company → VAT Accounts Configurations** | One **VAT Account Configuration** row per VAT ledger with its *VAT Type* |
| 5 | **Company address** | **VAT No.** |
| 6 | **Dispensing Setting** | Tick the document types on which a dispensing lot must be enforced |
| 7 | **Price Lists** | `OP Selling` and `IP Selling` exist, with item rates |
| 8 | **Chart of accounts** | A non-group account with type **Temporary** (needed by the opening-balance helper); VAT ledgers whose names contain `INPUT VAT` / `OUTPUT VAT` |
| 9 | **Employees** | *Is Overtime Payable ?*, *Is Less Time Deductible ?*, *Is Probation Period ?* + days, *Standard Working Hours*, *Visa Status* / *Under GOSI Registered ?*, CPR and NHRA rows in **Documents** |
| 10 | **Print format** | Create/import the *Employee Visa Renewal Consent Form* and, if you use it, run the Medication Label setup (section 7) |

### Master data the app expects

| Doctype | Used by |
| --- | --- |
| **Nationality**, **Religion** | Required fields on Employee |
| **Document Name** (`CPR`, `NHRA`, …) | Employee Documents |
| **Less Time Type**, **Overtime Type** | Less time / overtime engines |
| **Penalty Type** | Employee Penalty |
| **Item Class**, **Item Category** (tree), **Pharmaceutical Form**, **Route of Administration**, **Primary Packing**, **Unit of Strength**, **MAH**, **Batch Releaser**, **Pharmacy Agent**, **Manufacturer** | Item master (Healthcare tab) |
| **Urgency Type**, **PO Type**, **Invoicing Company** | Purchase Order / Item |
| **Additional Salary Type** | Additional Salary *Reason* |
| **Feeding Hours Entitlement** | Nursing-mother attendance |
| **TNA Template**, **TNA Rating Instruction** | Training Need Assessment |

## 3. Settings overview

| Setting | Effect |
| --- | --- |
| Payroll Settings → *GOSI Salary Component* | Appended as a deduction to every **new** Salary Structure |
| HR Settings → Indemnity settings | Defaults for Indemnity (cutoff, accounts) |
| Healthcare Settings → *Default Expiry Warehouse* | Target of the daily expired-batch movement |
| Healthcare Settings → *auto_apply_patient_price_list* | Enables OP/IP price-list switching |
| Healthcare Settings → *add_outstanding_balance_to_full_and_final_settlement* + *outstanding_balance_salary_component* | Outstanding-invoice recovery on Full and Final Statements |
| Dispensing Setting (one toggle per document type) | Where a dispensing lot is mandatory |
| `Auto Save Scan Interval` on each scanning document (default 10) | Saves the form every *N* scans |

## 4. Scheduled jobs

| Frequency | Job | Notes |
| --- | --- | --- |
| Daily | `utils.expiry_movement.move_expired_batches_to_expiry_warehouse` | Needs *Default Expiry Warehouse*; creates Material Transfer Stock Entries |
| Daily | `notifications.employee_notification.notify_expiring_employee_documents` | HR Manager alert + digest email, 90-day window on a 10-day cadence |
| Weekly | `notifications.employee_notification.notify_ending_probation_period` | Alerts `HR User` 30 days before probation ends |
| Hourly (long) | `utils.attendance.update_last_sync_for_all_shifts` | Keeps `last_sync_of_checkin` current so HRMS marks attendance |

Run one manually:

```bash
bench --site <site> execute beveren_health.beveren_health.utils.expiry_movement.trigger_expiry_movement
bench --site <site> execute beveren_health.beveren_health.utils.attendance.trigger_manual_last_sync
```

## 5. Desk customisation

### 5.1 HR workspace links

`after_migrate` re-adds **Employee Checkin Request** to the **HR Setup** and
**Shift & Attendance** workspaces (HRMS re-syncs those workspaces on every migrate, so the link
is re-applied instead of being edited in place) and keeps the **People** desktop tile hidden.
Both are idempotent; failures are logged (*"beveren_health: HR workspace link skipped"*) and
never break a migration.

### 5.2 Klik POS artwork

`after_migrate` also repoints the **KLiK PoS** desktop tile and the **Klik POS** workspace at the
artwork shipped in `public/images/klik_pos_icon.svg` / `public/icons.svg`. When the SVG changes,
bump the `?v=` cache-buster in
`...override.desk_sidebar.set_klik_pos_workspace_icon`.

### 5.3 Desk sidebar restriction for clinical roles

`...override.desk_sidebar.restrict_healthcare_sidebar` prunes the desk grid for clinical staff so
they only see the **Healthcare** workspace (plus **Frappe HR** if they also hold the *Employee*
role, and the **KLiK PoS** tile for pharmacists).

* **Restricted roles**: Doctor, Physician, Nurse, Nursing User, Psychologist, Anesthesiologist,
  Laboratory User, LabTest Approver, Psychiatrist, Occupational Therapist, Nutritionist,
  Insurance, Pharmacist.
* **Exempt**: `System Manager` (Administrator is always exempt). The `Employee` role adds the
  Frappe HR tree back; `Pharmacist` keeps the Klik POS tree.
* **It is currently disabled** — the `extend_bootinfo` hook is commented out in `hooks.py`.
  Uncomment `extend_bootinfo = ["beveren_health.beveren_health.override.desk_sidebar.restrict_healthcare_sidebar"]`
  to switch it on.
* Four of the roles (`Psychiatrist`, `Occupational Therapist`, `Nutritionist`, `Insurance`) do not
  ship with any app; create them with

  ```bash
  bench --site <site> execute beveren_health.beveren_health.override.desk_sidebar.create_restricted_roles
  ```

  (idempotent; also available as a commented-out `after_migrate` entry).

## 6. Full and Final import helpers

`scripts/create_fnf_from_xlsx.py` recreates the reference deployment's leaver settlements from the
HR workbook: it creates/keeps the **Employee**, then for each record creates the **Indemnity**,
the supporting **Additional Salary** rows (OT / Bonus / Salary / Leave Encashment), an
**Employee Advance** reference when one exists, and finally the **Full and Final Statement** with
correctly referenced payable rows. It also configures the Indemnity accounts and cutoff date in
HR Settings.

```bash
bench --site <site> execute beveren_health.scripts.create_fnf_from_xlsx.run
bench --site <site> execute beveren_health.scripts.cleanup_fnf.run   # delete script-created docs before a re-run
```

> **Important for other sites.** This script is wired into `after_migrate` in `hooks.py`, and its
> data (`FNF_DATA`), company (`Serene Psychiatry Hospital`), cost center, currency and account
> names are **hard-coded for the reference deployment**. On any other site it will try to create
> those employees (and overwrite the HR Settings indemnity accounts). Remove the
> `beveren_health.scripts.create_fnf_from_xlsx.run` line from `hooks.after_migrate` (or empty
> `FNF_DATA`) before installing elsewhere. It is idempotent — existing Employees, Indemnities,
> Additional Salaries and Full and Final Statements are detected and skipped.

`cleanup_fnf.run` is destructive (it empties `tabFull and Final Statement`,
`tabFull and Final Outstanding Statement`, Indemnity GL entries, `tabIndemnity`, and the
`HR-ENC%` / `HR-ADS-26-06%` documents) — use it only on the migration site.

## 7. Other maintenance commands

```bash
# Create the "Medication Label" print format for Purchase Receipt (Jinja)
bench --site <site> execute beveren_health.beveren_health.utils.print_format_setup.setup_print_format

# Generate EAN-13 barcodes/images for batches that have none
bench --site <site> execute beveren_health.beveren_health.utils.batch.generate_barcode_for_existing_batches

# Regenerate one batch's barcode image
bench --site <site> execute beveren_health.beveren_health.utils.batch.regenerate_barcode_image_for_batch \
  --kwargs "{'batch_name': 'BATCH-0001'}"
```

The Medication Label print format is **not** created automatically (the `after_install` hook is
commented out). Batch/medication labels printed from the desk (Batch → *Actions → Label Print*
and the *Batch Label Print* actions) build their HTML client-side and do not need it; the print
format is for printing the same label from the Purchase Receipt document itself.

### Optional: overtime patient-visit fields

`customize/overtime_allowance.validate` only runs when the Overtime Slip has the
`custom_patient_visit_allowance` field. The counts/rates fields
(`custom_bring_patients_count`, `custom_bring_patient_rate`, `custom_bring_patients_no_show_count`,
`custom_bring_patient_no_show_rate`, `custom_home_visit_count`, `custom_home_visit_rate`,
`custom_patient_visit_allowance`) are **not** shipped in `custom/overtime_slip.json`, so create
them once with **Customize Form → Overtime Slip**; the hook no-ops while they are missing.

### Print format for visa renewal

`print_format/employee_visa_renewal_consent_form/` ships only its `.json` metadata (no
`__init__.py`), so Frappe does not import it on install. Recreate it per site with
**Print Format → New**: DocType *Employee Visa Renewal Consent*, name
*Employee Visa Renewal Consent Form*, and the layout your HR team signs (the `.json` in the repo
documents the intended fields and settings).

## 8. Testing and CI

### Running tests

```bash
bench --site <site> set-config allow_tests true
bench --site <site> run-tests --app beveren_health
```

`bench run-tests` calls **`beveren_health.install.before_tests`** through the `before_tests` hook,
before any integration test (and therefore before the framework creates its test records). It
clears the `reqd` flag of the app's shipped customizations on:

| Doctype | Fields |
| --- | --- |
| Employee | `custom_nationality`, `custom_religion`, `employee_number`, `designation` |
| Shift Type | `holiday_list` |

Those flags are HR's rules for live records, but the synthetic records the framework raises
(`erpnext.tests.utils.BootStrapTestData`, `make_employee`, HRMS' `Day Shift` test record) do not
fill them in, so on an installed site the run aborted with a `MandatoryError` before a single
test executed. The cleared flags are committed (integration teardown rolls back), so they stay
cleared for the whole run; a following `bench migrate` (or re-install) applies the shipped
customization files again and restores them.

### CI

`.github/workflows/ci.yml` runs two jobs:

* **Server** — on `develop`, pull requests and manual runs: a fresh bench on Python 3.14 /
  Node 24, `erpnext` + `hrms` + `healthcare` + `beveren_health` on `version-16`, `bench build`,
  then `bench --site test_site run-tests --app beveren_health`.
* **Linters** — `pre-commit run semgrep --all-files` with a baseline commit, so only findings
  newly introduced by the change fail. A commit message containing `[skip semgrep]` skips it
  (used for one-off reformat commits).

Local pre-commit (`pre-commit install`) runs ruff (imports, lint, format), prettier
(**JS/Vue/SCSS only** — Markdown and Python are untouched by it), eslint and the Frappe Semgrep
rules.

### Test files

The generated `test_*` modules are Frappe/HRMS boilerplate (`IntegrationTestCase` subclasses with
no assertions); the value of the suite is that a site with this app installed boots and
bootstrap-tests cleanly. Add real tests next to the doctype they cover when you extend the logic.

## 9. Troubleshooting index

| Symptom | Where to look |
| --- | --- |
| Attendance not generated | [user_manual.md § 2.6](user_manual.md#26-refreshing-last-sync-of-checkin) |
| Payroll figures missing overtime / less time | [user_manual.md § 3](user_manual.md#3-less-time-and-overtime) |
| Gratuity zero or refusing to save | [user_manual.md § 5.1](user_manual.md#51-indemnity) |
| Scanning or dispensing lots misbehaving | [user_manual_stock.md § 10](user_manual_stock.md#10-troubleshooting) |
| VAT box understated / VAT dropdown empty | [user_manual_accounts.md § 9](user_manual_accounts.md#9-quick-reference--troubleshooting) |
| `bench run-tests` fails on mandatories | See section 8 — the `before_tests` hook clears them; check `hooks.py` still wires it |
| Migration fails with a mandatory error on Employee | A user-edited Custom Field / Property Setter re-added `reqd`; the shipped `custom/*.json` files are the source of truth |
| `after_migrate` errors mentioning Employees / FnF | The FnF import helper (section 6) — expected only on the reference site |
| Labels or scans behave oddly after an upgrade | `bench build` was skipped (desk JS cache) |
