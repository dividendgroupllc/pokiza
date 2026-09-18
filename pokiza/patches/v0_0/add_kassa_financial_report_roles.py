"""Allow the Kassa role to see the financial reports used in its workspace."""

import frappe


REPORTS = ("Balance Sheet", "Profit and Loss Statement")
ROLE = "kassa"


def execute():
    for report_name in REPORTS:
        if not frappe.db.exists("Report", report_name):
            continue

        custom_role_name = frappe.db.get_value(
            "Custom Role", {"report": report_name}, "name"
        )
        if custom_role_name:
            custom_role = frappe.get_doc("Custom Role", custom_role_name)
        else:
            custom_role = frappe.new_doc("Custom Role")
            custom_role.report = report_name
            custom_role.ref_doctype = frappe.db.get_value(
                "Report", report_name, "ref_doctype"
            )

        if ROLE not in {row.role for row in custom_role.roles}:
            custom_role.append("roles", {"role": ROLE})
            custom_role.save(ignore_permissions=True)

    frappe.clear_cache()
