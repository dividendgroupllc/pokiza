"""Anthropic client va AI sozlamalari."""
import frappe
from frappe.utils.password import get_decrypted_password

SETTINGS = "Pokiza AI Sozlamalari"
ROLES = ("System Manager", "AI Foydalanuvchi")

# $ / 1M token: (input, output, cache_read, cache_write_5m)
PRICES = {
    "claude-opus-5-5": (4.0, 20.0, 0.20, 5.0),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20, 2.5),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
    "claude-fable-5-1": (10.0, 50.0, 0.25, 12.5),
}


def get_settings():
    s = frappe.get_cached_doc(SETTINGS)
    return frappe._dict(
        enabled=s.enabled,
        model=(s.model or "claude-opus-5-5").strip(),
        effort=s.effort or "medium",
        max_steps=s.max_steps or 15,
        monthly_limit_usd=s.monthly_limit_usd or 0,
        sql_enabled=s.sql_enabled,
        gemini_model=(s.get("gemini_model") or "gemini-3.5-flash").strip(),
        db_ro_user=s.db_ro_user,
    )


def get_secret(fieldname):
    return get_decrypted_password(SETTINGS, SETTINGS, fieldname, raise_exception=False)


def get_client():
    import anthropic

    api_key = get_secret("api_key")
    if not api_key:
        frappe.throw("Pokiza AI Sozlamalari'da Anthropic API Key kiritilmagan")
    return anthropic.Anthropic(api_key=api_key, max_retries=2, timeout=600)


def usage_cost(model, usage):
    p = PRICES.get(model, PRICES["claude-opus-5-5"])
    inp = getattr(usage, "input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    cr = getattr(usage, "cache_read_input_tokens", 0) or 0
    cw = getattr(usage, "cache_creation_input_tokens", 0) or 0
    return (inp * p[0] + out * p[1] + cr * p[2] + cw * p[3]) / 1_000_000


def month_spent_usd():
    return frappe.db.sql(
        """SELECT COALESCE(SUM(cost_usd), 0) FROM `tabAI Xabar`
        WHERE role = 'assistant' AND creation >= DATE_FORMAT(CURDATE(), '%%Y-%%m-01')"""
    )[0][0]
