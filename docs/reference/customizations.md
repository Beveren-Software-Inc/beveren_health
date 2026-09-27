# Reference — Custom Fields & Property Setters

Every customization the app applies to a **standard** doctype. They live in
`beveren_health/beveren_health/custom/<doctype>.json` and are re-applied by Frappe's
`sync_customizations` on every `bench migrate` — they are the source of truth after an upgrade.

Some entries are HRMS/ERPNext fields that were only **re-positioned, relabelled or made
mandatory**; they appear in the export for the same reason. Labels marked **(mandatory)** are
`reqd = 1` — these are the fields the test bootstrap cannot fill (see
[operations.md § 8](../operations.md#8-testing-and-ci)).

## Employee (`custom/employee.json`)

| Label | Type | Notes |
| --- | --- | --- |
| Nationality | Link → Nationality | **mandatory**, after *Employee Name* |
| Religion | Link → Religion | **mandatory**, after *Gender* |
| CPR Number | Data | HRMS `employee_number`: relabelled, **mandatory**, visible, in list view |
| Department, Designation | Link | **mandatory** (Property Setter), shown in list view |
| Is Probation Period ? | Check | After *Image* |
| Probation Period (Days) | Float | Shown when *Is Probation Period ?* |
| Contract Expiry | Date | Shown when *Employment Type* = `Contract` |
| Is Overtime Payable ? | Check | Fed to the Overtime Slip |
| Is Less Time Deductible ? | Check | Fed to the Less Time Entry |
| Standard Working Hours | Float | Default daily hours |
| Payroll Cost Center | Link → Cost Center | Fetched from the Department |
| Visa Status | Select | `Company Visa / Dependent Visa / Independent Visa / National - With Gosi / National - Without Gosi` |
| Under GOSI Registered ? | Check | Shown for Bahraini employees on the GOSI visa |
| Years of Service | Float | Read-only, computed from joining → relieving date |
| Signature | Attach | Below *Under GOSI Registered ?* |
| Documents | Table → Employee Document | CPR / NHRA and other documents |
| Job Applicant | Link → Job Applicant | After *Employment Details* |
| Employment Type, Grade, Default Shift, Employee Advance Account, Leave Approver, Expense Approver, Shift Request Approver, MICR Code, IFSC Code, PAN Number, Provident Fund Account, Employee Name for Bank, Alternate Mobile 1–2, Employee Attendance Code, Health Insurance Provider/No | various | Re-positioned HRMS fields plus the health-insurance and alternate-mobile additions |
| Approvers, Document Attachment, Health Insurance, salary/bank section & column breaks | Section/Column Break | Layout |
| Employee Name for Bank / IFSC / MICR | — | Shown when *Salary Mode* = `Bank` |

Property Setters: `naming_series` default `S.###.` (options `S.###.\nHR-EMP-`, hidden, not
mandatory), `bank_details_section` and `passport_details_section` visibility, `relieving_date`
`depends_on`, list-view flags for Branch / Department / Designation / Employee Name, and the
whole form `field_order`.

## Shift Type (`custom/shift_type.json`)

| Label | Type | Notes |
| --- | --- | --- |
| Standard Working Hours | Float | Read-only; end − start (wraps over midnight) |
| Weekly Off | Data | Read-only, fetched from `holiday_list.weekly_off` |
| Allow Less Time | Check | |
| Less Time Type | Link → Less Time Type | Shown when *Allow Less Time* |

Property Setters: **`holiday_list` is mandatory**, `allow_import` = 1, form `field_order`.

## Shift Assignment (`custom/shift_assignment.json`)

| Label | Type | Notes |
| --- | --- | --- |
| Weekly Off | Data | Read-only, fetched from the Shift Type |
| Less Time Type | Link → Less Time Type | Fetched from the Shift Type |

Property Setter: form `field_order`.

## Attendance (`custom/attendance.json`)

| Label | Type | Notes |
| --- | --- | --- |
| Less Time Type | Link → Less Time Type | Read-only, set by the before_insert hook |
| Actual Less Time Duration | Float | Read-only shortfall in hours |
| Grace Hours | Float | Read-only time added back within the grace periods |
| Lesstime (section), column breaks | Section Break | Layout — the section shows only when a less time type was set |

Property Setter: form `field_order` (Attendance).

## Payroll and overtime

### Overtime Slip (`custom/overtime_slip.json`)

| Label | Type | Notes |
| --- | --- | --- |
| Is Overtime Payable ? | Check | Read-only, fetched from the Employee |
| Reference Document | Link → Less Time Entry | Read-only, set on submit |
| Total Less Time Duration | Float | Read-only, copied from the Less Time Entry |
| Total Overtime Duration | Float | Read-only; relabelled *Total Duration (After Compensation)* |

Property Setter: form `field_order`. The patient-visit allowance fields are created separately
(see [operations.md § 7](../operations.md#optional-overtime-patient-visit-fields)).

### Overtime Type (`custom/overtime_type.json`)

| Label | Type | Notes |
| --- | --- | --- |
| Rate Change Cutoff Hours | Float | **mandatory** |
| Rate Change Multiplier | Float | **mandatory** |

Property Setter: form `field_order`.

### Salary Slip (`custom/salary_slip.json`)

Property Setters only: `leave_without_pay` **read-only**, `rounded_total` visible and printed.

### Salary Component (`custom/salary_component.json`)

| Label | Type | Notes |
| --- | --- | --- |
| Is Basic Salary ? | Check | Identifies the basic component used by Indemnity |

Property Setter: form `field_order`.

### Additional Salary (`custom/additional_salary.json`)

| Label | Type | Notes |
| --- | --- | --- |
| Additional Salary Reason | Link → Additional Salary Type | |
| Remarks | Small Text | Shown when a reason is selected |

Property Setter: form `field_order`.

### Payroll Settings (`custom/payroll_settings.json`)

| Label | Type | Notes |
| --- | --- | --- |
| GOSI Settings (section) | Section Break | |
| GOSI Salary Component | Link → Salary Component | Appended as a deduction to new Salary Structures |

### HR Settings (`custom/hr_settings.json`)

| Label | Type | Notes |
| --- | --- | --- |
| Indemnity Settings (section) | Section Break | |
| Indemnity Cutoff Date | Date | Used by Indemnity |
| Default Indemnity Expense Account | Link → Account | |
| Default Indemnity Payable Account | Link → Account | |

## Full and Final Statement (`custom/full_and_final_statement.json`)

| Label | Type | Notes |
| --- | --- | --- |
| Base Salary / Basic Salary | Currency | Read-only, copied from the Indemnity |
| Consider Full Salary After Cutoff Date | Check | |
| Cutoff Date | Date | Read-only, default `2024-03-01` |
| Indemnity | Link → Indemnity | Same employee only |
| Total Experience | Data | Read-only, e.g. `3 years 2 months and 11 days` |
| Nationality | Link → Nationality | Read-only, fetched from the Employee |
| Under GOSI Registered ? | Check | Read-only, fetched from the Employee |
| Workflow State | Link → Workflow State | For an approval workflow |

Property Setters: `default_print_format` = **FFS Summary**, list-view flags for Company /
Employee / Employee Name, `total_payable_amount` and `total_receivable_amount` hidden in list
view, form `field_order`.

Child tables: **Full and Final Asset** and **Full and Final Outstanding Statement** each gain a
**Want Print ?** Check; the outstanding statement also gets `reference_document`
`mandatory_depends_on`.

## Appraisal and feedback

| Doctype | Addition |
| --- | --- |
| **Appraisal Cycle** | `Appraisal Type` → Select `Probation / Annual / Others` |
| **Appraisal** | `Appraisal Type` (Data, read-only, fetched from the cycle), `Final Score (%)` (Percent), form order |
| **Appraisal Goal**, **Appraisal KRA**, **Appraisal Template Goal**, **Employee Feedback Rating** | `Minimum Requirement (Out of 100)` (Percent, **mandatory**) |
| **Employee Performance Feedback** | `Feedback Type` (Select `Annual / Provision`, default `Annual`), `Employment Type` (read-only, fetched from the Employee) |

Property Setter: `allow_bulk_edit` + `row_format` on Appraisal Goal / Appraisal Template Goal /
Employee Feedback Rating (carried as fixtures, because editing the hrms JSON loses them on
upgrade).

## Job Requisition (`custom/job_requisition.json`)

| Label | Type | Notes |
| --- | --- | --- |
| Requisition Type | Select | `New / Replacement`, default `New` |
| Replacement (section) + Outgoing Employee(s) | Section + Table | Shown for `Replacement` |

Property Setters: `column_break_qkna` hidden, form `field_order`.

## Item (`custom/item.json`)

| Group | Fields |
| --- | --- |
| Registration | Drug Registration Number, Drug Status (`Active(Registered)` / `Inactive(Cancelled)`), Licensing Status (`PENDING` / `REGISTERED` / `SUSPENDED`), ATC Code, GTIN Number, First / Last / Next Renewal Date, Cancel Date, Cancel Reason |
| Manufacturer / licence | MAH Code (+ fetched MAH Name, MAH Full Address), Bulk Manufacturer Name / Address, Registration Number of Batch Releaser (+ fetched name, address, registration date), Agent Licence No. (+ fetched Agent Name) |
| Classification | Item Class, Item Subcategory (Link → Item Category), Item Category (read-only, fetched parent), Legacy Code, Pharmaceutical Form, Route of Administration, Primary Packing, Method of Sales/Supply (`OPOM / ORAL / POM / GS / PO / P`), Therapeutic Group, Active Substance(s) |
| Packaging / storage | Strength, Unit of Strength, Number of Pack, Pack Size, Shelf-life (in Months), Storage Conditions, Is Refrigerated ?, Is Schedule 3 Narcotic ? |
| Commercial | Invoicing Company, Invoicing Company Code, Invoicing Company Name & Country |

Property Setters: `barcodes` and `item_code` visible, `item_code` mandatory, `naming_series`
hidden with options `STO-ITEM-.YYYY.-`, `over_billing_allowance` and
`over_delivery_receipt_allowance` hidden, `has_variants` description cleared,
`standard_rate` `depends_on` cleared, `shelf_life_in_days` relabelled *Shelf-life (in Days)*,
form `field_order`.

## Item Barcode (`custom/item_barcode.json`)

| Label | Type | Notes |
| --- | --- | --- |
| Image | Attach Image | The generated EAN-13 image |

Property Setter: `barcode` visible.

## Manufacturer (`custom/manufacturer.json`)

* Manufacture Address (Small Text) + column break; property setter for `field_order`.

## Nationality (`custom/nationality.json`)

* Property Setter: `allow_import` = 1 (the **Nationality** doctype itself ships with the app).

## Supplier (`custom/supplier.json`)

| Label | Type |
| --- | --- |
| CR No. / CR Date / Branch No. | Data / Date / Int |
| NHRA Facility License | Data |
| UP ID / UP Date | Data / Date |
| Is Distributor ? | Check |
| Minimum Order | Data |
| Supplier Category | Select (`Local` / `International`) |
| Is VAT Applicable | Check |
| Supplier Remarks | Small Text |

Property Setters: `naming_series` hidden and not mandatory, form `field_order`.

## Purchase Order (`custom/purchase_order.json`)

| Label | Type |
| --- | --- |
| Department | Link → Department |
| PO Type | Link → PO Type |
| Urgency Type | Link → Urgency Type |

Property Setters: `rounded_total`, `base_rounded_total`, `in_words` visible (`in_words` prints,
`base_rounded_total` does not), `disable_rounded_total` default 0, `scan_barcode` visible,
`naming_series` options.

## Doctypes whose fields are shipped as part of the Custom Field fixture

| DocType | Fields |
| --- | --- |
| **Cost Center** | CR No. (`custom_cr_no`), Letter Head, Address, Address Display, Address HTML |
| **Warehouse** | Cost Center, CR No. |
| **Batch** | Original Batch ID |
| **Serial No** | GTIN |
| **Item** | Has Dispense Lot (`custom_has_dispense_lot`) |
| **Item Barcode** | Image (`custom_image`), Batch (`custom_batch`) |
| **Purchase Receipt** | Auto Save Scan Interval; item rows: Scanner, Dispensing Lot, Expiry Date, Manufacturing Date, GSTIN, Label Print, Label Printing |
| **Stock Entry** | Custom Scanner (`custom_custom_scanner`), Auto Save Scan Interval; detail rows: Scanner, Dispensing Lot, Expiry Date, Manufacturing Date, GSTIN |
| **Stock Reconciliation** | Custom Scanner, Auto Save Scan Interval; item rows: Scanner, Dispensing Lot, Expiry Date, Manufacturing Date, GSTIN |
| **Sales Invoice Item** | Dispensing Lot |
| **Delivery Note Item** | Dispensing Lot |
| **Timesheet** | Patient, Patient Name |
| **Timesheet Detail** | Patient, Patient Name, Duration |

## Notes

* **Both sources matter.** `custom/*.json` covers the HR / payroll / master-data doctypes;
  `fixtures/custom_field.json` covers the stock, scanning, label, Cost Center, Warehouse and
  Timesheet fields. A missing field after an upgrade usually means `bench migrate` was skipped.
* **Do not edit the hrms/erpnext JSON files** for these — the app re-applies them from here, and
  upstream upgrades would drop the changes.
* The `custom/*.json` files are also what HR Management edits when they change a mandatory flag
  in the UI: export the form again (**Customize Form → ⚙ → Export Customizations**) so the change
  lands in the repo.
