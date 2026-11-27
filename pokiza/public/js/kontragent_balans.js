// Kontragent kartochkasi tepasida joriy balans (qarzdor/haqdor) indikatori.
// Server tomoni: pokiza/api/kontragent.py (GL Entry bo'yicha debit − credit).

function pokiza_balans_korsat(frm, party_type) {
	if (frm.is_new()) return;
	frappe.call({
		method: "pokiza.api.kontragent.balans",
		args: { party_type: party_type, party: frm.doc.name },
	}).then((r) => {
		const bal = flt(r.message);
		const pul = format_currency(Math.abs(bal), "UZS", 0);
		let label, rang;
		if (party_type === "Customer") {
			if (bal > 0.5) {
				label = __("Bizga qarzdor: {0}", [pul]);
				rang = "red";
			} else if (bal < -0.5) {
				label = __("Haqdor (avans olingan): {0}", [pul]);
				rang = "blue";
			} else {
				label = __("Qarzi yo'q");
				rang = "green";
			}
		} else {
			// Supplier: credit > debit (bal < 0) -> biz qarzdormiz
			if (bal < -0.5) {
				label = __("Biz qarzdormiz: {0}", [pul]);
				rang = "red";
			} else if (bal > 0.5) {
				label = __("Haqdormiz (avans berilgan): {0}", [pul]);
				rang = "blue";
			} else {
				label = __("Qarz yo'q");
				rang = "green";
			}
		}
		frm.dashboard.add_indicator(label, rang);
	});
}

frappe.ui.form.on("Customer", {
	refresh(frm) {
		pokiza_balans_korsat(frm, "Customer");
	},
});

frappe.ui.form.on("Supplier", {
	refresh(frm) {
		pokiza_balans_korsat(frm, "Supplier");
	},
});
