import frappe
from frappe import _
from frappe.core.doctype.role.role import get_info_based_on_role
from frappe.utils import add_days, date_diff, escape_html, formatdate, get_url_to_form, getdate, today
from frappe.utils.user import get_users_with_role

# Employee document expiry reminders (scheduler job)
# ---------------------------------------------------------------------------
# Applies to every document stored in the Documents child table of the Employee
# (Employee Document). The first reminder goes out 90 days before the expiry
# date and then repeats every 10 days (90, 80, 70 ... 0 days left) until the
# document is renewed. Documents that are already expired keep the same 10 day
# cadence, so an overdue document is never forgotten. Recipients are all enabled
# users holding the DOCUMENT_EXPIRY_REMINDER_ROLE role.
DOCUMENT_EXPIRY_REMINDER_DAYS = 90
DOCUMENT_EXPIRY_REMINDER_INTERVAL_DAYS = 10
DOCUMENT_EXPIRY_REMINDER_ROLE = "HR Manager"


def get_documents_due_for_expiry_reminder():
    """Employee documents whose expiry reminder falls due today.

    A reminder is due when the expiry date is inside the 90 day window and the
    days left is a multiple of 10 (90, 80, ... 10, 0 and every 10 days after the
    expiry date).
    """
    reminder_date = getdate(today())
    window_end = add_days(reminder_date, DOCUMENT_EXPIRY_REMINDER_DAYS)

    documents = frappe.db.sql(
        """
        select d.parent as employee,
               e.employee_name,
               d.document_name,
               d.document_expiry_date
        from `tabEmployee Document` d
        inner join `tabEmployee` e on e.name = d.parent
        where ifnull(d.document_expiry_date, '') != ''
          and d.document_expiry_date <= %(window_end)s
        order by d.document_expiry_date, e.employee_name
        """,
        {"window_end": window_end},
        as_dict=True,
    )

    due = []
    for document in documents:
        document.days_left = date_diff(document.document_expiry_date, reminder_date)
        if document.days_left % DOCUMENT_EXPIRY_REMINDER_INTERVAL_DAYS == 0:
            document.employee_name = document.employee_name or document.employee
            due.append(document)

    return due


def get_document_expiry_reminder_status(document):
    """Human readable state of an expiring document, used in the reminder."""
    if document.days_left < 0:
        return _("Expired {0} day(s) ago").format(abs(document.days_left))
    if document.days_left == 0:
        return _("Expires today")
    return _("Expires in {0} day(s)").format(document.days_left)


def get_document_expiry_reminder_subject(documents):
    """Subject / title used for the Desk alert and the reminder email."""
    if any(document.days_left < 0 for document in documents):
        return _("Reminder: {0} employee document(s) expiring or expired").format(len(documents))
    return _("Reminder: {0} employee document(s) expiring within {1} days").format(
        len(documents), DOCUMENT_EXPIRY_REMINDER_DAYS
    )


def get_document_expiry_reminder_message(documents):
    """HTML digest of the documents due for renewal, shared by the alert and the email."""
    rows = "".join(
        "<tr>"
        f'<td><a href="{get_url_to_form("Employee", document.employee)}">'
        f"{escape_html(document.employee)}</a></td>"
        f"<td>{escape_html(document.employee_name)}</td>"
        f"<td>{escape_html(document.document_name or '')}</td>"
        f"<td>{formatdate(document.document_expiry_date)}</td>"
        f"<td>{escape_html(get_document_expiry_reminder_status(document))}</td>"
        "</tr>"
        for document in documents
    )

    return (
        "<p>"
        + _(
            "The following employee documents are due for renewal. Please renew them and "
            "update the Documents table of the employee."
        )
        + "</p>"
        + "<table class='table table-bordered'><thead><tr>"
        + f"<th>{_('Employee ID')}</th>"
        + f"<th>{_('Employee Name')}</th>"
        + f"<th>{_('Document')}</th>"
        + f"<th>{_('Expiry Date')}</th>"
        + f"<th>{_('Status')}</th>"
        + f"</tr></thead><tbody>{rows}</tbody></table>"
    )


def notify_expiring_employee_documents():
    """Daily scheduler job: remind HR Managers about expiring employee documents.

    Runs every day but only sends when a document is on its 10 day cadence, so HR
    Managers hear about it from 90 days before the expiry date until it is renewed.
    Each HR Manager gets a Desk notification (bell) and one digest email is sent to
    the whole role.
    """
    documents = get_documents_due_for_expiry_reminder()
    if not documents:
        return

    subject = get_document_expiry_reminder_subject(documents)
    message = get_document_expiry_reminder_message(documents)

    # Desk notification: one log per HR Manager so each of them sees it in the bell.
    # "Alert" notifications are in-app only (frappe.notification_skip_email_types),
    # the reminder email is sent separately below.
    for user in get_users_with_role(DOCUMENT_EXPIRY_REMINDER_ROLE):
        frappe.get_doc(
            {
                "doctype": "Notification Log",
                "for_user": user,
                "type": "Alert",
                "subject": subject,
                "email_content": message,
            }
        ).insert(ignore_permissions=True)

    recipients = get_info_based_on_role(
        DOCUMENT_EXPIRY_REMINDER_ROLE, "email", ignore_permissions=True
    )
    if not recipients:
        return

    try:
        frappe.sendmail(
            recipients=recipients,
            subject=subject,
            message=message,
            header=[_("Employee Document Expiry Reminder"), "orange"],
            now=frappe.in_test,
        )
    except frappe.OutgoingEmailError:
        frappe.log_error(
            title=_("Employee document expiry reminder email could not be sent"),
            message=frappe.get_traceback(),
        )


def notify_ending_probation_period():
    notify_date = add_days(today(), 30)
    employees = frappe.get_all("Employee", fields=["name", "employee_name", "date_of_joining", "custom_probation_period", "custom_is_probation_period_"])
    for emp in employees:
        if emp.custom_is_probation_period_:
            probation_period = add_days(emp.date_of_joining, emp.custom_probation_period)
            if getdate(probation_period) < getdate(notify_date):
                message = f"Employee {emp.employee_name} probation period is going to end on {formatdate(probation_period)}."
                frappe.get_doc({
                        "doctype": "Notification Log",
                        "subject": message,
                        "document_type": "Employee",
                        "document_name": emp.name,
                        "for_user": None,
                        "for_role": "HR User",
                        "type": "Alert",
                        "seen": 0,
                        "email_content": message
                    }).insert(ignore_permissions=True)

