# Beveren Health — User Manual (Pharmacy, Stock & Scanning)

Covers drug/stock master data, barcode scanning, batch labels, expiry handling, dispensing
lots (pack-level traceability), price updates and stock reporting.

* People processes (HR, payroll, gratuity, FnF) → [user_manual.md](user_manual.md)
* Accounts, VAT, cost centers → [user_manual_accounts.md](user_manual_accounts.md)
* Configuration, settings, scripts, troubleshooting → [operations.md](operations.md)

## 1. Master data

### 1.1 Item (drugs and consumables)

Extra **Healthcare** tab / fields added by the app:

| Group | Fields |
| --- | --- |
| Registration | `Drug Registration Number`, `Drug Status` (`Active(Registered)` / `Inactive(Cancelled)`), `Licensing Status` (`PENDING` / `REGISTERED` / `SUSPENDED`), `ATC Code`, `GTIN Number`, `First / Last / Next Renewal Date`, `Cancel Date`, `Cancel Reason` |
| Manufacturer / supplier | `MAH Code` + fetched `MAH Name`, `MAH Full Address` (*MAH* doctype), `Bulk Manufacturer Name`, `Bulk Manufacturer Address`, `Registration Number of Batch Releaser` + fetched name/address/registration date (*Batch Releaser* doctype), `Agent Licence No.` + fetched `Agent Name` (*Pharmacy Agent* doctype) |
| Classification | `Item Class`, `Item Subcategory` (tree **Item Category**), `Item Category` (read-only, fetched parent), `Legacy Code`, `Pharmaceutical Form`, `Route of Administration`, `Primary Packing`, `Method of Sales/Supply` (`OPOM / ORAL / POM / GS / PO / P`), `Therapeutic Group`, `Active Substance(s)` |
| Packaging / storage | `Strength`, `Unit of Strength`, `Number of Pack`, `Pack Size`, `Shelf-life (in Months)` (+ HRMS `Shelf-life (in Days)`), `Storage Conditions`, `Is Refrigerated ?`, `Is Schedule 3 Narcotic ?` |
| Commercial | `Invoicing Company`, `Invoicing Company Code`, `Invoicing Company Name & Country` |
| Tracking | `Has Dispense Lot` (`custom_has_dispense_lot`) — set it to make the dispensing lot **mandatory** on every stock/sales line for this item |

Buttons on a saved Item:

* **Generate Barcode** — creates an EAN-13 barcode row plus its image when the item has none
  (fills the missing image if only the barcode exists, and reports when nothing is needed).
* **Migrate Serials to Dispensing Lot** — queues a background job that creates one
  **Dispensing Lot** per existing Serial No (pack size and UNIT conversion taken from the
  item). Serial No records are left untouched.

### 1.2 Item Group — bulk maintenance

On a saved **Item Group**, the **Actions** buttons run background jobs and report back through
a desk notification:

| Button | What it does |
| --- | --- |
| **Generate EAN Barcodes** | Creates an EAN-13 barcode + image for every item in the group that has none |
| **Clear Has Serial No** | Unsets `has_serial_no` on all items in the group |
| **Migrate Serials to Dispensing Lot** | Creates Dispensing Lots from all Serial Nos of the group's items |
| **Enable Has Dispense Lot from Lots** | Ticks `Has Dispense Lot` on the group's items that already have dispensing lots |
| **Clear Has Dispense Lot** | Unsets `Has Dispense Lot` on all items in the group |
| **Reverse UOM Conversions** | Reverses the UOM conversion setup (background job; use before re-importing conversions) |

### 1.3 Item Barcode

The barcode grid is visible again (`barcode` and `barcodes` were hidden by the app's
Property Setter before). Each row can carry:

* `Image` (`custom_image`) — the generated EAN-13 image,
* `Batch` (`custom_batch`) — the batch this barcode belongs to (one row per batch).

### 1.4 Batch

* `Expiry Date` and `Manufacturing Date` are **copied from the creating voucher** when the
  Batch is created from a Purchase Receipt / Stock Entry / Stock Reconciliation line.
* On every save the app generates a **new unique EAN-13 barcode** for the batch and appends it
  to the item's barcode table (with `Batch` = this batch and the barcode image). Existing rows
  are never duplicated.
