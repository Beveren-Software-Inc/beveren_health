# Beveren Health — User Manual (HR, Attendance & Payroll)

This manual covers the people processes: employee records, shifts, attendance, less time,
overtime, payroll, gratuity (indemnity), full-and-final settlement, appraisals, training,
HR policies, employee documents and assets.

* Pharmacy stock / scanning / dispensing → [user_manual_stock.md](user_manual_stock.md)
* Accounts, cost centers, VAT → [user_manual_accounts.md](user_manual_accounts.md)
* Configuration, scheduled jobs, scripts, troubleshooting → [operations.md](operations.md)

## Roles used

| Role | Typical use |
| --- | --- |
| `HR Manager` | HR master data, payroll, indemnity, FnF, policy documents, document-expiry alerts |
| `HR User` | Day-to-day HR work, probation reminders |
| `System Manager` | Configuration, settings doctypes, manual "last sync" refresh, scripts |
| `Employee` (role) | Gets the *Frappe HR* desk icon for self-service (leave, expenses, payslips) |

> Several processes end in an `Additional Salary` document, which HRMS picks up when you run
> **Payroll Entry** for the period. Unless stated otherwise, the payroll date those documents use
> is the 28th of the month following the period you processed.

---

## 1. Employee records

### 1.1 Fields that are mandatory at this site

The customization makes these fields required on **Employee**, on top of HRMS' own
requirements (Company, Date of Joining, Designation, Department, …):

| Field | Notes |
| --- | --- |
| `Nationality` | Link to the **Nationality** doctype (master data shipped by the app) |
| `Religion` | Link to the **Religion** doctype (master data shipped by the app) |
| `CPR Number` | HRMS field `employee_number`, relabelled **CPR Number** |
| `Designation`, `Department` | Made required by Property Setter |

Employee IDs use the `S.###.` series only; the *Series* field is hidden on the form.

### 1.2 Additional fields on the Employee form

| Field / section | What it is for |
| --- | --- |
| `Is Probation Period ?` + `Probation Period (Days)` | Drives the weekly probation-ending reminder |
| `Contract Expiry` | Shown only when *Employment Type* is `Contract` |
| `Is Overtime Payable ?` | Copied to the Overtime Slip; only payable slips create Additional Salary rows |
| `Is Less Time Deductible ?` | Copied to Less Time Entry; only deductible entries are deducted from overtime |
| `Standard Working Hours` | Default daily hours |
| `Payroll Cost Center` | Fetched from the Department; used by payroll entries |
| `Visa Status` | `Company Visa / Dependent Visa / Independent Visa / National - With Gosi / National - Without Gosi` |
| `Under GOSI Registered ?` | Shown for Bahraini employees on a GOSI visa; when ticked, Indemnity is zero |
| `Years of Service` | Read-only, computed from Date of Joining → Relieving Date |
| `Signature` | Attach image used on printed documents |
| Approvers | `Expense Approver`, `Leave Approver`, `Shift Request Approver` |
| Health insurance | `Health Insurance Provider`, `Health Insurance No` |
| Bank details | `Employee Name for Bank`, `IFSC Code`, `MICR Code`, `Provident Fund Account`, `PAN Number` |
| Other | `Alternate Mobile 1`, `Alternate Mobile 2`, `Employee Attendance Code` |

### 1.3 Documents (CPR / NHRA) — warnings you will see

CPR and NHRA are recorded as rows of the **Documents** table (`custom_documents` →
**Employee Document**): set *Document Name* (`CPR`, `NHRA`, …), *ID Number*,
*Document Expiry Date*, attachment and remarks.

On save the app prints a **warning** (never a block):

* **CPR Document Missing** — no `CPR` row exists.
* **NHRA Document Missing** — no `NHRA` row and the Designation is one of
  `NURSE`, `DOCTOR`, `GP DOCTOR`, `CONSULTANT`, `HEAD NURSE`, `LAB TECHNICIAN`.
* **NHRA Expiry Date Missing** — an `NHRA` row exists without a *Document Expiry Date*
  (for any designation).

