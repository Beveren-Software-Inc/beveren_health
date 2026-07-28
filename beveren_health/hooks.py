app_name = "beveren_health"
app_title = "Beveren Health"
app_publisher = "Beveren Software"
app_description = "Beveren Health"
app_email = "diwakar@beverensoftware.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "beveren_health",
# 		"logo": "/assets/beveren_health/logo.png",
# 		"title": "Beveren Health",
# 		"route": "/beveren_health",
# 		"has_permission": "beveren_health.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/beveren_health/css/beveren_health.css"
app_include_js = [
	"/assets/beveren_health/js/dispensing_lot_scan_helpers.js",
	"/assets/beveren_health/js/warehouse_cost_center.js",
	"/assets/beveren_health/js/auto_save_scan.js",
]

# include js, css files in header of web template
# web_include_css = "/assets/beveren_health/css/beveren_health.css"
# web_include_js = "/assets/beveren_health/js/beveren_health.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "beveren_health/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_list_js = {"Shift Type" : "public/js/shift_type_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

doctype_js = {
    "Appraisal": "public/js/appraisal.js",
    # "Purchase Receipt" : "beveren_health/public/js/purchase_receipt_item.js",
    "Purchase Receipt":"public/js/purchase_receipt.js",
    "Purchase Order": "public/js/purchase_order.js",
    "Purchase Invoice": "public/js/purchase_invoice.js",
    "Employee" : "beveren_health/public/js/employee.js",
    # "Purchase Receipt" : "beveren_health/public/js/purchase_receipt_item.js",
    "Stock Settings" : "/public/js/stock_settings.js",
    "Item" : "/public/js/item.js",
    "Batch" : "public/js/batch.js",
    "Item Group": "public/js/item_group.js",
    "Overtime Slip" : "public/js/overtime_slip.js",
    "Salary Slip" : "public/js/salary_slip.js",
    "Holiday List" : "public/js/holiday_list.js",
    "Shift Type" : "public/js/shift_type.js",
    "Shift Assignment" : "public/js/shift_assignment.js",
    "Employee Checkin" : "public/js/employee_checkin.js",
    "Cost Center" : "public/js/cost_center.js",
    "Stock Reconciliation": "public/js/stock_reconciliation.js",
    "Stock Scanner": "public/js/stock_scanner.js",
    "Stock Entry": "public/js/stock_entry.js",
    "Sales Invoice": "public/js/sales_invoice.js",
    "Full and Final Statement": "public/js/full_and_final_statement.js",
}

# Svg Icons
# ------------------
# include app icons in desk
# Custom desk icon sprite (adds #icon-klik-pos, used by the Klik POS workspace).
app_include_icons = "/assets/beveren_health/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "beveren_health.utils.jinja_methods",
# 	"filters": "beveren_health.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "beveren_health.install.before_install"
# after_install = "beveren_health.beveren_health.utils.print_format_setup.create_medication_label_print_format"

after_migrate = [
    "beveren_health.beveren_health.override.hr_workspace.add_hr_workspace_links",
    "beveren_health.scripts.create_fnf_from_xlsx.run",
    "beveren_health.beveren_health.override.desk_sidebar.create_restricted_roles",
    "beveren_health.beveren_health.override.desk_sidebar.set_klik_pos_workspace_icon",
]

# Boot
# ----
# Prune the desk grid to the Healthcare app only for clinical/healthcare staff.
extend_bootinfo = [
    "beveren_health.beveren_health.override.desk_sidebar.restrict_healthcare_sidebar"
]

# Uninstallation
# ------------

# before_uninstall = "beveren_health.uninstall.before_uninstall"
# after_uninstall = "beveren_health.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "beveren_health.utils.before_app_install"
# after_app_install = "beveren_health.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "beveren_health.utils.before_app_uninstall"
# after_app_uninstall = "beveren_health.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "beveren_health.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

