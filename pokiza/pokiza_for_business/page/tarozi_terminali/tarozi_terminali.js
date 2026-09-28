// TAROZI TERMINALI — tarozichi uchun MAKSIMAL SODDA ekran (MES operator
// printsipi, 2026-09-28): faqat bugungi tortiladigan mahsulotlar ro'yxati
// va fakt kg kiritish. Dashboard, pul, mijoz statistikasi YO'Q.
// Orqada: sarf = REJA bo'yicha (o'zgarmaydi), kirim = FAKT bo'yicha —
// PE qoralamasini ishlab chiqarish rahbari navbat sahifasidan tasdiqlaydi.

frappe.pages["tarozi-terminali"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("⚖️ Tarozi terminali"),
		single_column: true,
	});

	const $wrap = $('<div class="tz-wrap"></div>').appendTo(page.main);
	$(`<style>
		.tz-wrap { max-width: 860px; margin: 0 auto; padding: 8px 4px 40px; }
		.tz-nav { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
		.tz-sana { font-size: 20px; font-weight: 700; flex: 1; text-align: center; }
		.tz-row { display: flex; align-items: center; gap: 12px; padding: 14px 16px;
			border: 1px solid var(--border-color); border-radius: 10px; margin-bottom: 10px;
			background: var(--card-bg); }
		.tz-row.tz-done { opacity: 0.65; background: var(--bg-light-gray, #f6f8f6); }
		.tz-nom { flex: 1; }
		.tz-sku { font-size: 16px; font-weight: 600; }
		.tz-norma { font-size: 12px; color: var(--text-muted); }
		.tz-hujjat { font-size: 11px; color: var(--text-muted); }
		.tz-reja { font-size: 14px; white-space: nowrap; color: var(--text-muted); }
		.tz-fakt { width: 110px; font-size: 18px; text-align: right; padding: 8px; }
		.tz-saqla { font-size: 15px; padding: 8px 18px; }
		.tz-ok { font-size: 16px; font-weight: 700; color: var(--green-600, #2e7d32); white-space: nowrap; }
		.tz-bosh { text-align: center; color: var(--text-muted); padding: 40px 0; font-size: 16px; }
	</style>`).appendTo($wrap);

	const state = { sana: frappe.datetime.get_today() };

	const $nav = $(`
		<div class="tz-nav">
			<button class="btn btn-default tz-prev">‹</button>
			<div class="tz-sana"></div>
			<button class="btn btn-default tz-next">›</button>
			<button class="btn btn-default tz-bugun">${__("Bugun")}</button>
		</div>`).appendTo($wrap);
	const $list = $('<div></div>').appendTo($wrap);

	$nav.find(".tz-prev").on("click", () => sur(-1));
	$nav.find(".tz-next").on("click", () => sur(1));
	$nav.find(".tz-bugun").on("click", () => {
		state.sana = frappe.datetime.get_today();
		yukla();
	});
	function sur(k) {
		state.sana = frappe.datetime.add_days(state.sana, k);
		yukla();
	}

	function yukla() {
		frappe
			.call({ method: "pokiza.api.navbat.tarozi_royxat", args: { sana: state.sana } })
			.then((r) => render(r.message));
	}

	function render(d) {
		$nav.find(".tz-sana").text(frappe.datetime.str_to_user(d.sana));
		$list.empty();
		if (!(d.qatorlar || []).length) {
			$list.append(`<div class="tz-bosh">${__("Bu kunga tortiladigan mahsulot yo'q")}</div>`);
			return;
		}
		d.qatorlar.forEach((q) => {
			const done = q.holat !== "Kutilmoqda";
			const $r = $(`
				<div class="tz-row ${done ? "tz-done" : ""}">
					<div class="tz-nom">
						<div class="tz-sku">${frappe.utils.escape_html(q.sku)}</div>
						${q.norma ? `<div class="tz-norma">${frappe.utils.escape_html(q.norma)}</div>` : ""}
						<div class="tz-hujjat">${frappe.utils.escape_html(q.hujjat)}</div>
					</div>
					<div class="tz-reja">${__("reja")}: <b>${format_number(q.reja_kg, null, 1)} kg</b></div>
					${
						done
							? `<div class="tz-ok">✓ ${format_number(q.fakt_kg, null, 1)} kg</div>`
							: `<input type="number" step="0.1" min="0" class="form-control tz-fakt"
									placeholder="fakt" value="${q.reja_kg || ""}">
							   <button class="btn btn-success tz-saqla">${__("Saqlash")}</button>`
					}
				</div>`);
			$r.find(".tz-saqla").on("click", () => {
				const fakt = flt($r.find(".tz-fakt").val());
				if (fakt <= 0) {
					frappe.show_alert({ message: __("Fakt kg kiriting"), indicator: "orange" });
					return;
				}
				$r.find(".tz-saqla").prop("disabled", true);
				frappe
					.call({
						method: "pokiza.api.navbat.chiqarildi",
						args: { row_name: q.row, fakt_kg: fakt },
					})
					.then(() => {
						frappe.show_alert({
							message: __("✓ Saqlandi: {0} — {1} kg", [q.sku, fakt]),
							indicator: "green",
						});
						yukla();
					})
					.catch(() => $r.find(".tz-saqla").prop("disabled", false));
			});
			$list.append($r);
		});
	}

	frappe.realtime.on("navbat_update", () => yukla());
	yukla();
};