### 1.4 Feeding hours (nursing mothers)

**Feeding Hours Entitlement** records the statutory paid feeding break so the less-time
engine does not dock it.

1. Create **Feeding Hours Entitlement** for the employee.
2. Enter the `Child Date of Birth`. The app then fills
   *Entitlement Start* = date of birth, *Entitlement End* = DOB + 12 months,
   *Current Hours / Day* = **2h** before 6 months, **1h** from 6–12 months, **0** afterwards
   and sets *Status* to `Active` or `Expired`.
3. Nothing else to do: Attendance subtracts the entitlement from standard working hours and
   stores it in `custom_feeding_hours`.

---

## 2. Shifts, holidays and attendance

### 2.1 Shift Type

* *Standard Working Hours* (`custom_standard_working_hours`) is calculated from Start/End
  Time — wrapping over midnight — both while you type and again on save.
* `Weekly Off` is **fetched** from the selected **Holiday List**.
* On the first save the Shift Type is **renamed** to
  `<hours> Hours Shift <startHour>-<endHour> <WeeklyOff>-Off`
  (for example `8 Hours Shift 7-15 Friday-Off`), once hours, times and weekly off are present.
* **Holiday List is mandatory on Shift Type** at this site.
* `Allow Less Time` + `Less Time Type` decide which kind of shortfall this shift produces.

### 2.2 Holiday List

On a saved Holiday List, `Country` and `Weekly Off` are read-only — they are inherited data
and must be corrected at the source, not edited per list.

### 2.3 Shift Assignment

1. Create **Shift Assignment** for the employee and period.
2. `Weekly Off` and `Less Time Type` are fetched from the Shift Type.
3. The employee's **Holiday List Assignment** rows are **not** submitted automatically: a
   helper exists (`customize.shift_assignment.on_submit_shift_assignment`, which submits the
   matching draft Holiday List Assignments for the employee and period) but it is **not wired**
   in `hooks.py`. Submit those assignments manually after rostering, or wire the hook if you
   want it automatic.

### 2.4 How Attendance is computed automatically

When HRMS auto-creates Attendance from Employee Checkins, the app fills:

| Attendance field | Value |
| --- | --- |
| `standard_working_hours` | Shift End − Start, minus the employee's paid feeding hours |
| `custom_feeding_hours` | 2 / 1 / 0 hours from Feeding Hours Entitlement |
| `custom_grace_hours` | Late-in / early-out time **within** the shift's grace periods, added back to `working_hours` |
| `custom_less_time_type` | The shift's Less Time Type — set only when `working_hours` < `standard_working_hours` |
| `custom_actual_lesstime_duration` | `standard_working_hours` − `working_hours` (the shortfall in hours) |

`Grace Hours`, `Less Time Type` and `Actual Less Time Duration` are read-only.

### 2.5 Missed punch — Employee Checkin Request

Use this when a real IN or OUT punch never registered (Attendance Request works on whole
dates and cannot express a single missing punch).

1. New **Employee Checkin Request** → select *Employee* (must be Active), *Log Type*
   (`IN` / `OUT`), *Punch Time* and a *Reason*.
2. On save the app validates the punch time (not in the future, not before the joining
   date), rejects duplicates (same employee + log type + time, and any existing Employee
   Checkin at that time) and resolves *Shift* from the employee's active Shift Assignment
   for that date — the field is read-only, do not fill it manually.
3. Save, then submit the document (or route it through your approval workflow; the
   `Draft / Pending Approval / Approved / Rejected / Cancelled` statuses are built in).
4. On **submit** an **Employee Checkin** is created and linked back on
   `custom_checkin_request`; the request shows `Approved`, the approver and the timestamp.
   A request submitted with status `Rejected` creates **no** punch.
5. To undo: cancel the request. If the punch has already been consumed by an Attendance
   record the app refuses — repair that Attendance first; otherwise the punch is deleted so
   attendance cannot keep counting an unauthorised punch.