doc_events = {
    "Employee" : {
        "before_save" : "beveren_health.beveren_health.customize.employee.before_save"
    },
    "Salary Structure": {
        "before_insert": "beveren_health.beveren_health.customize.salary_structure.before_insert"
    },
    "Sales Invoice": {
        "validate": [
            "beveren_health.beveren_health.customize.sales_invoice.validate_return_restrictions",
            # ACC-181 OP / IP price list by admission status
            "beveren_health.beveren_health.customize.patient_pricing.set_price_list_for_patient",
        ],
        "before_submit": "beveren_health.beveren_health.customize.sales_invoice.validate_dispensing_lots",
        "on_submit": "beveren_health.beveren_health.customize.sales_invoice.update_dispensing_lots_on_submit",
        "on_cancel": "beveren_health.beveren_health.customize.sales_invoice.restore_dispensing_lots_on_cancel",
    },
    "Full and Final Statement" : {
        "before_save" : "beveren_health.beveren_health.customize.full_and_final_settlement.before_save"
    },
    "Attendance" : {
        "before_insert" : "beveren_health.beveren_health.customize.attendance.before_insert"
    },
     "Item" : {
        "on_update" : "beveren_health.beveren_health.customize.item.on_update"
    },
    "Shift Type": {
        "before_save": "beveren_health.beveren_health.customize.shift_type.before_save"
    },
    "Batch": {
        "before_save": "beveren_health.beveren_health.override.batch.before_save",
        "on_update":"beveren_health.beveren_health.utils.batch.batch_before_save",
        # "validate": "beveren_health.beveren_health.override.batch.validate_batch"
    },
    
    "Serial No": {
        "before_insert": "beveren_health.beveren_health.customize.serial_no.set_gtin_universal"
    },
    # --- Serene BRD ---------------------------------------------------------
    # HR-154 / HR-155 / HR-156 patient-visit allowances
    "Overtime Slip": {
        "validate": "beveren_health.beveren_health.customize.overtime_allowance.validate"
    },
    # HR-107 HR policy document sharing
    "HR Policy Document": {
        "on_update": "beveren_health.beveren_health.customize.hr_policy.distribute_policy"
    },
    # ACC-181 OP / IP price list by admission status
    "Sales Order": {
        "validate": "beveren_health.beveren_health.customize.patient_pricing.set_price_list_for_patient"
    },
    "Quotation": {
        "validate": "beveren_health.beveren_health.customize.patient_pricing.set_price_list_for_patient"
    },
    "Purchase Order": {
        "validate": "beveren_health.beveren_health.customize.warehouse_cost_center.set_cost_center_from_set_warehouse",
    },
    "Purchase Invoice": {
        "validate": "beveren_health.beveren_health.customize.warehouse_cost_center.set_cost_center_from_set_warehouse",
    },
    "Purchase Receipt": {
        "validate": "beveren_health.beveren_health.customize.warehouse_cost_center.set_cost_center_from_set_warehouse",
        "before_submit": "beveren_health.beveren_health.customize.dispensing_lot.validate_stock_document_dispensing_lots",
        "on_submit": [
            "beveren_health.beveren_health.customize.serial_no.update_serial_gtin",
            "beveren_health.beveren_health.customize.dispensing_lot.create_dispensing_lots_on_submit",
        ],
        "on_cancel": "beveren_health.beveren_health.customize.dispensing_lot.reverse_stock_document_dispensing_lots",
    },
    "Stock Reconciliation": {
        "validate": "beveren_health.beveren_health.customize.warehouse_cost_center.set_cost_center_from_set_warehouse",
        "before_submit": "beveren_health.beveren_health.customize.dispensing_lot.validate_stock_document_dispensing_lots",
        "on_submit": [
            "beveren_health.beveren_health.customize.serial_no.update_serial_gtin",
            "beveren_health.beveren_health.customize.dispensing_lot.create_dispensing_lots_on_submit",
            "beveren_health.beveren_health.customize.stock_scanner.mark_stock_scanners_on_reconciliation_submit",
        ],
        "on_cancel": [
            "beveren_health.beveren_health.customize.dispensing_lot.reverse_stock_document_dispensing_lots",
            "beveren_health.beveren_health.customize.stock_scanner.release_stock_scanners_from_reconciliation",
        ],
        "on_trash": "beveren_health.beveren_health.customize.stock_scanner.release_stock_scanners_from_reconciliation",
    },
    "Stock Entry": {
        "validate": "beveren_health.beveren_health.customize.warehouse_cost_center.set_cost_center_from_stock_entry_warehouse",
        "before_submit": "beveren_health.beveren_health.customize.dispensing_lot.validate_stock_entry_dispensing_lots",
        "on_submit": [
            "beveren_health.beveren_health.customize.serial_no.update_serial_gtin",
            "beveren_health.beveren_health.customize.dispensing_lot.create_dispensing_lots_on_submit",
        ],
        "on_cancel": "beveren_health.beveren_health.customize.dispensing_lot.reverse_stock_document_dispensing_lots",
    },
    "Stock Scanner": {
        "before_submit": "beveren_health.beveren_health.customize.dispensing_lot.validate_stock_scanner_dispensing_lots",
    },
}


# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"beveren_health.tasks.all"
# 	],
# 	"daily": [
# 		"beveren_health.tasks.daily"
# 	],
# 	"hourly": [
# 		"beveren_health.tasks.hourly"
# 	],
# 	"weekly": [
# 		"beveren_health.tasks.weekly"
# 	],
# 	"monthly": [
# 		"beveren_health.tasks.monthly"
# 	],
# }

