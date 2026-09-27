# Beveren Health — Documentation

`beveren_health` is the site-customization app for **Beveren Health**. It runs on top of
**Frappe v16 + ERPNext + HRMS + Healthcare** and adds the Bahrain-specific and
hospital-specific behaviour the standard apps do not ship.

Everything is applied from this app (`bench migrate` re-applies it), so the upstream
`erpnext`, `hrms` and `healthcare` repositories stay clean and upgrades do not lose the
customization.

> Reference deployment: company **Serene Psychiatry Hospital** (`SPH`), currency **BHD**.
> Several maintenance scripts carry that company name — adjust them before use on another site.

## What this app adds

| Area | What it covers |
| --- | --- |
| **HR & attendance** | Employee master (CPR / NHRA documents, probation, visa & GOSI, years of service), shift types named by hours + weekly off, standard working hours, grace hours, feeding-hours entitlement, missed-punch approval, employee-document expiry reminders, HR policy distribution & acknowledgement, appraisals, training need assessment, asset verification, visa-renewal consent, outgoing employees |
| **Payroll** | Overtime slip with less-time deduction and patient-visit allowances, less-time entry + compensation, LWP/absent day calculation, GOSI component, indemnity (gratuity) with GL or salary-slip payout, Full and Final Statement extensions, Employee Penalty |
| **Pharmacy stock** | GS1 barcode scanning on Purchase Receipt / Stock Entry / Stock Reconciliation / Stock Scanner, EAN-13 barcode generation for items and batches, batch labels, expiry movement, dispensing lots (pack-level traceability), batch expiry inherited from the voucher |
| **Sales** | OP/IP price list switch by admission status, dispensing-lot validation on sales, lots auto-filled on returns |
| **Accounting & VAT** | Bahrain NBR VAT return (report + interactive doctype + Excel), warehouse → cost center mapping, cost center CR/address/letter head, opening-balance migration helpers, prepared remediations |
| **Reports** | Bahrain VAT Return, Department Wise Expense, Dispensing Lot Ledger |
| **Admin** | HR workspace links, Klik POS icon, Healthcare-only desk for clinical roles, TNA template fixture, print format for visa renewal, test-time relaxation of the site's mandatory fields |

## Documentation index

| Document | Read it when you need to |
| --- | --- |
| [user_manual.md](user_manual.md) | Do day-to-day **HR / attendance / payroll / appraisal / exit** work |
| [user_manual_stock.md](user_manual_stock.md) | Do **pharmacy stock, scanning, labels, batches, dispensing lots, price changes** |
| [user_manual_accounts.md](user_manual_accounts.md) | Do **cost centers, patient pricing, VAT returns, reports, opening balances** |
| [operations.md](operations.md) | **Install, configure, run the scheduled jobs, test, troubleshoot, run maintenance scripts** |
| [reference/customizations.md](reference/customizations.md) | Look up **every Custom Field / Property Setter** the app adds to standard doctypes |
| [reference/hooks_and_api.md](reference/hooks_and_api.md) | Look up **hooks, Python API, doctype classes, fixtures, file map** |

## Prerequisites

* Frappe bench **v16** (`frappe >=16,<17`, `erpnext >=16,<17`, Python ≥ 3.10, Node ≥ 24)
* Installed apps on the site: `erpnext`, `hrms`, `healthcare`, then `beveren_health`
* Python package `python-barcode == 0.15.1` (declared in `pyproject.toml`, used for
  EAN-13 images). Install with `bench pip install "python-barcode[images]"` if it is missing.
* Desk roles used by the app: `HR Manager`, `HR User`, `System Manager`, plus the clinical
  roles listed in
  [operations.md](operations.md#53-desk-sidebar-restriction-for-clinical-roles).

## Install

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/<org>/beveren_health --branch develop
bench --site <site> install-app beveren_health
bench --site <site> migrate
bench build
```

After installing, complete the configuration listed in
[operations.md](operations.md#2-configuration-after-install) — at minimum HR Settings
(indemnity accounts + cutoff date), Healthcare Settings (default expiry warehouse),
Company VAT accounts and the Payroll Settings GOSI component.

## What runs automatically

`after_migrate` (every `bench migrate`):

1. `...override.hr_workspace.add_hr_workspace_links` — re-adds *Employee Checkin Request*
   to the **HR Setup** and **Shift & Attendance** workspaces and keeps the *People* desktop
   tile hidden.
2. `...scripts.create_fnf_from_xlsx.run` — Full-and-Final import helper (idempotent; see
   [operations.md](operations.md#6-full-and-final-import-helpers)).
3. `...override.desk_sidebar.set_klik_pos_workspace_icon` — points the Klik POS tile at the
   SVG shipped in `public/images/klik_pos_icon.svg`.
4. `...vat_setup.ensure_nbr_vat_fields` — creates the VAT custom fields
   (Company → *VAT Accounts Configurations*, Address → *VAT No.*, Sales/Purchase Invoice →
   *VAT Category*, Item Tax Template → *VAT Category*).

Scheduled jobs (see [operations.md](operations.md#4-scheduled-jobs)):

| Frequency | Job |
| --- | --- |
| Daily | Move expired batches to the expiry warehouse |
| Daily | Employee document expiry reminders (90 → 0 days, every 10 days) |
| Weekly | Probation-period ending reminder (30 days ahead) |
| Hourly (long) | Refresh `last_sync_of_checkin` for every shift |

`bench run-tests` additionally calls `beveren_health.install.before_tests`, which clears the
`reqd` flag of the site's shipped customizations on **Employee** and **Shift Type** so the
framework's synthetic test records can be created. See
[operations.md](operations.md#running-tests).

## Repository layout

```
beveren_health/
├── hooks.py                       # all wiring: doctype_js, doc_events, scheduler, hooks
├── install.py                     # before_tests() — relaxes site-required fields for CI
├── constants.py, vat_setup.py     # VAT category options + VAT custom fields
├── fixtures/                      # TNA Template, selected Property Setters, selected Custom Fields
├── scripts/                       # create_fnf_from_xlsx.py, cleanup_fnf.py (bench execute)
└── beveren_health/
    ├── custom/*.json              # Custom Fields / Property Setters exported via "Customize Form"
    ├── customize/*.py             # business logic hooked onto standard doctypes
    ├── doctype/*                  # 43 doctypes owned by this app (see reference/hooks_and_api.md)
    ├── override/*.py              # Batch class override, HR workspace links, desk sidebar
    ├── utils/*.py                 # barcode, batch, scanner, labels, expiry, VAT, opening balance
    ├── notifications/             # employee document / probation notifications
    ├── report/                    # Bahrain VAT Return, Department Wise Expense, Dispensing Lot Ledger
    └── print_format/              # Employee Visa Renewal Consent Form (bundled JSON; see note)
public/js/*.js                     # desk scripts (scanner, labels, lots, cost center, payroll ...)
public/icons.svg, public/images/   # custom desk icon sprite + Klik POS artwork
docs/                              # this documentation
```

> Note: `print_format/employee_visa_renewal_consent_form/` currently ships only the
> `.json` metadata (no `__init__.py`), so it is not imported by Frappe. The print format is
> recreated per site with **Print Format → New → DocType: Employee Visa Renewal Consent**.

## How to read this documentation

* **Process steps** are numbered and use the exact button and field labels you see on screen.
* Field names in `code font` are the underlying fieldnames, handy when filtering/reporting.
* Commands are shown for a bench at `~/frappe-bench` with site name `<site>` — substitute yours.
