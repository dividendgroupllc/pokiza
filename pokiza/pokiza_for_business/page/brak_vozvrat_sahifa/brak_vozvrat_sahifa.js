// BRAK VOZVRAT SAHIFASI — kun oxiri brak jadvali, ALOHIDA sahifa
// (egasi talabi 2026-10-01: modal emas, ikkinchi list bo'lib ochilsin).
// Dunyo standarti (SAP scrap posting / Odoo scrap / MES waste log):
// jadval — har mahsulot alohida qator («bunisidan 5, bunisidan 3»),
// bitta Saqlash → orqada har qator uchun Stock Entry avto submit.
// 2026-10-06 (egasi talabi): skladga HECH NARSA qaytmaydi — SKU ombordan
// Material Issue bilan chiqadi, to'liq tannarxi (farsh + upakovka) «Брак»
// rasxod hisobiga tushadi.
// Server: pokiza.api.navbat.brak_vozvrat_toplu / brak_royxat.

frappe.pages["brak-vozvrat-sahifa"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("🗑 Brak vozvrat"),
		single_column: true,
	});

	const $wrap = $('<div class="bv-wrap"></div>').appendTo(page.main);
	$(`<style>
		.bv-wrap { max-width: 860px; margin: 0 auto; padding: 8px 4px 40px; }
		.bv-eslatma { color: var(--text-muted); margin-bottom: 10px; }
		.bv-royxat { margin-top: 18px; }
		.bv-royxat table td { padding: 4px 8px; }
	</style>`).appendTo($wrap);

	const kg1 = (v) => format_number(v, null, 1);

	$wrap.append(`<div class="bv-eslatma">
		${__("Kun davomida yig'ilgan brakni mahsulot kesimida kiriting. Saqlashda har qator uchun ombor harakati avtomatik o'tadi: mahsulot ombordan chiqadi va to'liq tannarxi «Брак» rasxod hisobiga tushadi — skladga hech narsa qaytmaydi.")}
	</div>`);

	// jadval (FieldGroup ichida Table control)
	const form = new frappe.ui.FieldGroup({
		fields: [
			{
				fieldname: "qatorlar",
				fieldtype: "Table",
				label: __("Brak ro'yxati"),
				in_place_edit: true,
				data: [],
				get_data: () => [],
				fields: [
					{
						fieldname: "item_code",
						fieldtype: "Link",
						options: "Item",
						label: __("Mahsulot"),
						in_list_view: 1,
						reqd: 1,
						columns: 7,
						get_query: () => ({ filters: { item_group: "Сотув махсулотлари" } }),
					},
					{
						fieldname: "kg",
						fieldtype: "Float",
						label: __("Brak kg"),
						in_list_view: 1,
						reqd: 1,
						columns: 3,
					},
				],
			},
		],
		body: $wrap.get(0),
	});
	form.make();

	const $royxat = $('<div class="bv-royxat"></div>').appendTo($wrap);

	function royxatYukla() {
		frappe
			.call({ method: "pokiza.api.navbat.brak_royxat", args: {} })
			.then((r) => {
				const m = r.message || {};
				const rows = (m.qatorlar || [])
					.map(
						(q) =>
							`<tr><td>${frappe.utils.escape_html(q.item_code)}</td>
							 <td class="text-muted">${frappe.utils.escape_html(q.norma || "-")}</td>
							 <td style="text-align:right"><b>${kg1(q.kg)} kg</b></td></tr>`
					)
					.join("");
				$royxat.html(
					rows
						? `<b>${__("Bugun vozvrat qilinganlar")} (${__("jami")} ${kg1(m.jami)} kg):</b>
							<table class="table table-sm" style="margin-top:4px">${rows}</table>`
						: `<div class="text-muted">${__("Bugun hali vozvrat yo'q")}</div>`
				);
			});
	}

	function saqla() {
		const v = form.get_values(true) || {};
		const rows = (v.qatorlar || []).filter((r) => r.item_code && flt(r.kg) > 0);
		if (!rows.length) {
			frappe.show_alert({ message: __("Jadvalga kamida bitta qator kiriting"), indicator: "orange" });
			return;
		}
		const jami = rows.reduce((t, r) => t + flt(r.kg), 0);
		frappe.confirm(
			__("{0} ta mahsulot, jami <b>{1} kg</b> brak vozvrat qilinadi.<br>Davom etasizmi?", [
				rows.length, kg1(jami),
			]),
			() => {
				frappe
					.call({
						method: "pokiza.api.navbat.brak_vozvrat_toplu",
						args: { qatorlar: rows.map((r) => ({ item_code: r.item_code, kg: flt(r.kg) })) },
					})
					.then((res) => {
						const m = res.message || {};
						const satrlar = (m.natijalar || [])
							.map((n) =>
								n.ok
									? `<li>✅ <b>${frappe.utils.escape_html(n.item_code)}</b> — ${kg1(n.kg)} kg (${__("farsh")}: ${frappe.utils.escape_html(n.norma || "-")})</li>`
									: `<li>❌ <b>${frappe.utils.escape_html(n.item_code)}</b> — ${kg1(n.kg)} kg: ${frappe.utils.escape_html(n.xato || "")}</li>`
							)
							.join("");
						frappe.msgprint({
							title: __("Brak vozvrat natijasi"),
							message: `<ul style="padding-left:18px">${satrlar}</ul>`,
							indicator: m.xato ? "orange" : "green",
						});
						// o'tganlari jadvaldan tozalanadi, xatolari tuzatish uchun qoladi
						const xatolilar = (m.natijalar || []).filter((n) => !n.ok);
						const grid_field = form.get_field("qatorlar");
						grid_field.df.data = xatolilar.map((n) => ({ item_code: n.item_code, kg: n.kg }));
						grid_field.grid.refresh();
						royxatYukla();
					});
			}
		);
	}

	page.set_primary_action(__("💾 Saqlash (vozvrat)"), saqla);
	page.set_secondary_action(__("⚖️ Terminalga qaytish"), () =>
		frappe.set_route("tarozi-terminali")
	);

	royxatYukla();
};
