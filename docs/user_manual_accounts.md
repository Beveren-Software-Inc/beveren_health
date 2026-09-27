# Beveren Health — User Manual (Accounts, Cost Centers & VAT)

Covers the branch/cost-center setup, patient price lists, Bahrain VAT preparation and filing,
expense reporting and the opening-balance / remediation helpers.

* People processes → [user_manual.md](user_manual.md)
* Pharmacy stock and dispensing → [user_manual_stock.md](user_manual_stock.md)
* Configuration, scripts, troubleshooting → [operations.md](operations.md)

## 1. Warehouses and cost centers

### 1.1 Mapping

Each **Warehouse** carries a **Cost Center** (`custom_cost_center`). The app uses that mapping
to stamp the right cost center automatically, so users do not have to pick one per line:

| Document | Behaviour |
| --- | --- |
| Purchase Order / Purchase Invoice / Purchase Receipt / Stock Reconciliation | *Cost Center* is set from the **Set Warehouse**; each row's cost center follows its own warehouse |
| Stock Entry | Cost center from the **Target Warehouse**, falling back to the **Source Warehouse**; rows use their own s/t warehouse |

If a row's warehouse has no cost center, nothing is overwritten — the value already on the row
is kept (so a manual cost center is respected).

> **Sales documents are not in this list.** Sales Invoice / Sales Order cost centers come from
> the ERPNext defaults (item, customer, company) or are entered by the user; the app only
> switches their *price list* (section 2). The dispensing-lot ledger still reports sales by the
> warehouse's cost center.

### 1.2 Cost Center master data

The **Cost Center** form gains:

* `CR No.` (`custom_cr_no`) and `Letter Head` — the branch's commercial registration and the
  letterhead used on its printed documents.
* `Address` (filtered to addresses linked to this cost center) plus the read-only
  `Address Display`, rendered on the form.

