# Copyright (c) 2026, Sardorbek and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class TGAzo(Document):
	"""Telegram a'zosi. AI/ko'rsatkich roli YAGONA manbada — User.ai_roli; bu yerdagi rol/bolim uning nusxasi.

	Botdagi «👥 Xodimlar» yoki ulash havolasi rolni o'zgartirsa — User.ai_roli ham yangilanadi;
	yangi a'zoda bo'lim tanlanmagan bo'lsa — foydalanuvchining mavjud AI roli olinadi.
	"""

	def validate(self):
		from pokiza.nazorat.scope import RAHBAR

		if self.is_new() and not self.bolim and self.rol != "Rahbar":
			mavjud = frappe.db.get_value("User", self.user, "ai_roli")
			if mavjud:
				self.rol, self.bolim = ("Rahbar", RAHBAR) if mavjud == RAHBAR else ("Xodim", mavjud)

	def on_update(self):
		from pokiza.nazorat.scope import rol_tgdan

		if not (self.has_value_changed("bolim") or self.has_value_changed("rol")):
			return
		yangi = rol_tgdan(self.rol, self.bolim)
		if frappe.db.get_value("User", self.user, "ai_roli") != yangi:
			frappe.db.set_value("User", self.user, "ai_roli", yangi)
