"""User: AI roli (User.ai_roli) o'zgarsa — Telegram a'zosidagi nusxa (TG Azo rol/bolim) ham yangilanadi."""
import frappe


def on_update(doc, method=None):
	if not doc.has_value_changed("ai_roli") or not frappe.db.exists("TG Azo", doc.name):
		return
	from pokiza.nazorat.scope import RAHBAR

	nom = doc.get("ai_roli") or None
	rol, bolim = ("Rahbar", RAHBAR) if nom == RAHBAR else ("Xodim", nom)
	frappe.db.set_value("TG Azo", doc.name, {"rol": rol, "bolim": bolim})