scheduler_events = {
    "daily": [
        "beveren_health.beveren_health.utils.expiry_movement.move_expired_batches_to_expiry_warehouse",
    ],
    "weekly": [
        "beveren_health.beveren_health.notifications.employee_notification.notify_document_expiry",
        "beveren_health.beveren_health.notifications.employee_notification.notify_ending_probation_period"
    ],
    "hourly_long": [
        "beveren_health.beveren_health.utils.attendance.update_last_sync_for_all_shifts"
    ]
}


# Testing
# -------

# before_tests = "beveren_health.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
extend_doctype_class = {
	"Overtime Slip": "beveren_health.beveren_health.customize.overtime_slip.OvertimeSlip",
	"Appraisal": "beveren_health.beveren_health.customize.appraisal.Appraisal",
	"Employee Performance Feedback": "beveren_health.beveren_health.customize.employee_performance_feedback.EmployeePerformanceFeedback",
	"Full and Final Statement": "beveren_health.beveren_health.customize.full_and_final_statement_class.FullandFinalStatement",
	"Batch": "beveren_health.beveren_health.override.batch.CustomBatch"
}



# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "beveren_health.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "beveren_health.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["beveren_health.utils.before_request"]
# after_request = ["beveren_health.utils.after_request"]

# Job Events
# ----------
# before_job = ["beveren_health.utils.before_job"]
# after_job = ["beveren_health.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"beveren_health.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

fixtures = [
    {"doctype" : "TNA Template"},
    {
        # Employee IDs use the EMP-.###. series only (default, single option, field hidden)
        "doctype": "Property Setter",
        "filters": [
            ["doc_type", "=", "Employee"],
            ["field_name", "=", "naming_series"],
        ]
    },
    {
        # Appraisal / feedback grids: bulk edit + dynamic row height. These were
        # edited directly in the hrms app's DocType JSON, which loses them on any
        # hrms upgrade; carried here as Property Setters instead.
        "doctype": "Property Setter",
        "filters": [
            ["doc_type", "in", [
                "Appraisal Goal",
                "Appraisal Template Goal",
                "Employee Feedback Rating",
            ]],
            ["property", "in", ["allow_bulk_edit", "row_format"]],
        ]
    },
    {
        "doctype": "Custom Field",
        "filters": [
            ["name", "in", [
                "Purchase Receipt Item-custom_label_print",
                "Purchase Receipt Item-custom_label_printing",
                "Item Barcode-custom_image",
                "Purchase Receipt Item-custom_expiry_date",
                "Purchase Receipt Item-custom_manufacturing_date",
                "Cost Center-custom_cr_no",
                "Warehouse-custom_cr_no",
                "Cost Center-custom_address",
                "Cost Center-custom_letter_head",
                "Cost Center-custom_address_display",
                "Cost Center-custom_address_html",
                "Stock Entry-custom_custom_scanner",
                "Stock Reconciliation-custom_custom_scanner",
                "Item Barcode-custom_batch",
                "Purchase Receipt Item-custom_scanner",
                "Batch-custom_original_batch_id",
                "Stock Entry Detail-custom_expiry_date",
                "Stock Entry Detail-custom_manufacturing_date",
                "Stock Reconciliation Item-custom_expiry_date",
                "Stock Reconciliation Item-custom_manufacturing_date",
                "Stock Reconciliation Item-custom_scanner",
                "Stock Entry Detail-custom_scanner",
                "Stock Entry Detail-custom_column_break_ikwni",
                "Stock Reconciliation Item-custom_gstin",
                "Stock Entry Detail-custom_gstin",
                "Purchase Receipt Item-custom_gstin",
                "Serial No-custom_gtin",
                "Sales Invoice Item-custom_dispensing_lot",
                "Item-custom_has_dispense_lot",
                "Sales Invoice Item-custom_section_break_k4p2l",
                "Purchase Receipt Item-custom_dispensing_lot",
                "Purchase Receipt Item-custom_section_break_qpm82",
                "Stock Entry Detail-custom_dispensing_lot",
                "Stock Entry Detail-custom_section_break_81xt5",
                "Stock Reconciliation Item-custom_dispensing_lot",
                "Stock Reconciliation Item-custom_section_break_vv0xo",
                "Delivery Note Item-custom_section_break_o7y1z",
                "Delivery Note Item-custom_dispensing_lot",
                "Warehouse-custom_cost_center",
                "Purchase Receipt-custom_auto_save_scan_interval",
                "Stock Entry-custom_auto_save_scan_interval",
                "Stock Reconciliation-custom_auto_save_scan_interval",
            ]]
        ]
    }
]
