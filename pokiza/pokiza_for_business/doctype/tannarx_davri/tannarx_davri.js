// Copyright (c) 2026, Sardorbek and contributors
// For license information, please see license.txt

frappe.ui.form.on("Tannarx Davri", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Qayta hisoblash"), () => {
			frappe.confirm(
				__("Barcha SKU normativ tannarxi shu daqiqadagi xomashyo narxlarida qayta yoziladi. Davom etasizmi?"),
				() => {
					frm.call({
						doc: frm.doc,
						method: "qayta_hisobla",
						freeze: true,
						freeze_message: __("BOM'lar va ombor narxlari o'qilmoqda..."),
						callback: () => frm.reload_doc(),
					});
				}
			);
		});

		if (frm.doc.holat === "Qoralama") {
			frm.dashboard.set_headline(
				__("Bu davr QORALAMA — kartochka va sotuv uni ishlatmaydi. Tasdiqlangan qilib saqlang.")
			);
		}
	},
});