* `Original Batch ID` (`custom_original_batch_id`) keeps the manufacturer's batch number when
  the same batch number belongs to a different item — the app then stores the batch as
  `<batch_no>_<item_code>` and remembers the original. Scanning the printed batch number still
  resolves to the right item.
* **Batch Releaser / MAH / Pharmacy Agent** are simple master doctypes
  (code/name/address/registration date) linked from the Item.

### 1.5 Stock Settings and UOMs

* Warehouse → Cost Center mapping (`Warehouse.custom_cost_center`) is described in
  [user_manual_accounts.md](user_manual_accounts.md#1-warehouses-and-cost-centers).
* Cost Center carries `CR No.`, `CR Name`, a linked `Address` with its display, and a
  `Letter Head` — used on the branch line of the batch label and on invoices.
* Items tracked in whole packs use a `UNIT` UOM row; the dispensing-lot engine converts stock
  quantities into UNITs with that conversion factor (see
  [4. Dispensing lots](#4-dispensing-lots--pack-level-traceability)).

---

## 2. Barcodes

### 2.1 Two kinds of barcode

| Kind | Created by | Where it is used |
| --- | --- | --- |
| **Item barcode** (EAN-13) | *Generate Barcode* button on the Item, *Generate EAN Barcodes* on the Item Group | Plain scanning on stock documents; POS |
| **Batch barcode** (EAN-13) | Automatically on every Batch save | Batch label printing; scanning resolves item + batch |

Batch barcodes are the ones printed on the **medication labels**, so a label scan carries both
item and batch (and, when the manufacturer's GS1 code is used, serial, expiry and batch too).

### 2.2 Barcode formats the scanner understands

`beveren_health.beveren_health.customize.scanner.parse_barcode` accepts:

1. **Parentheses GS1** — `(01)08901234567890(21)SERIAL(17)270731(10)BATCH123`
   (AI 01 = GTIN, 21 = serial, 17 = expiry `YYMMDD`, 10 = batch).
2. **Raw GS1** — the same AIs concatenated, with or without GS separators.
3. **Simple batch/serial text** — the scanned value is used as the batch number.
4. **Delimiter format** used by internal labels — `ITEMCODE|BATCHNO`
   (`utils/scanner.get_item_and_batch_from_barcode`).

`YYMMDD` is expanded to a full date (expiry and manufacturing dates are filled on the row).

### 2.3 Scanner fields on the documents

| Document | Header scanner | Row scanner |
| --- | --- | --- |
| Purchase Receipt | — | `Scanner` on each item row |
| Stock Entry | `custom_custom_scanner` | `Scanner` on each detail row |
| Stock Reconciliation | `custom_custom_scanner` | `Scanner` on each item row |
| Stock Scanner | — | `Barcode` / `Scanner` on each row |

A USB/handheld scanner types the code and sends Enter, so just keep the scanner field focused:
the barcode is consumed, the field is cleared and a toast tells you what happened. Nothing is
left in the field to trip the next scan.

**Auto-save:** each scan updates the row, and the form is saved automatically every *N* scans
(or immediately when the server could not persist the row itself). The interval comes from
`Auto Save Scan Interval` (`auto_save_scan_interval`, label *Auto Save Scan Interval*, shipped on
Purchase Receipt / Stock Entry / Stock Reconciliation); `beveren_health.auto_save_scan.get_interval`
falls back to **10** when it is left empty. Set it to `1` to save after every scan.

### 2.4 What a scan does

1. The barcode is resolved to **item + batch + serial + GTIN + expiry/manufacturing dates**.
2. If the current row is empty, the batch/serial/dates and quantity land on it (case 1).
3. Scanning the **same batch** again appends another dispensing lot/serial to the row and
   recalculates the row quantity (case 2).
4. Scanning a **different batch** while the current row is already used asks the UI to add a
   **new child row** for it (case 3).
5. If the batch or serial does not exist yet, it is created on the fly (with the expiry date
   from the barcode), reusing the original batch number per item when the same number is
   already used by another item.

---

## 3. Batch labels

### 3.1 Printing from a Batch

1. Open the saved **Batch**.
2. **Actions → Label Print**.
3. Set the **Number of Labels** (defaults to the batch quantity, or 1) and pick the
   **Branch (Cost Center)** — the cost center's `custom_cr_name` is printed as the branch line
   (falling back to the cost center's own name when that field is not present).
4. **Print** — a print window opens with one label per copy; close it after printing.

Each 2.299in × 1.5in label contains: branch, barcode image, item code + item name line
(item name, strength, pharmaceutical form, batch UOM and number of packs), **Standard Selling
Price**, batch number and expiry date. If a batch has no barcode yet, one is generated on the
fly so label printing never blocks.

### 3.2 Printing from a stock document

**Purchase Receipt**, **Stock Entry** and **Stock Reconciliation** have
**Actions → Batch Label Print**:

1. Choose the **row range** (From Row → To Row) of the item table.
2. Click **Load Items**.
3. In **Review & Print Labels** set the number of labels per row and click **Print All**
   (or Cancel to abort).

### 3.3 Keeping batch dates correct

* **Purchase Receipt / Stock Reconciliation** entries carry `Expiry Date` and
  `Manufacturing Date` per row; on submit they are written to the Batch.
* For **Stock Entry**, use **Actions → Update Batch Expiry Dates** to push the row dates onto
  the batches afterwards.

---

## 4. Dispensing lots — pack-level traceability

A **Dispensing Lot** is one physical pack: item, batch, warehouse, the manufacturer's serial
and its **Initial** and **Remaining Qty** in the dispensing UOM (usually `UNIT`). Every
movement is stamped in its **Transactions** table (`Out` / `In` / `Transfer`).

### 4.1 Statuses

| Status | Meaning |
| --- | --- |
| `Active` | Full pack in stock |
| `Partially Sold` | Some units (tabs/ml) already sold, remainder still usable |
| `Delivered` | Pack fully consumed |
| `Inactive` | Lot reversed / transferred away / expired |

### 4.2 Turning the checks on — Dispensing Setting

**Dispensing Setting** is a single with one toggle per document type:

* Validate Dispensing Lot on Stock Entry
* Validate Dispensing Lot on Sales Invoice
* Validate Dispensing Lot on Delivery Note
* Validate Dispensing Lot on Stock Reconciliation
* Validate Dispensing Lot on Purchase Receipt
* Validate Dispensing Lot on Stock Scanner

Only for items with **Has Dispense Lot** ticked on the Item. Leave a toggle off to work
without lot validation on that document type. The single also has the button
**Enable Has Dispense Lot from Lots**, which ticks the flag on every item that already has
dispensing lots.

### 4.3 How lots are created

* Scanning a manufacturer serial on a **Purchase Receipt / Stock Entry / Stock Reconciliation /
  Stock Scanner** line puts it in the row's `Dispensing Lot` field (and keeps the batch).
* On **submit** the app creates one **Dispensing Lot** per serial, at the row's warehouse, with
  the GTIN from the barcode, the batch from the row and quantities in the dispensing UOM.
* Quantities are distributed pack by pack: with `n` serials on a line, each serial except the
  last represents one full pack and the last one gets the fractional remainder
  (e.g. 1.86 pack across 2 serials → 1 and 0.86).
* Where the item has a `UNIT` UOM row, the dispensing quantity is rounded: a fractional part
  **≥ 0.80 rounds up**, below that rounds down (9.99 → 10, 9.70 → 9). Without a UNIT row the
  stock quantity is used as-is.
* The GTIN is also written back onto the **Serial No** rows of the document (Purchase Receipt,
  Stock Entry and Stock Reconciliation, on submit).

### 4.4 Rules the app enforces

| Situation | Behaviour |
| --- | --- |
| Item has **Has Dispense Lot** and the line has no lot | Blocked on submit, on the document types enabled in Dispensing Setting |
| **Material Transfer** of a pack that was already partly consumed | Blocked — only *full, unconsumed* packs may be transferred |
| Selling a **full pack** (stock UOM) after units were sold from it | Blocked — only unit (dispensing UOM) sales are allowed for the remainder |
| Several lots on one invoice line | Supported: the line quantity is shared out across the lots in order, each filled up to its remaining quantity |
| Cancelling a Purchase Receipt / Stock Entry / Stock Reconciliation | The lots that document introduced are posted **Out** for their remaining quantity, so the lot goes to zero and becomes `Inactive` |
| A Stock Reconciliation line counting a batch **down to zero** | Every dispensing lot of that item + batch in the document's warehouse is posted **Out** for its remaining quantity, so the lot becomes `Inactive` and can no longer be scanned, transferred or sold. **Cancelling** the reconciliation posts the same quantity **back** (`In`) and the lots are dispensable again |
| A zeroed lot is received again (Purchase Receipt / Stock Entry / Stock Reconciliation with the same serial) | The lot is **reactivated** with the received quantity and keeps its history |
| Cancelling a Material Transfer | Lots are **moved back** to the source warehouse (no Out/In entries) |
| Return (credit note / return DN) | Lots on the returned rows are **restored** (In). If the return rows carry no lot, the app inherits the lots from the original document row automatically, in the form and on submit |
| Manual correction needed | Open the Dispensing Lot and use **Add Transaction** (`...doctype.dispensing_lot.add_transaction`), or the Stock Reconciliation actions below |

### 4.5 Dispensing Lot form

Fields: *Item*, *Item Name*, *Batch*, *Warehouse*, *Source DocType* / *Source Document*,
*Serial No* (the document name — lots are auto-named by serial), *GTIN*, *Stock UOM*,
*Dispensing UOM*, *Status*, *Initial Qty*, *Remaining Qty* and the **Transactions** table
(*Posting Date*, *Type* `Out / In / Transfer`, *Qty*, *UOM*, *Reference DocType*,
*Reference Name*, *Remarks*).

---

## 5. Stock document flows

### 5.1 Purchase Receipt (goods in)

1. Create the Purchase Receipt (from a Purchase Order or manually) and set the warehouses.
2. Scan each pack into its row (**Scanner** column) — batch, serial, GTIN and expiry come from
   the barcode, and a new row is added when you scan a different batch.
3. Add `Expiry Date` / `Manufacturing Date` if the barcode did not carry them (they are pushed
   onto the Batch on submit).
4. Optional: **Actions → Batch Label Print** to print medication labels for the received packs.
5. **Submit**: batches get their dates, GTIN is stamped on the serials and one **Dispensing
   Lot** per pack is created.

### 5.2 Stock Entry

* Header scanner `custom_custom_scanner` and a row `Scanner` column, same behaviour as the
  Purchase Receipt.
* Material Issue / Material Receipt consume and create lots like a receipt.
* **Material Transfer** moves whole packs only: the lot follows the pack to the destination
  warehouse (and is created there if the serial was new); cancelling the entry moves it back.
* **Actions → Batch Label Print** and **Actions → Update Batch Expiry Dates**.

### 5.3 Stock Reconciliation

1. Create the reconciliation with *Purpose* (`Opening Stock` or `Stock Reconciliation`) and the
   *Default Warehouse*.
2. Scan into the rows: *Current Qty*, *Current Valuation Rate*, *Quantity Difference* and the
   amounts are recalculated, and the row being scanned is highlighted while you work.
3. **Actions → Zero Batch from Chosen Warehouse** (available on a **draft** as soon as a *Default
   Warehouse* is chosen) — a shortcut for counting a whole location down to zero without scanning:
   it lists every batch holding stock in that warehouse with the quantity on hand, the valuation
   from the ledger and the dispensing lots of the batch, and fills the form with one line per batch
   set to quantity `0`. If the form already has lines, choose whether to **replace** them or **add
   to** them. Nothing is saved by the button — review the lines and submit the reconciliation.
4. **Actions → Batch Label Print** (row range → review → print).
5. **Submit** — batch dates and GTIN are set and dispensing lots are created for the scanned packs.
   On a document whose lines count a batch down to zero, submitting sets the dispensing lots of that
   batch to `Inactive` instead.
6. On a **submitted** reconciliation three more Actions are available:
   * **Dispensing Lots** — lists every dispensing lot this reconciliation affects (item, batch,
     lot, remaining qty, status) so you can verify what was recorded.
   * **Zero Unreconciled Batches** — shows the batch/warehouse combinations still holding stock in
     this document's warehouse that the reconciliation does not cover (quantity on hand, valuation
     and the dispensing lots found for each batch) and creates a draft Stock Reconciliation with
     one **zero-quantity line per combination**. Submitting that draft counts those batches down to
     zero **and sets their dispensing lots to `Inactive`**, so nothing left in the system can be
     dispensed from a batch that was written off; cancelling the draft posts the quantities **back**
     and the lots become dispensable again. Where lot validation is on, each line must carry a
     dispensing lot before the draft can be submitted.
   * **Correct Lot Quantities** — a one-time repair for legacy documents whose lot quantities
     were recorded incorrectly: it previews the lots that can be auto-corrected from the
     document's line totals, then sets their initial/remaining quantities.
7. Cancelling reverses the lots the document introduced. When the document counted a batch down to
   zero, cancelling puts those lots back in stock instead.

### 5.4 Stock Scanner (cycle count on the floor)

**Stock Scanner** is a submittable counting sheet (`MAT-RECO-.YYYY.-`) with a *Purpose*
(`Opening Stock` / `Stock Reconciliation`), a *Default Warehouse*, the scanned rows and a
*Stock Recon Created* marker. It is the scan-first way to produce a Stock Reconciliation.

1. New **Stock Scanner** → set *Company*, *Purpose*, *Posting Date* and *Default Warehouse*.
2. Scan every pack; rows carry `Barcode`, `Scanner`, quantity, UOM, batch, serial/dispensing
   lot, GTIN, manufacturing and expiry dates, plus the current stock figures. A row whose batch
   was deleted is recreated automatically so a draft scanner stays editable.
3. **Submit** the scanner (where the setting is on, the scanned packs must carry a dispensing
   lot).
4. **Actions → Create Stock Reconciliation** → select one or more of your **submitted scanners
   that are not yet used** and click **Create**. The app builds one Stock Reconciliation from
   them (purpose, difference account, cost center and accounts pre-filled) and links it back on
   the scanner.
5. On the scanner, **Actions → Stock Reconciliation** jumps to the created document. The
   *Stock Recon Created* flag is ticked only when that reconciliation is **submitted**; if it is
   cancelled or deleted the scanner is released and can be used again.

---

## 6. Sales and dispensing

### 6.1 Sales Invoice

* Each item row has a **Dispensing Lot** field. Its picker is filtered by the row's item and
  batch, and to lots that are still usable (`Active` / `Partially Sold` with remaining
  quantity). On a **return** all non-inactive lots are offered, so a delivered pack can be put
  back.
* The field becomes **mandatory** for items with **Has Dispense Lot** when the invoice updates
  stock (`Update Stock` ticked).
* Entering a lot that belongs to another item or batch is rejected with a message.
* **Submit** posts an **Out** on every lot on the line (one pack per lot when the line carries
  several serials) — or **In** for a return, which makes the lot usable again.
* **Cancel** posts the opposite transactions; the app checks first that they were not already
  reversed.
* Returns created from the original invoice carry the lots over; if the field is empty the app
  fills it from the original document automatically (both in the form and just before submit).

### 6.2 Delivery Note (hospital POS)

When the POS creates a **Delivery Note** from a Sales Order, the lots are consumed **on the
Delivery Note** (not only on the invoice): the same validation applies before submit, the Out
transactions are posted on submit and restored on cancel.

### 6.3 Price lists (OP / IP)

`...customize.patient_pricing.set_price_list_for_patient` runs on **Sales Order**, **Sales
Invoice** and **Quotation**: an **inpatient** is billed from the **IP Selling** price list, an
**outpatient** from **OP Selling**. See
[user_manual_accounts.md](user_manual_accounts.md#2-patient-pricing-op--ip).

---

## 7. Price Update

Bulk price changes with an audit trail:

1. New **Price Update** → *Company*, *Posting Date*, *Cost Center*.
2. Add one **Price Update Detail** row per item: *Item* (name, group and *Current Price* come
   with it), *New Price*, and optionally *Batch* + *Expiry Date* for a batch-specific price.
   A new price of zero or less is rejected.
3. **Submit** — for each row the app updates the **Standard Selling** price list:
   * existing Item Price → its rate is updated and the previous rate is stored in
     *Current Price*,
   * no Item Price → one is created (dated the posting date, batch-specific when a batch is
     given) and *Current Price* is set to 0 to mark it as created by this document.
4. **Cancel** restores the previous rate, or deletes the Item Price rows this document created.

---

## 8. Expiry handling

Expired batches are moved out of the selling warehouses into the site's expiry warehouse.

1. Set **Healthcare Settings → Default Expiry Warehouse** (it must belong to a company).
2. Either let the **daily scheduled job** run, or trigger it manually:
   **Stock Settings → Move Expired Batches**.
3. For every batch whose `Expiry Date` is in the past and which still has stock outside the
   expiry warehouse, the app creates a **Material Transfer Stock Entry** into the expiry
   warehouse and reports the list of entries it created. Batches already in the expiry
   warehouse are skipped.
4. If the setting or the warehouse is missing, the job reports it instead of failing silently
   (*"Default Expiry Warehouse is not set in Healthcare Settings."*).

---

## 9. Stock reports

### 9.1 Dispensing Lot Ledger

**Dispensing Lot Ledger** (`Beveren Health` → reports; ref doctype *Dispensing Lot*) is the
row-by-row movement of every pack. Filters: **From Date**, **To Date**, *Item*, *Batch*,
*Warehouse*, *Cost Center*, *Dispensing Lot*, *Movement* (`Out / In / Transfer`),
*Transaction DocType* and *Status*.

Columns: Date, Days (age of the lot), Dispensing Lot, Batch, Item, Item Name, Warehouse,
Cost Center, Movement, Qty, UOM, Transaction DocType, Transaction, Remaining Qty, Status,
Remarks. It is the report to use for pack-level traceability and stock ageing.

### 9.2 Dispensing Lot Movement

Shipped as a **placeholder** script report (its columns are `Column 1` / `Column 2` and it
returns sample rows). Use **Dispensing Lot Ledger** instead until it is implemented.

---

## 10. Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| Scan does nothing | The scanner field must have focus; check the row is highlighted, and that a default warehouse is set (some flows need one on the form or row). |
| *"No item found for barcode …"* | The barcode is not on the Item (Item → Barcodes) and could not be resolved as a batch/serial. |
| *"Save the document first, then scan again"* | The scanner needs a saved (named) document to persist the row — save once and continue scanning. |
| Batch created with a suffixed name (`BATCH123_ITEM-001`) | The same batch number already exists for a **different item**; the original number is kept in *Original Batch ID*. |
| Row quantity grows unexpectedly | Scanning the same batch again appends a lot and recalculates the quantity — that is by design; remove the extra lots from the field if it was a double scan. |
| *Dispensing lot is mandatory* error | Item has **Has Dispense Lot** and the document type's toggle is on in **Dispensing Setting** — scan the pack or pick the lot. |
| Cannot transfer a pack | The pack was already partly consumed; only full packs can be transferred. |
| Cannot sell a full pack | The pack is partly sold — sell the remaining units in the dispensing UOM or pick another pack. |
| Labels print without a barcode | The batch barcode could not be generated (missing `python-barcode`); install it and reprint. |
| Labels show the wrong branch | Set *Branch (Cost Center)* in the print dialog; the branch line uses the cost center's `custom_cr_name` (or its name). |
| Expired batches did not move | *Default Expiry Warehouse* is not set in Healthcare Settings, or the batches have no expiry date / no stock outside the expiry warehouse. |
| Price did not change after submit | The Item Price row lives in the **Standard Selling** price list; if a customer uses another list, that list still applies. |
| Old reconciliation shows wrong lot quantities | Open it and use **Actions → Correct Lot Quantities**. |

## 11. Quick reference

| I want to … | Where |
| --- | --- |
| Create barcodes for a whole item group | Item Group → **Generate EAN Barcodes** (1.2) |
| Print pack labels from a Batch | Batch → **Actions → Label Print** (3.1) |
| Print labels for received rows | Purchase Receipt / Stock Entry / Stock Reconciliation → **Actions → Batch Label Print** (3.2) |
| Require lots on a document type | **Dispensing Setting** toggles (4.2) |
| See which packs a reconciliation created | Stock Reconciliation → **Actions → Dispensing Lots** (5.3) |
| Write off a whole warehouse without scanning | Stock Reconciliation (draft) → **Actions → Zero Batch from Chosen Warehouse** (5.3) |
| Write off batches a reconciliation missed | Stock Reconciliation → **Actions → Zero Unreconciled Batches** (5.3) |
| Count stock with a scanner | **Stock Scanner** → submit → **Create Stock Reconciliation** (5.4) |
| Trace one pack | **Dispensing Lots** list or the *Dispensing Lot Ledger* report (9.1) |
| Move expired stock | **Stock Settings → Move Expired Batches** (8) |
| Change selling prices in bulk | **Price Update** (7) |