The doctype is linked in the **HR Setup** and **Shift & Attendance** workspaces (re-applied
on every migrate).

### 2.6 Refreshing "Last Sync of Checkin"

HRMS only marks attendance after `last_sync_of_checkin` has passed. If attendance stops
being generated:

1. Open the **Shift Type** list.
2. Click **Update Last Sync For All Shifts** → confirm.
3. The app sets each shift's last sync to the latest Employee Checkin of that shift. The
   same logic also runs hourly in the background.

### 2.7 Employee document expiry reminders

A daily job alerts and emails `HR Manager` when a document is due for renewal: from **90
days** before the expiry date on a **10-day cadence** (90, 80, 70 … 10, 0 and every 10 days
after expiry). Each HR Manager gets a desk notification and one digest email listing the
employee, document, expiry date and days remaining.

---

## 3. Less time and overtime

The two engines work on the same **21st → 20th** pay window and are linked: overtime is
reduced by the less time of the month, and a shortfall bigger than the overtime comes back
as a less-time deduction.

### 3.1 Less Time Type (master data)

Create **Less Time Type** for each kind of shortfall (late arrival, early departure,
unauthorised absence hours, …):

| Field | Use |
| --- | --- |
| `Less Time Salary Component` | The salary component the shortfall posts to |
| `Less Time Amount Calculation` | `Salary Component Based` (uses the components below) or `Fixed Hourly Rate` |
| `Applicable Salary Components` | Earned components used to derive the hourly rate when calculation is *Salary Component Based* |
| `Hourly Rate` | Used when calculation is *Fixed Hourly Rate* |

With *Salary Component Based*, the hourly rate is derived from the employee's Salary
Structure Assignment: the amount of the applicable components divided by **30 days** and then
by the shift's standard working hours.

### 3.2 Less Time Entry — daily shortfall per period

1. New **Less Time Entry** → select *Employee* and set *Posting Date*.
   The period (*Start Date* = 21st of the previous month, *End Date* = 20th of the payroll
   month) is derived from the employee's Salary Structure Assignment; without one you get
   *"Salary Structure not assigned for employee …"*.
2. Click **Fetch Less Time Details**. The app pulls every **submitted, Present** Attendance
   in the period that carries a `Less Time Type` and a shortfall, and builds the
   **Less Time Details** rows (Reference Document, Date, Less Time Type, Less Time Duration,
   Standard Working Hours). If nothing is found it reports
   *"No attendance records found for employee … between … and …"*.
3. Review the two read-only totals:
   * *Total Less Time Duration (in Hours)* — sum of the rows.
   * *Total Less Time Duration (in Hours) (After Compensation)* — the running figure after
     overtime compensation.
4. Submit. Overlapping entries for the same employee are rejected
   (*"Less Time Entry … has been created between … and …"*).

`Is Less Time Deductible ?` is fetched from the Employee. **Only entries with it ticked are
picked up by the Overtime Slip.**

### 3.3 Overtime Type (master data)

Create **Overtime Type** for each overtime rate:

* HRMS fields: *Standard Multiplier*, *Weekend Multiplier*, *Public Holiday Multiplier*,
  *Applicable for Weekend / Public Holiday*, *Maximum Overtime Hours Allowed*,
  *Overtime Salary Component*, *Overtime Calculation Method*.
* Site additions (both **mandatory**): *Rate Change Cutoff Hours* and
  *Rate Change Multiplier*. Hours **within** the cutoff are paid at the normal multiplier,
  hours **beyond** it at the rate-change multiplier. Example: cutoff 2, multiplier 1.5,
  rate-change multiplier 2 → first 2 hours at 1.5×, every further hour at 2×.

---

### 3.4 Overtime Slip

1. New **Overtime Slip** → *Employee*, *Posting Date*, *Start Date*. The *End Date* (and
   vice-versa) is kept exactly one month apart while you type.
2. Add the **Overtime Details** rows (date, overtime type, overtime duration) — the grid is
   **not** mandatory, so a slip can be saved with zero overtime and used purely to knock down
   larger less time.
