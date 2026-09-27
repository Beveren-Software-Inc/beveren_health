# Reference — Hooks, API and app inventory

Technical map of what `beveren_health` wires into Frappe / ERPNext / HRMS / Healthcare.

## 1. `hooks.py` at a glance

| Hook | Value | Purpose |
| --- | --- | --- |
| `app_include_js` | `js/dispensing_lot_scan_helpers.js`, `js/warehouse_cost_center.js`, `js/auto_save_scan.js` | Global helpers shared by the desk scripts |
| `app_include_icons` | `/assets/beveren_health/icons.svg` | Adds `#icon-klik-pos` used by the Klik POS workspace |
| `doctype_js` | 22 doctypes | Client scripts (section 2) |
| `doctype_list_js` | `Shift Type` | Adds **Update Last Sync For All Shifts** to the list view |
| `after_migrate` | 4 methods | HR workspace links, FnF import helper, Klik POS artwork, VAT custom fields |
| `before_tests` | `beveren_health.install.before_tests` | Lifts the site's `reqd` flags so the test framework can create its records |
| `doc_events` | see below | Server-side business logic |
| `scheduler_events` | daily / weekly / `hourly_long` | Expiry movement, document-expiry and probation reminders, last-sync refresh |
| `extend_doctype_class` | 5 doctypes | Class overrides (section 4) |
| `fixtures` | 4 entries | TNA Template, Employee naming-series Property Setter, appraisal-grid Property Setters, 47 scanning/label Custom Fields |
| `extend_bootinfo` | **commented out** | Healthcare-only desk for clinical roles — see [operations.md § 5.3](../operations.md#53-desk-sidebar-restriction-for-clinical-roles) |

### `doc_events`

| DocType | Event | Handler |
| --- | --- | --- |
| Employee | before_save | `customize.employee.before_save` |
| Shift Type | before_save | `customize.shift_type.before_save` |
| Attendance | before_insert | `customize.attendance.before_insert` |
| Overtime Slip | validate | `customize.overtime_allowance.validate` |
| Salary Structure | before_insert | `customize.salary_structure.before_insert` |
| Full and Final Statement | before_save | `customize.full_and_final_settlement.before_save` |
| HR Policy Document | on_update | `customize.hr_policy.distribute_policy` |
| Timesheet | validate | `customize.timesheet.set_patient_on_time_logs` |
| Item | on_update | `customize.item.on_update` |
| Batch | before_save / on_update | `override.batch.before_save`, `utils.batch.batch_before_save` |
| Serial No | before_insert | `customize.serial_no.set_gtin_universal` |
| Purchase Receipt | validate | `customize.warehouse_cost_center.set_cost_center_from_set_warehouse` |
| Purchase Receipt | before_submit | `customize.dispensing_lot.validate_stock_document_dispensing_lots` |
| Purchase Receipt | on_submit / on_cancel | `customize.serial_no.update_serial_gtin`, `customize.dispensing_lot.create_dispensing_lots_on_submit`, `...reverse_stock_document_dispensing_lots` |
| Stock Entry | validate | `customize.warehouse_cost_center.set_cost_center_from_stock_entry_warehouse` |
| Stock Entry | before_submit | `customize.dispensing_lot.validate_stock_entry_dispensing_lots` |
| Stock Entry | on_submit / on_cancel | `customize.serial_no.update_serial_gtin`, `customize.dispensing_lot.create_dispensing_lots_on_submit`, `...reverse_stock_document_dispensing_lots` |
| Stock Reconciliation | validate / before_submit / on_submit / on_cancel / on_trash | cost center, lot validation, lot creation + GTIN, scanner marking/release, lot reversal |
| Stock Scanner | before_submit | `customize.dispensing_lot.validate_stock_scanner_dispensing_lots` |
| Sales Invoice | validate | `customize.sales_invoice.validate_return_restrictions`, `customize.patient_pricing.set_price_list_for_patient` |
| Sales Invoice | before_submit | `customize.sales_invoice.validate_dispensing_lots`, `customize.dispensing_lot.fill_return_lots_on_submit` |
| Sales Invoice | on_submit / on_cancel | `...update_dispensing_lots_on_submit`, `...restore_dispensing_lots_on_cancel` |
| Delivery Note | before_submit / on_submit / on_cancel | lot validation, return-lot fill, consume and restore |
| Sales Order, Quotation | validate | `customize.patient_pricing.set_price_list_for_patient` |
| Purchase Order, Purchase Invoice | validate | `customize.warehouse_cost_center.set_cost_center_from_set_warehouse` |

### `scheduler_events`

```python
scheduler_events = {
    "daily": [
        "beveren_health.beveren_health.utils.expiry_movement.move_expired_batches_to_expiry_warehouse",
        "beveren_health.beveren_health.notifications.employee_notification.notify_expiring_employee_documents",
    ],
    "weekly": [
        "beveren_health.beveren_health.notifications.employee_notification.notify_ending_probation_period"
    ],
    "hourly_long": ["beveren_health.beveren_health.utils.attendance.update_last_sync_for_all_shifts"],
}
```

## 2. Desk (client) scripts

| File | Doctype / scope | Highlights |
| --- | --- | --- |
| `dispensing_lot_scan_helpers.js` | global | `beveren_health.dispensing_lot_scan.*` — append / split / count / set lots on a row |
| `warehouse_cost_center.js` | global | `set_from_warehouse` and `set_row_from_warehouse` used by PO / PI / PR / SR / SE |
| `auto_save_scan.js` | global | `beveren_health.auto_save_scan.*` — interval, row patching, save after *N* scans |
| `scanner.js` | global | Overrides `custom.barcode_scanner.handle_scan` (item + batch + qty into the item grid) |
| `stock_entry.js` | Stock Entry | Header + row scanner, batch label print, update batch expiry dates |
| `stock_reconciliation.js` | Stock Reconciliation | Row scanner, batch label print, dispensing-lots dialog, lot-quantity correction |
| `stock_scanner.js` | Stock Scanner | Scan handler, **Create Stock Reconciliation** dialog, view action |
| `purchase_receipt.js` | Purchase Receipt | Row scanner, batch label print and label review table |
| `sales_invoice.js` | Sales Invoice | Lot picker filters, mandatory lot on stock-updating lines, return lot auto-fill |
| `purchase_order.js`, `purchase_invoice.js` | PO / PI | Cost center propagation from the warehouse |
| `batch.js` | Batch | **Actions → Label Print** dialog (copies, branch) and the label HTML/CSS |
| `item.js` | Item | **Generate Barcode**, **Migrate Serials to Dispensing Lot** |
| `item_group.js` | Item Group | The six bulk actions (barcodes, serials, dispensing lots, UOM reversal) |
| `cost_center.js` | Cost Center | Address link + address display |
| `salary_slip.js` | Salary Slip | LWP / absent-day recalculation |
| `overtime_slip.js` | Overtime Slip | One-month date window, hides the Additional Salary button |
| `full_and_final_statement.js` | Full and Final Statement | **Create → Generate Indemnity**, indemnity payables, restricted reference pickers |
| `holiday_list.js` | Holiday List | Country / weekly off read-only |
| `shift_type.js`, `shift_type_list.js` | Shift Type | Standard-hours calculation; **Update Last Sync For All Shifts** |
| `shift_assignment.js` | Shift Assignment | Assignment helpers |
| `employee_checkin.js` | Employee Checkin | Employee / log type read-only once attendance exists |
| `timesheet.js` | Timesheet | Header patient pushed down to the time logs |
| `appraisal.js` | Appraisal | Refresh goals / self ratings after template selection |
| `stock_settings.js` | Stock Settings | **Move Expired Batches** |

> **Two loose ends in `doctype_js`** (harmless but worth knowing):
> `"Employee": "beveren_health/public/js/employee.js"` points at a file that is **not shipped**
> (the Employee logic lives in `customize/employee.py`), and the *Stock Settings* and *Item*
> entries write the path with a leading slash (`/public/js/item.js`) instead of the
> app-relative form (`public/js/item.js`) the other entries use. If a script ever fails to
> load, check that mapping first.

## 3. Python API (whitelisted)

| Method | Purpose |
| --- | --- |
| `customize.hr_policy.my_policies` | Policies for the logged-in employee with acknowledgement state |
| `customize.hr_policy.acknowledge_policy(acknowledgement, remarks)` | Employee acknowledges a policy |
| `customize.hr_policy.policy_compliance(policy)` | HR compliance counters + rows |
| `customize.full_and_final_settlement.get_reference_doctypes` | Link search for FnF reference doctypes |
| `customize.full_and_final_settlement.create_indemnity(fnf)` | Create / re-link the Indemnity for a draft statement |
| `customize.dispensing_lot.resolve_return_lots_for_lines(doctype, return_against)` | Lots to auto-fill on return rows |
| `customize.dispensing_lot.preview_dispensing_lot_qty_corrections(source_doctype, source_document)` | Preview the lot-quantity correction |
| `customize.dispensing_lot.correct_dispensing_lot_quantities(source_doctype, source_document)` | Apply the lot-quantity correction |
| `customize.salary_slip.get_lwp_absents(employee, start_date, end_date)` | LWP days + absent days for a payslip |
| `customize.patient_pricing.get_price_list_for_patient(patient)` | OP / IP price list for the POS |
| `customize.overtime_allowance.get_patient_visit_allowance(overtime_slip)` | Recalculate and return the patient-visit allowance |
| `customize.item.migrate_serials_to_dispensing_lots_for_item(item_code)` | Background: lots from serials for one item |
| `customize.item_group.*` | Background: barcodes, serial flags, dispensing lots, UOM reversal per group |
| `doctype.dispensing_lot.add_transaction(...)` | Post an Out / In / Transfer on a lot by hand |
| `doctype.dispensing_setting.flag_has_dispense_lot_from_dispensing_lots` | Tick *Has Dispense Lot* on items that already have lots |
| `doctype.less_time_compensation.get_compensation_data(from_date, to_date, employee)` | LT / OT rows for the compensation document |
| `doctype.less_time_entry.get_frequency_and_dates`, `get_emp_and_lesstime_details` | Period + attendance rows for a Less Time Entry |
| `doctype.training_need_assessment.get_instructions` | Rating instruction text for the TNA form |
| `utils.attendance.trigger_manual_last_sync` | Manually refresh `last_sync_of_checkin` (System Manager) |
| `utils.expiry_movement.trigger_expiry_movement` | Manually run the expiry movement |
| `utils.label_printing.get_label_data_for_batch(batch_name)` | All label fields for a batch |
| `utils.label_printing.get_batch_and_expiry_from_bundle(bundle)` | Batch + expiry from a Serial and Batch Bundle |
| `utils.batch.generate_barcode_for_existing_batches`, `regenerate_barcode_image_for_batch(batch_name)` | Barcode backfill |
| `utils.barcode.generate_barcode_image`, `utils.barcode.generate_ean13_barcode` | Barcode primitives |
| `utils.nbr_vat_api.*` | VAT summary, breakup, invoice list, unclassified items, Excel download, VAT numbers |
| `utils.opening_balance.get_template`, `validate_rows`, `create_opening_entry`, `opening_balance_status` | Opening-balance migration |
| `utils.print_format_setup.setup_print_format` | Create the *Medication Label* print format |
| `scripts.create_fnf_from_xlsx.run`, `scripts.cleanup_fnf.run` | FnF bulk import / cleanup |

## 4. Overridden doctype classes (`extend_doctype_class`)

| Doctype | Class | Adds |
| --- | --- | --- |
| Overtime Slip | `customize.overtime_slip.OvertimeSlip` | Less-time deduction, rate-change multiplier, Additional Salary creation |
| Appraisal | `customize.appraisal.Appraisal` | Manual template selection; KRAs, goals and rating criteria copied with minimum requirements |
| Employee Performance Feedback | `customize.employee_performance_feedback.EmployeePerformanceFeedback` | Feedback type / employment type handling |
| Full and Final Statement | `customize.full_and_final_statement_class.FullandFinalStatement` | Unique statement per employee + period, extended payable components, Employee party on the settlement JE |
| Batch | `override.batch.CustomBatch` | Expiry / manufacturing dates inherited from the creating voucher |

## 5. App-owned DocTypes

Submittable doctypes are marked **(S)**; the child tables have no autoname.

### HR, attendance and payroll

| DocType | Purpose |
| --- | --- |
| Additional Salary Type | Reusable Additional Salary reason → salary component |
| Employee Document | Child: document name, ID number, expiry, attachment |
| Employee Checkin Request **(S)** | Missed punch request → approved Employee Checkin |
| Employee Penalty **(S)** | Disciplinary penalty record |
| Penalty Type | Penalty master |
| Feeding Hours Entitlement | Paid feeding break for nursing mothers |
| Less Time Type | Shortfall master (component, calculation method, hourly rate) |
| Less Time Entry **(S)** | Period shortfall + details; the total deducts from overtime |
| Less Time Details | Child: attendance row, date, duration, standard hours |
| Less Time Compensation **(S)** | Settles uncompensated shortfall through an Additional Salary |
| LT Compensation Details | Child: LTE / OT references and durations |
| Indemnity **(S)** | Gratuity, paid through the GL or a salary slip |
| HR Policy Document | Policy + audience + publish flag |
| HR Policy Acknowledgement | Per-employee acknowledgement |
| Training Need Assessment **(S)** | TNA with ratings and totals |
| TNA Template / TNA Table / TNA Rating Instruction | TNA master data |
| Asset Physical Verification **(S)** | Asset count sheet (with its item child table) |
| Employee Visa Renewal Consent **(S)** | Visa renewal decision + approvals |
| Outgoing Employee | Child: leaver to be replaced (Job Requisition) |
| Nationality, Religion, Document Name | Simple employee master data |

### Stock, pharmacy and sales

| DocType | Purpose |
| --- | --- |
| Dispensing Setting | Per-document lot validation toggles |
| Dispensing Lot | One physical pack + its transactions |
| Dispensing Lot Transaction | Child: Out / In / Transfer |
| Stock Scanner **(S)** | Scan-first counting sheet → Stock Reconciliation |
| Stock Scanner Item | Child: barcode, batch, serial/lot, quantities, dates |
| Price Update **(S)** | Bulk price change → Item Price, reversible |
| Price Update Detail | Child: item, batch, current/new price |
| Item Category | Tree of item sub-categories |
| Item Class, Pharmaceutical Form, Route of Administration, Primary Packing, Unit of Strength | Item master data |
| MAH, Batch Releaser, Pharmacy Agent, Manufacturer | Manufacturer / licence master data |
| Urgency Type, PO Type, Invoicing Company | Purchasing / invoicing master data |

### Accounting and tax

| DocType | Purpose |
| --- | --- |
| VAT Account Configuration | Child of Company: VAT ledger + VAT type |
| NBR VAT Report | Interactive Bahrain VAT return (drill-down + Excel) |
| Bahrain VAT Return | Script report over the same calculation |
| Department Wise Expense | Script report (department / expense account) |
| Dispensing Lot Ledger | Script report (pack movements) |
| Dispensing Lot Movement | Placeholder script report (not implemented) |

## 6. Fixtures and print formats

| Fixture | Content |
| --- | --- |
| `TNA Template` | Training assessment templates |
| `Property Setter` (Employee) | `naming_series` default/options only (`S.###.`) |
| `Property Setter` (Appraisal Goal / Appraisal Template Goal / Employee Feedback Rating) | `allow_bulk_edit`, `row_format` for the appraisal grids |
| `Custom Field` | 47 rows: scanner / lot / GTIN / label / auto-save fields on Purchase Receipt, Stock Entry, Stock Reconciliation, Delivery Note, Sales Invoice, Serial No, Item Barcode, Batch, Cost Center, Warehouse and Timesheet |

Print formats: `Employee Visa Renewal Consent Form` (JSON only — recreate per site, see
[operations.md § 7](../operations.md#print-format-for-visa-renewal)) and the *Medication Label*
Jinja format created by `utils.print_format_setup.setup_print_format`.

> `fixtures/property_setter.json` is currently empty. The Property Setters that really apply are
> in `beveren_health/beveren_health/custom/*.json`, which Frappe's `sync_customizations` reloads
> on every migrate — see [customizations.md](customizations.md).
