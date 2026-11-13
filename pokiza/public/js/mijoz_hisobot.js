// Oylik mijoz hisoboti (PDF): Customer va Mijoz Kartochkasi formalarida tugma.
// PDF serverda yasaladi: pokiza.api.mijoz_hisobot.yuklab_ol
window.pokiza_mijoz_hisobot = function (mijoz) {
	const OY = ["Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"];
	const bugun = new Date();
	const variantlar = [];
	for (let i = 0; i < 13; i++) {
		const d = new Date(bugun.getFullYear(), bugun.getMonth() - i, 1);
		const v = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
		variantlar.push({ value: v, label: `${OY[d.getMonth()]} ${d.getFullYear()}` + (i === 0 ? ` (${__("davom etmoqda")})` : "") });
	}
	const d = new frappe.ui.Dialog({
		title: __("Oylik savdo tahlili (PDF)"),
		fields: [
			{
				fieldname: "oy", fieldtype: "Select", label: __("Oy"), reqd: 1,
				options: variantlar, default: variantlar[1].value,
				description: __("Tanlangan oy o'tgan oyga nisbatan solishtiriladi. Keyingi oy maqsadi Mijoz Kartochkasi → Oylik maqsadlar jadvalidan olinadi."),
			},
		],
		primary_action_label: __("PDF yuklab olish"),
		primary_action(v) {
			d.hide();
			const url = `/api/method/pokiza.api.mijoz_hisobot.yuklab_ol?mijoz=${encodeURIComponent(mijoz)}&oy=${v.oy}`;
			window.open(url, "_blank");
		},
	});
	d.show();
};

frappe.ui.form.on("Customer", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Oylik savdo tahlili (PDF)"), () => pokiza_mijoz_hisobot(frm.doc.name), __("Hisobotlar"));
	},
});