The desk label scripts also read `custom_cr_name` from the Cost Center for the **branch line on
the batch/medication label**. That field is **not** shipped in this repo (Frappe falls back to
the cost center's own name when it is missing) — create it on the site with **Customize
Form → Cost Center** if you want a short branch label there.
`Warehouse.custom_cost_center` drives the *Cost Center* filter of the
[Dispensing Lot Ledger](user_manual_stock.md#91-dispensing-lot-ledger).

---

## 2. Patient pricing (OP / IP)

`...customize.patient_pricing` picks the selling price list from the patient's admission
status on **Quotation**, **Sales Order** and **Sales Invoice**:

* **Inpatient** → `IP Selling`
* **Outpatient** → `OP Selling`

A patient counts as an inpatient when `Patient.inpatient_status` is `Admitted`, or when an
**Inpatient Admission** exists for them with status `Admitted`.

Rules of the automatic switch:

1. It is only active when **Healthcare Settings → auto_apply_patient_price_list** is ticked.
2. It only replaces an *empty* price list, `OP Selling`, `IP Selling` or `Standard Selling` —
   a price list the user deliberately picked (any other value) is never overwritten.
3. If the target price list does not exist, the document is left untouched.

The POS / SPA can call
`...customize.patient_pricing.get_price_list_for_patient(patient)` to show the right list up
front. Make sure both `OP Selling` and `IP Selling` exist as Price Lists and that every item
that a patient can be billed for has rates in both.

---

## 3. VAT setup

### 3.1 Configuration (one-off)

The custom fields are created automatically on every migrate
(`beveren_health.vat_setup.ensure_nbr_vat_fields`). Fill them in:

| Where | Field | What to enter |
| --- | --- | --- |
| **Company** | **VAT Accounts Configurations** table | One **VAT Account Configuration** row per VAT ledger with its *VAT Type*: `RCM Input`, `RCM Output`, `VAT Input`, `VAT Output` |
| **Address** of the company | **VAT No.** (`tax_id`) | The company's NBR VAT registration number(s); the report's VAT-number dropdown is built from the addresses linked to the company |
| **Sales Invoice** | **VAT Category** | `Registered (Domestic)`, `Unregistered (Domestic)`, `GCC Registered`, `GCC Unregistered`, `Overseas` |
| **Purchase Invoice** | **VAT Category** + **Reverse Charge Applicable** | Same list, plus the tick for imports accounted for through reverse charge |
| **Item Tax Template** | **VAT Category** | `Standard 10%`, `Standard 5%`, `Zero-Rated`, `Exempt` |

### 3.2 Tagging invoices

1. On a **Sales Invoice**: set the *VAT Category* (customer's status) and the sales taxes as
   usual. The VAT amount is read from the invoice's tax rows.
2. On a **Purchase Invoice**: set the *VAT Category*, tick *Reverse Charge Applicable* where the
   import VAT is accounted for through reverse charge, and keep the tax rows correct.
3. On the **Item Tax Template** used by the lines: set the Bahrain *VAT Category*
   (`Standard 10%` / `Standard 5%` / `Zero-Rated` / `Exempt`) so items can be classified.
4. Map the company's VAT ledgers in the *VAT Accounts Configurations* table — the return
   resolves the `VAT Output` / `VAT Input` / `RCM` ledgers from it.

---

## 4. NBR VAT Report (interactive)

The **NBR VAT Report** document is the working surface for a filing:

1. New **NBR VAT Report** → *Company*, *From Date*, *To Date*. The **VAT Number** dropdown is
   filled from the VAT numbers found on the company's Addresses (the first is preselected).
2. Click the primary button **Generate** to render the return.
3. Drill down through three levels:
   * **Level 1 – Summary**: the return form totals.
   * **Level 2 – Category**: the breakup of each box.
   * **Level 3 – Invoices**: the invoices contributing to a box, so every figure can be traced
     back to a document.
4. **Unclassified items** are listed separately — anything that could not be classified from
   its tax rows / Item Tax Template appears there; fix the master data and regenerate.
5. **Download Excel** (navbar secondary action) downloads the return with its invoice list as a
   filing workpaper.

The report is prepared from **submitted invoices only** and is a preparation aid — review it
before filing with the NBR.

**How the interactive report classifies a line** (`utils/nbr_vat_api.classify_sales_item` /
`classify_purchase_item`), from three sources:

* the invoice's **VAT Category** (`Registered (Domestic)`, `GCC Registered`, …),
* the **Item Tax Template's** Bahrain **VAT Category** (`Standard 10%`, `Standard 5%`,
  `Zero-Rated`, `Exempt`),
* the party's **country** (Bahrain → domestic, other GCC states, otherwise export/import) and the
  **Reverse Charge Applicable** flag.

Sales lines land in 1a/1b (standard 10 % / 5 %), 2 (GCC registered), 3 (domestic reverse
charge), 4 (zero-rated), 5 (exports) or 6 (exempt); purchase lines in 8a/8b (standard domestic),
9a/9b (imports, VAT at customs), 11a/11b or 12 (reverse charge, import / domestic) and 13
(zero-rated, exempt or non-registered suppliers). Anything the classifier cannot place is
reported under **Unclassified Items**. The VAT ledgers themselves come from the **Company's VAT
Accounts Configurations** rows, filtered by *VAT Type*
(`utils/nbr_vat_api.get_company_vat_accounts`).

`utils/nbr_vat_api.py` exposes the same data as API methods:
`get_vat_return_summary`, `get_category_breakup`, `get_invoice_list`, `get_unclassified_items`,
`get_all_contributing_invoices`, `download_vat_excel`, `get_company_vat_number(s)` and
`get_company_vat_accounts`.

---

## 5. Bahrain VAT Return (report)

**Bahrain VAT Return** is the plain script report over the same calculation
(`utils/vat_return.get_vat_return`), in NBR filing order:

| Box | Description |
| --- | --- |
| 1 | Standard rated sales |
| 2 | Sales to registered customers in other GCC states |
| 3 | Zero rated domestic sales |
| 4 | Exports |
| 5 | Exempt sales |
| 6 | Standard rated domestic purchases |
| 7 | Imports subject to VAT paid at customs |
| 8 | Imports subject to VAT accounted for through reverse charge |
| 9 | Zero rated purchases |
| 10 | Exempt purchases |

Columns: **Box**, **Description**, **Amount (excl. VAT)** and **VAT**, with *Total sales*,
*Total purchases* and **Net VAT due** rows.

> **The two VAT surfaces use different box layouts.** The **NBR VAT Report** document (section 4)
> classifies line by line (boxes 1a/1b, 2, 3, 8a/8b, 9a/9b, 11a/11b, 12, 13) and is the one to
> drill into; this **report** presents the simpler NBR 1–10 layout above from the same
> submitted invoices. Compare the totals of both when preparing a filing.

> VAT ledgers are recognised by the words `OUTPUT VAT` and `INPUT VAT` in the account name
> (`utils/vat_return._vat_accounts`). Keep that naming convention in the chart of accounts so
> this report finds the ledgers.

---

## 6. Department Wise Expense

**Department Wise Expense** aggregates expense-account GL entries by the **Department**
accounting dimension, with a **Cost Center** (branch) filter.

* Default period: 1 January of the current year → today; Company defaults to the user's default.
* Rows with no department land in a visible **`No Department`** bucket, so spend is never
  silently understated.
* **Summary view**: Department, Entries, Expense Amount, % of Total (with subtotals).
* Tick **Group by Account** for the detail view: Department, Expense Account, Entries,
  Expense Amount.

---

## 7. Opening balances

The site went live without an opening-balance migration (the only opening GL entries came from
Stock Reconciliation), so `utils/opening_balance.py` provides a **safe import path** — nothing
is posted until you supply and validate the figures.

Four kinds of import, each with its own template:

| Kind | Columns |
| --- | --- |
| `gl` | account, debit, credit, cost center, remarks |
| `customer` | customer, debit, credit, due date, remarks |
| `supplier` | supplier, debit, credit, due date, remarks |
| `bank` | account, debit, credit, remarks |

Workflow (debit = what the company owns / is owed, credit = what it owes; the two must
balance overall):

1. `get_template(kind)` — the column layout to fill in.
2. `validate_rows(kind, rows, company)` — **dry run**, reports problems without posting.
3. `create_opening_entry(kind, rows, posting_date, company, submit)` — posts one **Journal
   Entry of type "Opening Entry"** against the company's **Temporary** account
   (`account_type = Temporary`, which must exist first).
4. `opening_balance_status(company)` — has an opening-balance migration already been done?

Example:

```bash
bench --site <site> execute beveren_health.beveren_health.utils.opening_balance.opening_balance_status \
  --kwargs "{'company': 'Serene Psychiatry Hospital'}"
```

---

## 8. Prepared remediations (dry-run)

`utils/remediation.py` holds the corrections prepared for the UAT "Needs Sign-Off" items.
**Every function is a dry run by default** — it reports what it would change and changes
nothing. Pass `apply=True` only after sign-off. Nothing here is wired to a hook or scheduler.

| Function | What it covers |
| --- | --- |
| `fix_receivable_account` | Company default receivable account |
| `report_vat_misposting` | **Reports only** — the GL correction is a finance decision |
| `fix_asset_accounts` | Asset account setup |
| `fix_payroll_accounts` | Payroll account setup |
| `fix_default_shifts` | Missing default shifts |
| `fix_indemnity_cutoff` | Indemnity cutoff date |
| `fix_discount_caps` | Reports the POS discount cap (the cap itself is enforced by Healthcare Settings `discount_approval_threshold_percent`) |
| `fix_batch_expiry` | Batches with missing expiry dates |
| `run_all(apply=False)` | Everything above |

The module is pinned to company `Serene Psychiatry Hospital` — change the constant before use on
another site.

---

## 9. Quick reference & troubleshooting

| Task | Where |
| --- | --- |
| Give a warehouse a cost center | Warehouse → **Cost Center** (1.1) |
| Branch CR details on a cost center | Cost Center → CR No. / Address / Letter Head (1.2) |
| Switch patient price lists on/off | Healthcare Settings → *auto_apply_patient_price_list* (2) |
| Configure VAT ledgers | Company → **VAT Accounts Configurations** (3.1) |
| Prepare a VAT filing | **NBR VAT Report** → Generate → drill down → Download Excel (4) |
| VAT figures without drill-down | Report **Bahrain VAT Return** (5) |
| Spend per department | Report **Department Wise Expense** (6) |
| Post opening balances | `utils/opening_balance` dry run → create (7) |

| Symptom | Cause / fix |
| --- | --- |
| Price list not switching | The price list was set manually, the patient is not `Admitted`, or the `IP/OP Selling` price list does not exist. |
| A VAT box is understated | The invoice's *VAT Category* or the Item Tax Template's *VAT Category* is missing — check **Unclassified Items**. |
| VAT total does not match the ledger | VAT account names do not contain `INPUT VAT` / `OUTPUT VAT`, or the invoice tax rows are missing. |
| VAT dropdown empty | The company has no **Address** with a **VAT No.** |
| Cost center not filled | The warehouse has no Cost Center mapping (1.1) — the mapping is the only automatic source. |
