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
# app_include_js = "/assets/beveren_health/js/beveren_health.js"

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
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

doctype_js = {
    "Purchase Receipt" : "beveren_health/public/js/purchase_receipt_item.js",
    "Stock Settings" : "/public/js/stock_settings.js",
    "Item" : "/public/js/item.js",
    "Batch" : "public/js/batch.js",
    "Item Group" : "beveren_health/public/js/item_group.js",
    "Overtime Slip" : "public/js/overtime_slip.js",
    "Salary Slip" : "public/js/salary_slip.js",
    "Holiday List" : "public/js/holiday_list.js",
    "Shift Type" : "public/js/shift_type.js",
    "Shift Assignment" : "public/js/shift_assignment.js",
    "Employee Checkin" : "public/js/employee_checkin.js",
    "Cost Center" : "public/js/cost_center.js"
}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "beveren_health/public/icons.svg"

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
    "Sales Invoice" : {
        "validate" : "beveren_health.beveren_health.customize.sales_invoice.validate_return_restrictions"
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
        "before_save": "beveren_health.beveren_health.override.batch.before_save"
    }
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
	"Overtime Slip": "beveren_health.beveren_health.customize.overtime_slip.OvertimeSlip"
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
                "Cost Center-custom_address_html"
            ]]
        ]
    }
]