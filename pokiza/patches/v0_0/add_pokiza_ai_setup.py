# Pokiza AI: "AI Foydalanuvchi" roli va sozlamalar standart qiymatlari
import frappe


def execute():
    if not frappe.db.exists("Role", "AI Foydalanuvchi"):
        frappe.get_doc({"doctype": "Role", "role_name": "AI Foydalanuvchi", "desk_access": 1}).insert(
            ignore_permissions=True
        )

    frappe.reload_doc("pokiza_for_business", "doctype", "pokiza_ai_sozlamalari")
    s = frappe.get_single("Pokiza AI Sozlamalari")
    for field, value in (
        ("enabled", 1),
        ("model", "claude-opus-5-5"),
        ("effort", "medium"),
        ("max_steps", 15),
        ("monthly_limit_usd", 200),
        ("sql_enabled", 1),
        ("db_ro_user", "pokiza_ai_ro"),
    ):
        if not s.get(field):
            s.set(field, value)
    s.flags.ignore_mandatory = True
    s.save(ignore_permissions=True)
    frappe.db.commit()