3. Save/calculate: hours are totalled and the patient-visit allowance defaults are re-applied.
4. **Submit**:
   * The employee's submitted, deductible **Less Time Entry** for the matching window
     (21st → 20th) is copied to *Reference Document* and *Total Less Time Duration*, and
     *Total Overtime Duration* becomes `overtime hours − less-time hours`.
   * If the result is **positive** and `Is Overtime Payable ?` (fetched from Employee) is
     ticked, one **Additional Salary** is submitted per overtime salary component, dated the
     **28th of the month after the End Date** — this is what payroll pays.
   * If the result is **negative**, the linked Less Time Entry is updated (its total becomes
     the negative overtime figure and *Reference Document* points at the overtime slip) and
     its less-time salary components are posted as **Additional Salary** rows instead.
5. The **Additional Salary** button is hidden on the slip on purpose — the app creates those
   documents itself.

**Patient-visit allowances (HR-154 / 155 / 156).** On the Overtime Slip:

| Field | Default | Meaning |
| --- | --- | --- |
| `Bring Patients Count` | — | Trips bringing a patient in from home |
| `Bring Patient Rate` | 10 BD | Paid per such trip |
| `Bring Patients No Show Count` | — | Went, but the patient did not come |
| `Bring Patient No Show Rate` | 5 BD | Paid per such trip |
| `Home Visit Count` | — | HOD-approved home visits |
| `Home Visit Rate` | 5 BD | Paid per home visit |
| `Patient Visit Allowance` | computed | Sum of the three (count × rate) lines |

