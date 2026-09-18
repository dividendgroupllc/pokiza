"""Expose the custom PL Hisoboti report to the Kassa workspace."""

import frappe


REPORT = "PL Hisoboti"
ROLE = "kassa"
WORKSPACE = "Kassa-admin"


def execute():
    if not frappe.db.exists("Report", REPORT):
        return

    add_report_role()
    add_workspace_link()
    frappe.clear_cache()


def add_report_role():
    custom_role_name = frappe.db.get_value(
        "Custom Role", {"report": REPORT}, "name"
    )
    if custom_role_name:
        custom_role = frappe.get_doc("Custom Role", custom_role_name)
    else:
        custom_role = frappe.new_doc("Custom Role")
        custom_role.report = REPORT
        custom_role.ref_doctype = frappe.db.get_value(
            "Report", REPORT, "ref_doctype"
        )

    if ROLE not in {row.role for row in custom_role.roles}:
        custom_role.append("roles", {"role": ROLE})
        custom_role.save(ignore_permissions=True)


def add_workspace_link():
    if not frappe.db.exists("Workspace", WORKSPACE):
        return

    workspace = frappe.get_doc("Workspace", WORKSPACE)
    if any(
        row.link_type == "Report" and row.link_to == REPORT
        for row in workspace.links
    ):
        return

    link = workspace.append(
        "links",
        {
            "label": REPORT,
            "type": "Link",
            "link_type": "Report",
            "link_to": REPORT,
            "report_ref_doctype": frappe.db.get_value(
                "Report", REPORT, "ref_doctype"
            ),
        },
    )

    standard_pl_index = next(
        (
            index
            for index, row in enumerate(workspace.links)
            if row.link_type == "Report"
            and row.link_to == "Profit and Loss Statement"
        ),
        None,
    )
    if standard_pl_index is not None:
        workspace.links.remove(link)
        workspace.links.insert(standard_pl_index + 1, link)

    workspace.save(ignore_permissions=True)
