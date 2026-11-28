// Kontragent kartochkasida joriy balans: tepada indikator-pill + Details
// ichidagi «Balans» HTML maydoni (custom_balans_korinish).
// Server tomoni: pokiza/api/kontragent.py (GL Entry bo'yicha debit − credit).
// Ishora ikkala turda ham bir xil o'qiladi:
//   balans > 0 -> kontragent BIZGA QARZDOR; balans < 0 -> HAQDOR (biz qarzdormiz).

function pokiza_balans_korsat(frm, party_type) {
	if (frm.is_new()) return;
	frappe.call({
		method: "pokiza.api.kontragent.balans",
		args: { party_type: party_type, party: frm.doc.name },
	}).then((r) => {
		const bal = flt(r.message);
		const pul = format_currency(Math.abs(bal), "UZS", 0);
		let label, css;
		if (bal > 0.5) {
			label = __("Bizga qarzdor: {0}", [pul]);
			css = "var(--red-600)";
		} else if (bal < -0.5) {
			label = __("Haqdor (biz qarzdormiz): {0}", [pul]);
			css = "var(--blue-600)";
		} else {
			label = __("Qarzi yo'q");
			css = "var(--text-color)";
		}

		// Details ichidagi «Balans» maydoni (dashborddagi pill ataylab YO'Q —
		// u yerda ERPNext'ning o'z Total Unpaid'i bor, takror bo'lib qolardi)
		const field = frm.get_field("custom_balans_korinish");
		if (field && field.$wrapper) {
			field.$wrapper.html(`
				<div class="frappe-control">
					<div class="control-label">${__("Balans")}</div>
					<div class="like-disabled-input" style="color:${css}">${label}</div>
				</div>`);
		}
	});
}

// «Акт сверки» tugmasi — hisobotga shu kontragent filtrlari bilan o'tadi
// (sanalar hisobotning o'z sukutida qoladi: oxirgi 1 oy).
function pokiza_akt_sverka_tugma(frm, party_type) {
	if (frm.is_new()) return;
	frm.add_custom_button(__("Акт сверки"), () => {
		frappe.set_route("query-report", "Akt Sverka", {
			party_type: party_type,
			party: frm.doc.name,
		});
	});
}

frappe.ui.form.on("Customer", {
	refresh(frm) {
		pokiza_balans_korsat(frm, "Customer");
		pokiza_akt_sverka_tugma(frm, "Customer");
	},
});

frappe.ui.form.on("Supplier", {
	refresh(frm) {
		pokiza_balans_korsat(frm, "Supplier");
		pokiza_akt_sverka_tugma(frm, "Supplier");
	},
});
