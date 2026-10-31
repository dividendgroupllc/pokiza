// Copyright (c) 2026, Sardorbek and contributors
// For license information, please see license.txt

// Накладная ketma-ketligi formasi. Tartibni qatorlarni TORTIB o'zgartirasiz
// (Frappe bola jadvali o'zi beradi), bu yerdagi tugmalar esa ikki ishni
// qiladi: Excel'dan ro'yxatni bir marta joylash va o'zgargan tartibni
// mavjud kartochkalarga qo'llash.

frappe.ui.form.on("Mahsulot Tartibi", {
	refresh(frm) {
		frm.add_custom_button(__("Ro'yxatni joylash"), () => royxatniJoylash(frm));

		frm.add_custom_button(__("Kartochkalarga qo'llash"), () => kartochkalargaQolla(frm));

		frm.add_custom_button(__("Ro'yxatda yo'qlarini ko'rish"), () => {
			frappe.call({ method: "pokiza.pokiza_for_business.doctype.mahsulot_tartibi.mahsulot_tartibi.tartibsizlar" })
				.then((r) => {
					const royxat = r.message || [];
					frappe.msgprint({
						title: __("Ro'yxatda yo'q aktiv mahsulotlar ({0})", [royxat.length]),
						message: royxat.length
							? "<p>" + __("Bular doim oxirida, nom bo'yicha turadi:") + "</p><ul>" +
							  royxat.map((x) => `<li>${frappe.utils.escape_html(x.item_name || x.name)}</li>`).join("") +
							  "</ul>"
							: __("Hamma aktiv sotuv mahsuloti ro'yxatda bor."),
						indicator: royxat.length ? "orange" : "green",
					});
				});
		});

		if (!frm.doc.qatorlar || !frm.doc.qatorlar.length) {
			frm.dashboard.set_headline(
				__("Ro'yxat bo'sh — «Ro'yxatni joylash» tugmasi bilan Excel ro'yxatini kiriting.")
			);
		}
	},
});

function royxatniJoylash(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Excel ro'yxatini joylash"),
		size: "large",
		fields: [
			{
				fieldtype: "HTML",
				options:
					"<p>" +
					__("Excel'dan mahsulot nomlari ustunini ko'chirib shu yerga tashlang — <b>har satrda bitta nom</b>. «СОСИСКИ» kabi guruh sarlavhalari ham qolsa bo'ladi: ular mahsulot sifatida topilmasa, keyingi qatorlarga guruh belgisi bo'lib yoziladi.") +
					"</p><p><b>" +
					__("Diqqat: mavjud ro'yxat butunlay almashtiriladi.") +
					"</b></p>",
			},
			{
				fieldname: "matn",
				fieldtype: "Small Text",
				label: __("Ro'yxat"),
				reqd: 1,
			},
		],
		primary_action_label: __("Joylash"),
		primary_action(v) {
			d.hide();
			frappe.call({
				method: "pokiza.pokiza_for_business.doctype.mahsulot_tartibi.mahsulot_tartibi.royxatni_joylash",
				args: { matn: v.matn },
				freeze: true,
				freeze_message: __("Ro'yxat joylanmoqda..."),
				callback(r) {
					const n = r.message || {};
					let xabar = "<p>" + __("{0} mahsulot joylandi.", [n.qoshildi || 0]) + "</p>";
					if ((n.guruhlar || []).length) {
						xabar += "<p>" + __("Guruh sarlavhasi deb qabul qilindi:") + " " +
							n.guruhlar.map((x) => frappe.utils.escape_html(x)).join(", ") + "</p>";
					}
					if ((n.topilmadi || []).length) {
						xabar += "<p style='color:#c0392b'><b>" + __("Mahsulot topilmadi (ro'yxatga tushmadi) — nomini tekshiring:") + "</b><br>" +
							n.topilmadi.map((x) => frappe.utils.escape_html(x)).join("<br>") + "</p>";
					}
					if ((n.takror || []).length) {
						xabar += "<p>" + __("Takror kelgani (bir marta olindi):") + " " +
							n.takror.map((x) => frappe.utils.escape_html(x)).join(", ") + "</p>";
					}
					if ((n.tartibsiz || []).length) {
						xabar += "<p>" + __("Ro'yxatga tushmagan aktiv mahsulot: {0} ta — ular oxirida turadi.",
							[n.tartibsiz.length]) + "</p>";
					}
					frappe.msgprint({ title: __("Ro'yxat joylandi"), message: xabar, indicator: "green" });
					frm.reload_doc();
				},
			});
		},
	});
	d.show();
}

function kartochkalargaQolla(frm) {
	const chaqir = (sinov, keyin) =>
		frappe.call({
			method: "pokiza.pokiza_for_business.doctype.mahsulot_tartibi.mahsulot_tartibi.kartochkalarga_qolla",
			args: { sinov: sinov },
			freeze: true,
			freeze_message: sinov ? __("Tekshirilmoqda...") : __("Kartochkalar yangilanmoqda..."),
			callback: (r) => keyin(r.message || {}),
		});

	// Avval SINOV: nima o'zgarishini ko'rsatamiz, keyin tasdiqlatamiz
	chaqir(1, (n) => {
		if (!n.ozgardi) {
			frappe.msgprint({
				title: __("O'zgarish yo'q"),
				message: __("{0} kartochkaning hammasi allaqachon shu tartibda.", [n.kartochka]),
				indicator: "green",
			});
			return;
		}
		frappe.confirm(
			__("{0} kartochkadan {1} tasining qator tartibi o'zgaradi. Davom etamizmi?",
				[n.kartochka, n.ozgardi]),
			() =>
				chaqir(0, (res) => {
					let xabar = "<p>" + __("{0} kartochka yangilandi.", [res.ozgardi || 0]) + "</p>";
					if ((res.xatolar || []).length) {
						xabar += "<p>" + __("Quyidagilar saqlanmadi:") + "</p><ul>" +
							res.xatolar.map((x) => `<li>${frappe.utils.escape_html(x)}</li>`).join("") + "</ul>";
					}
					frappe.msgprint({
						title: __("Kartochkalarga qo'llandi"),
						message: xabar,
						indicator: (res.xatolar || []).length ? "orange" : "green",
					});
				})
		);
	});
}