Rates are stored on the slip so a case can be overridden; empty rates are re-filled with the
defaults and the total is recalculated on every validate. (If these fields are absent on a
fresh site the hook quietly does nothing — see
[operations.md](operations.md#optional-overtime-patient-visit-fields).)

### 3.5 Less Time Compensation — when the shortfall is not settled by overtime

1. New **Less Time Compensation** → *Employee*, *Posting Date*, *From Date*, *To Date*,
   *Compensation Frequency* (`Monthly / Bi-Monthly / Quarterly / Half-Yearly / Yearly`),
   *Salary Component* and *Hourly Rate*. `Is Less Time Deductible ?` comes from the Employee.
2. Click **Fetch LT-OT Data**. The app fills **LT Compensation Details** rows from the
   employee's submitted **Less Time Entry** and **Overtime Slip** records in the period
   (select employee, from and to date first, or you are told
   *"Please select Employee, From Date and To Date first"*).
3. Save: *Total Less Time Duration*, *Total Overtime Duration* and
   *Uncompensated Duration* (= less time − overtime) are recalculated.
4. Submit: `Uncompensated Duration × Hourly Rate` is posted as an **Additional Salary** with
   the chosen salary component, dated the 28th of the month after the *To Date*.

### 3.6 Where each figure ends up

| Source | Result |
| --- | --- |
| Attendance (automatic) | `custom_less_time_type`, `custom_actual_lesstime_duration`, grace and feeding hours |
| Less Time Entry | Period rows; the *Total* is deducted from overtime on the Overtime Slip |
| Overtime Slip (positive) | Additional Salary per overtime component, End Date + 1 month, day 28 |
| Overtime Slip (negative) | Less Time Entry updated + Additional Salary per less-time component |
| Less Time Compensation | Additional Salary for `uncompensated hours × hourly rate` |

### 3.7 Employee Penalty

**Employee Penalty** is a submittable record for disciplinary deductions:
*Posting Date*, *From Date*, *To Date*, *Reason*, *Company*, *Type of Penalty*
(**Penalty Type** master), *Employee*, *No. of Days*, numbered `HR-EP-<employee>-#####`.

It is a **record of the decision only** — no GL entry or deduction is created automatically.
To actually recover an amount, raise an **Additional Salary** with a deduction component (or
add the deduction on the Salary Slip) and quote the penalty in the reason/remarks.

---

## 4. Payroll

### 4.1 Master data

| Doctype | What to set |
| --- | --- |
| **Salary Component** | `Is Basic Salary ?` marks the basic component (used by Indemnity). Create *Deduction* components for GOSI, less time, outstanding balances … |
| **Additional Salary Type** | Reusable *Additional Salary Reason* (e.g. Bonus, OT, Indemnity) + its Salary Component |
| **Payroll Settings** | *GOSI Settings* section → *GOSI Salary Component* |
| **HR Settings** | *Indemnity Settings* → *Indemnity Cutoff Date*, *Default Indemnity Expense Account*, *Default Indemnity Payable Account* |

### 4.2 Salary Structure

1. Create the **Salary Structure** as usual (earnings, deductions, payroll frequency).
2. On **insert**, the app appends the *GOSI Salary Component* from Payroll Settings as a
   **deduction** row (amount 0, *Depends on Payment Days* ticked) unless it is already there.
   Only new structures are touched — changing the GOSI component later does not rewrite
   existing structures.
3. Assign it with **Salary Structure Assignment**. Both the less-time and the overtime
   engines derive their hourly rates from this assignment, so an employee without one cannot
   use either.

### 4.3 Salary Slip

The site works on **30-day months** and a 21st → 20th window:

1. Create the Salary Slip (or let **Payroll Entry** create it).
2. As soon as employee, frequency and dates are set, the app calls its own calculator and
   fills:
   * `Total Working Days` = **30**
   * `Payment Days` = **30**
   * `Leave Without Pay` = working days of submitted **Leave Without Pay** applications
     inside the window (21st of the previous month → 20th)
   * `Absent Days` = number of submitted Attendance rows with status `Absent` in the window
3. `Leave Without Pay` is **read-only** — correct the underlying Attendance/Leave
   Application instead of typing over it.
4. `Rounded Total` is visible on the form and prints (the HIP/HRMS default hides it).

### 4.4 Additional Salary

* `Additional Salary Reason` (Link **Additional Salary Type**) and `Remarks`
  (shown when a reason is selected) are the two fields the app adds.
* Rows created automatically: Overtime Slip, Less Time Entry, Less Time Compensation and
  Indemnity all reference their source document in `Ref Doctype` / `Ref Docname`, so you can
  always trace what an amount is for.
* For a full-and-final deduction the app books the leaver's outstanding invoices as a
  submitted Deduction Additional Salary (see [5.3](#53-outstanding-balances-on-the-statement)).

### 4.5 Running payroll

1. Run **Payroll Entry** for the period (or create Salary Slips manually).
2. Check the `Additional Salary` rows whose **Payroll Date** falls inside the slip period —
   they appear on the slip automatically.
3. Submit the slips, then book the payment/journals as usual.

---

## 5. Indemnity (gratuity) and Full and Final Settlement

### 5.1 Indemnity

**Indemnity** computes Bahrain end-of-service gratuity, cut over on the site's *Indemnity
Cutoff Date*, and pays it either through the GL or through a salary slip.

Before you start, set in **HR Settings → Indemnity Settings**: *Indemnity Cutoff Date*,
*Default Indemnity Expense Account* and *Default Indemnity Payable Account*. Without the
cutoff date the document refuses to save (*"Indemnity Cutoff Date is not configured …"*).

1. New **Indemnity** → select the *Employee*. Designation, Department, Company, Date of
   Joining, Relieving Date, Nationality and *Under GOSI Registered* are **fetched from the
   Employee and read-only**, so complete those on the Employee first.
2. Set *Cost Center*, and decide:
   * `Consider Full Salary After Cutoff Date` — tick to use the **full base salary** for the
     post-cutoff period; leave unticked to use the **basic salary** only.
   * `Pay via Salary Slip` — tick to pay through payroll, then fill `Salary Component` and
     `Payroll Date`; leave unticked to post GL entries, then fill `Expense Account` and
     `Payable Account` (both default from HR Settings).
3. Save. The app checks Date of Joining and Relieving Date, rejects a second Indemnity for the
   same employee and joining/relieving period, and computes:
   * `Base Salary` = the base of the employee's latest submitted Salary Structure Assignment;
     `Basic Salary` = the sum of the earnings whose Salary Component has
     **Is Basic Salary ?** ticked (formulas are evaluated).
   * Eligible days by the statutory scale: **15 days per year for the first 3 years
     (1095 days)**, then **30 days per year** (`× days / 365`, i.e. `45 + (days − 1095) × 30/365`).
   * The joining → relieving period is split at the cutoff date; the pre-cutoff segment is
     valued on the base salary, the post-cutoff segment on the base or basic salary according
     to the flag. Employees who joined after the cutoff get a single post-cutoff segment.
   * `Total Indemnity Amount` = pre-cutoff amount + post-cutoff amount.
4. A **Bahraini employee with *Under GOSI Registered* ticked** gets every amount zeroed
   (they are covered by GOSI instead).
5. **Submit**:
   * *Pay via Salary Slip* ticked → an **Additional Salary** is created (employee, component,
     amount, payroll date, reference `Indemnity`).
   * Otherwise → GL entries are posted: expense account debited, payable account credited with
     **party = Employee**, cost center applied. **Cancel** reverses them.

### 5.2 Full and Final Statement

The site extends HRMS' Full and Final Statement with the employee's Indemnity, an
"experience" text and the recovery of outstanding sales invoices.

1. Create **Full and Final Statement** for the employee. HRMS computes the components from the
   Employee profile, Salary Structure and the relieving date.
2. Site fields filled automatically (read-only unless stated):
   * `Total Experience` — e.g. `3 years 2 months and 11 days` (relieving date + 1 day).
   * `Base Salary`, `Basic Salary`, `Nationality`, `Under GOSI Registered ?` — copied from the
     Employee / latest Indemnity.
   * `Indemnity` — the linked Indemnity document (only for the same employee).
   * `Cutoff Date` — defaults to `2024-03-01`, the site's go-live cutoff.
3. One statement per employee per joining + relieving period is allowed
   (*"A Full and Final Statement … already exists for employee …"*).
4. **Indemnity**: if none exists yet, use **Create → Generate Indemnity** on the saved draft.
   The app raises and submits the Indemnity, links it back, and pushes its two figures into the
   **Payables** table as `Indemnity Reward (Before Cut-Off Date)` and
   `Indemnity Reward (After Cut-Off Date)` (account from the Indemnity, status `Unsettled`,
   reference type `Indemnity`). The rows are refreshed — never duplicated — on every save.
   Picking the Indemnity by hand does the same from the client.
5. Add any other Payables/Receivables rows. The reference-document picker is restricted to
   **HR / Payroll / Loan Management** doctypes plus **Indemnity**; `Reference Document`
   becomes mandatory as soon as a type is chosen.
6. The default print format is **FFS Summary**. Tick **Want Print ?** on the asset /
   outstanding rows you want printed.
7. **Submit**: HRMS books the settlement Journal Entry; the app makes sure the
   outstanding-balance line (below) carries the **Employee as party**, so the receivable lands
   on the employee's ledger.

### 5.3 Outstanding balances on the statement

Controlled from **Healthcare Settings**:

* `add_outstanding_balance_to_full_and_final_settlement` — turns the feature on.
* `outstanding_balance_salary_component` — the **Deduction** Salary Component used for the
  recovery (an Additional Salary cannot hold a negative amount, so the recovery is booked as a
  deduction).

With the flag on, every save of a **draft** statement:

1. Finds the leaver's unpaid **Sales Invoices** (linked through `Sales Invoice.custom_employee`
   or `Customer.custom_employee`) and totals the outstanding amounts.
2. Adds or refreshes one **Receivables** row labelled `Outstanding Sales Invoice`, with the
   receivable account, the invoice-wise breakdown in *Remark*, status `Unsettled` and a
   reference to the **Additional Salary** raised for it.
3. Raises (and submits) a Deduction **Additional Salary** for the total. One raised earlier is
   reused when the amount still matches, refreshed while it is still a draft, or cancelled and
   re-raised once the balance has moved on. If Payroll has already consumed the amount in a
   Salary Slip it is left standing and HR is asked to recover the difference by hand.
4. Only the statement references that Additional Salary (never the reverse), so a statement
   raised by mistake can still be cancelled or deleted.

---

## 6. Performance, training, policy, assets and exit

### 6.1 Appraisal

1. Create the **Appraisal Cycle**; set `Appraisal Type`
   (`Probation / Annual / Others`) — it is carried onto every Appraisal raised under the
   cycle and shown there read-only as **Appraisal Type**.
2. Build the **Appraisal Template**. **Minimum Requirement (Out of 100)** is **mandatory** on
   each template goal and rating criterion; it also exists (and is mandatory) on the Appraisal
   Goal / Appraisal KRA / Employee Feedback Rating rows.
3. Create the **Appraisal**: the template is **not** auto-filled from the cycle any more —
   pick it yourself. Choosing a template copies its goals/KRAs and rating criteria, including
   the minimum requirements, into the document.
4. Score the document as usual. `Final Score (%)` is available next to the final score, and
   the goals/criteria grids support **bulk edit** and dynamic row height.

### 6.2 Employee Performance Feedback

* `Feedback Type` — `Annual` (default) or `Provision`.
* `Employment Type` is copied read-only from the Employee.
* **Minimum Requirement (Out of 100)** is mandatory on each feedback rating row.

### 6.3 Training Need Assessment (TNA)

1. Maintain **TNA Template** records (Title + Description) — the app ships a fixture so the
   templates survive re-installs — and the **TNA Rating Instruction** single
   (Instructions + Formal Text).
2. New **Training Need Assessment** → *Employee*, *Evaluator*, *Date of Joining*,
   *Appraisal Cycle*, supervisor and signature fields.
3. On open the form fetches the rating instructions from the single and **rebuilds the
   Assessments table from every TNA Template** — rate the rows in the same session and save.
   A *Title* can be used only once per document.
4. Enter a **Ratings** value (0–5) per row, or tick **Not Applicable** (forced to 0 and
   excluded from the totals). On save: `Total Rating` = Σ rating × 5 and
   `Total % Achieved` = total ÷ (applicable rows × 5) × 100.
5. Add comments, then submit.

### 6.4 HR policy documents and acknowledgement (HR-107)

1. Create **HR Policy Document**: *Policy Title*, *Category*
   (`HR Policy / Code of Conduct / Clinical Policy / Safety / Infection Control / Quality /
   Other`), *Version*, *Effective From*, optional *Next Review*, the *Policy Document*
   attachment and *Summary*.
2. Choose the audience: tick **All Employees**, or filter by *Company*, *Department* and
   *Designation*. Tick **Requires Acknowledgement** if employees must confirm they read it,
   and set the *Acknowledge By* deadline.
3. Save/publish (`Is Published`) — the app fans out one **HR Policy Acknowledgement** row per
   active employee, alerts each employee who has a linked User (desk notification) and adds a
   comment to the policy stating how many employees it was shared with. Re-saving does not
   duplicate rows.
4. Employees read their own policies and status through
   `...customize.hr_policy.my_policies` and confirm with
   `...customize.hr_policy.acknowledge_policy` (stamps *Acknowledged On*). HR pulls compliance
   with `...customize.hr_policy.policy_compliance` (total / acknowledged / pending / rows).

### 6.5 Employee Visa Renewal Consent

1. New **Employee Visa Renewal Consent** (series `HR-VRC-.#####`) → *Employee* (name, code,
   designation, department and date of joining follow), *Application Date*, *Company*,
   *Date of Renewal*.
2. Employee decision: `I would like` → `Renew` or `Not Renew`. With **Renew**, *Renewal
   Period* (`6 / 12 / 24 Months`) becomes mandatory; with **Not Renew** it is cleared.
3. Employee signs (*Employee Signature Date*), the HOD recommends (*Recommended for Renewal*,
   *HOD* — active employees only — and *HOD's Signature Date*) and the CEO authorises
   (*Authorized by CEO*, *Authorized Period*, *CEO Signature Date*).
4. Status moves `Draft → Submitted → Cancelled` with the document.
5. Print with the **Employee Visa Renewal Consent Form** print format (see
   [operations.md](operations.md#print-format-for-visa-renewal)) and file the signed copy in
   the Employee's Documents table so the expiry reminders track it.

### 6.6 Job Requisition (replacements) and Outgoing Employee

* **Job Requisition** gains `Requisition Type` (`New` default / `Replacement`).
* On **Replacement** the *Replacement* section and the **Outgoing Employee(s)** table
  (Employee, Employee Name, Department, Designation) appear — record who is leaving so HR can
  plan the handover.

### 6.7 Asset Physical Verification

Use it for periodic asset counts:

1. New **Asset Physical Verification** (series `APV-.YYYY.-`) → *Title*, *Company*,
   *Verification Date*, *Branch / Cost Center*, *Verified By*.
2. Add one **Asset Physical Verification Item** row per asset: *Asset*, *Asset Name*,
   *Expected Location*, *Actual Location*, *Status*
   (`Found / Not Found / Moved / Damaged / Scrapped`), *Condition* (`Good / Fair / Poor`) and
   remarks.
3. Save/submit the sheet: *Total Assets*, *Found*, *Not Found*, *Discrepancies* and *Remarks*
   summarise the exercise.

### 6.8 Probation reminder

A weekly job alerts the `HR User` role when an employee's probation ends within the next
**30 days** (`probation end = Date of Joining + Probation Period (Days)`, only for employees
with *Is Probation Period ?* ticked).

---

## 7. Quick reference

| I want to … | Go to |
| --- | --- |
| Record a missed punch | Employee Checkin Request (2.5) |
| Fix attendance that is not being generated | Shift Type list → **Update Last Sync For All Shifts** (2.6) |
| Pay overtime | Overtime Slip → submit → Additional Salary (3.4) |
| Deduct short hours | Less Time Entry → **Fetch Less Time Details** → submit (3.2) |
| Settle short hours not offset by overtime | Less Time Compensation → **Fetch LT-OT Data** → submit (3.5) |
| Recalculate a payslip's LWP / absent days | Open the Salary Slip (recalculated on load) (4.3) |
| Pay gratuity | Indemnity → submit (5.1) |
| Settle a leaver | Full and Final Statement → **Create → Generate Indemnity** → submit (5.2) |
| Share a policy and track reading | HR Policy Document → publish (6.4) |
| Record a disciplinary penalty | Employee Penalty + an Additional Salary deduction (3.7) |
| Record visa renewal intent | Employee Visa Renewal Consent (6.5) |
| Count assets | Asset Physical Verification (6.7) |

## 8. Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| *"Salary Structure not assigned for employee …"* | No submitted Salary Structure Assignment on/before the posting date — assign the structure first. |
| *"No attendance records found …"* on Less Time Entry | No submitted **Present** Attendance with a `Less Time Type` in the 21st → 20th window. |
| Overtime Slip created no Additional Salary | `Is Overtime Payable ?` is unticked on the Employee, or the total after less-time compensation is ≤ 0 (the Less Time Entry is updated instead). |
| Attendance row has no less time | The punch was inside the shift's late/early grace, feeding hours covered the gap, or the Shift Type has no `Less Time Type`. |
| Indemnity saves with zeros | The employee is Bahraini with *Under GOSI Registered* ticked. |
| *"Indemnity Cutoff Date is not configured"* | Set it in HR Settings → Indemnity Settings. |
| FnF outstanding row not created | The Healthcare Settings flag `add_outstanding_balance_to_full_and_final_settlement` is off, the statement is not a draft, or the leaver has no linked unpaid Sales Invoice. |
| Employee cannot be saved | Nationality, Religion, CPR Number, Designation and Department are mandatory. |
| No document-expiry emails | No employee document is on its 10-day cadence, or the employee has no linked User. |

---
