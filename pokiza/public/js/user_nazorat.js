// Nazorat boti: Telegram akkauntni ERP foydalanuvchiga ulash (bir martalik kod, 10 daqiqa).
// - xodim o'z profilida o'zi uchun kod oladi;
// - administrator / rahbar istalgan xodim sahifasida o'sha xodim uchun kod yaratadi va bo'limini belgilaydi.
frappe.ui.form.on("User", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.user_type !== "System User" || !frm.doc.enabled) return;
		frappe
			.call({ method: "pokiza.nazorat.tg.linking.tg_holat", args: { user: frm.doc.name } })
			.then(({ message: h }) => h && pokiza_tg_render(frm, h));
	},
});

function pokiza_tg_render(frm, h) {
	const a = h.azo;
	const ulangan = a && a.telegram_id;
	if (ulangan) {
		const kim = [a.ism, a.username ? "@" + a.username : ""].filter(Boolean).join(" ");
		const info = [kim, a.bolim ? __("bo'lim: {0}", [a.bolim]) : __("bo'lim belgilanmagan"), a.faol ? "" : __("o'chirilgan")]
			.filter(Boolean)
			.join(" · ");
		frm.dashboard.set_headline_alert(
			`<span class="indicator ${a.faol ? "green" : "gray"}">${__("Telegram ulangan")}: ${frappe.utils.escape_html(info)}</span>`
		);
	} else if (!h.oziniki) {
		frm.dashboard.set_headline_alert(`<span class="indicator orange">${__("Telegram ulanmagan")}</span>`);
	}
	const label = ulangan ? __("Telegram'ni qayta ulash") : __("Telegram'ga ulash");
	frm.add_custom_button(label, () => {
		if (!h.bot_faol) {
			frappe.msgprint(__("Nazorat boti hali yoqilmagan. Avval Nazorat Bot Sozlamalari'da botni yoqing."));
			return;
		}
		if (h.oziniki && !h.admin) return pokiza_tg_kod(frm, null);
		const d = new frappe.ui.Dialog({
			title: __("Telegram'ga ulash: {0}", [frm.doc.full_name || frm.doc.name]),
			fields: [
				{
					fieldname: "bolim",
					fieldtype: "Select",
					label: __("Bo'lim"),
					options: [""].concat(h.bolimlar),
					default: (a && a.bolim) || h.taxminiy_bolim || "",
					description: __("Xodim botda va guruhlarda faqat shu bo'lim ko'rsatkichlarini ko'radi. Rahbar — hammasini."),
				},
			],
			primary_action_label: __("Kod yaratish"),
			primary_action: (v) => {
				d.hide();
				pokiza_tg_kod(frm, v.bolim || null);
			},
		});
		d.show();
	});
}

function pokiza_tg_kod(frm, bolim) {
	const boshqa = frm.doc.name !== frappe.session.user;
	frappe
		.call({ method: "pokiza.nazorat.tg.linking.kod_yarat", args: { user: frm.doc.name, bolim } })
		.then(({ message: r }) => {
			if (!r) return;
			const kod = frappe.utils.escape_html(r.kod);
			const kimga = boshqa
				? `<p>${__("Havolani <b>{0}</b>ga yuboring — u o'z telefonida ochib, botda Start bosadi.", [frappe.utils.escape_html(frm.doc.full_name || frm.doc.name)])}</p>`
				: "";
			const link = r.link
				? `<p><a class="btn btn-primary btn-sm" href="${r.link}" target="_blank" rel="noopener">${__("Telegram'da ochish")}</a>
				   <button class="btn btn-default btn-sm pokiza-tg-copy">${__("Havolani nusxalash")}</button></p>
				   <p class="text-muted small">${__("Yoki botga yozing")}: <code>/start ${kod}</code></p>`
				: `<p>${__("Botga yozing")}: <code>/start ${kod}</code></p>`;
			const dlg = frappe.msgprint({
				title: __("Telegram'ga ulash"),
				message: `${kimga}${link}<p class="text-muted small">${__("Kod {0} daqiqa amal qiladi va bir marta ishlaydi.", [r.daqiqa])}${
					boshqa ? "" : " " + __("Uni hech kimga bermang.")
				}</p>`,
			});
			dlg.$wrapper.find(".pokiza-tg-copy").on("click", () => frappe.utils.copy_to_clipboard(r.link));
		});
}
