// Copyright (c) 2026, Sardorbek and contributors
// For license information, please see license.txt

// Mijoz Kartochkasi formasi: SKU tanlanganda norma/narx/bonus avto-tushadi,
// marja jonli hisoblanadi. Yakuniy hisob baribir serverda (validate) qayta
// tekshiriladi — bu yerdagisi faqat foydalanuvchi ko'rishi uchun.

frappe.ui.form.on("Mijoz Kartochkasi", {
	setup(frm) {
		frm.set_query("sku", "qatorlar", () => ({
			filters: { item_group: "Сотув махсулотлари", disabled: 0 },
		}));
		frm.set_query("norma", "qatorlar", () => ({
			filters: { item_group: "Готовый продукт", disabled: 0 },
		}));
	},

	refresh(frm) {
		if (!frm.is_new() && frm.doc.mijoz) {
			frm.add_custom_button(__("90 kunlik tarixdan to'ldirish"), () => {
				frappe.call({
					method: "pokiza.api.kartochka.qoralama_toldir",
					args: { mijoz: frm.doc.mijoz },
					freeze: true,
					freeze_message: __("Sotuv tarixi o'qilmoqda..."),
					callback(r) {
						const n = r.message || {};
						frappe.show_alert({
							message: __("{0} ta qator qo'shildi", [n.qator_qoshildi || 0]),
							indicator: "green",
						});
						frm.reload_doc();
					},
				});
			});
		}
	},
});

function hisobla_qator(frm, cdt, cdn) {
	const q = locals[cdt][cdn];
	const keyin = flt(q.sotuv_narxi) * (1 - flt(q.bonus_foiz) / 100);
	frappe.model.set_value(cdt, cdn, {
		bonus_keyin_narx: keyin,
		marja_som: keyin - flt(q.tannarx),
		marja_foiz: keyin ? ((keyin - flt(q.tannarx)) / keyin) * 100 : 0,
	});
}

function tannarx_yangila(frm, cdt, cdn) {
	const q = locals[cdt][cdn];
	if (!q.sku) return;
	frappe.call({
		method: "pokiza.api.kartochka.tannarx_hisobla",
		args: { sku: q.sku, norma: q.norma || null },
		callback(r) {
			if (!r.message) return;
			frappe.model.set_value(cdt, cdn, {
				tannarx: r.message.tannarx,
				tannarx_tafsilot: r.message.izoh,
			}).then(() => hisobla_qator(frm, cdt, cdn));
		},
	});
}

frappe.ui.form.on("Mijoz Kartochka Qatori", {
	sku(frm, cdt, cdn) {
		const q = locals[cdt][cdn];
		if (!q.sku) return;
		frappe.call({
			method: "pokiza.api.kartochka.sku_malumot",
			args: { sku: q.sku, mijoz: frm.doc.mijoz || null },
			callback(r) {
				if (!r.message) return;
				const m = r.message;
				const yangilash = {};
				if (m.norma && !q.norma) yangilash.norma = m.norma;
				if (m.oxirgi_narx && !flt(q.sotuv_narxi)) yangilash.sotuv_narxi = m.oxirgi_narx;
				if (m.bonus_foiz && !flt(q.bonus_foiz)) yangilash.bonus_foiz = m.bonus_foiz;
				if (!q.amal_sana) yangilash.amal_sana = frappe.datetime.get_today();
				frappe.model.set_value(cdt, cdn, yangilash).then(() =>
					tannarx_yangila(frm, cdt, cdn)
				);
			},
		});
	},
	norma: tannarx_yangila,
	sotuv_narxi: hisobla_qator,
	bonus_foiz: hisobla_qator,
});
