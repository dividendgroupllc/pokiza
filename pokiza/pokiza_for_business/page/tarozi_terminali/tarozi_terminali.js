// TAROZI TERMINALI — tarozichi uchun MAKSIMAL SODDA ekran (MES operator
// printsipi, 2026-09-28): faqat bugungi tortiladigan mahsulotlar ro'yxati.
// Dashboard, pul, mijoz statistikasi YO'Q.
//
// 2026-09-30 (egasi talabi): mahsulot zames-zames keladi — tarozichi har
// kelgan bo'lakni [+] bilan ALOHIDA qo'shadi (masalan 200 kg rejadan 50+50+
// 50...), yig'indi darhol omborga (PE qoralama) va schyotga tarqaladi,
// qoldiq "yana N zames" ko'rinib turadi; yakunda [Tasdiqlash] bosadi.
// Orqada: sarf = REJA bo'yicha (o'zgarmaydi), kirim = FAKT bo'yicha.

frappe.pages["tarozi-terminali"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("⚖️ Tarozi terminali"),
		single_column: true,
	});

	const $wrap = $('<div class="tz-wrap"></div>').appendTo(page.main);
	$(`<style>
		.tz-wrap { max-width: 900px; margin: 0 auto; padding: 8px 4px 40px; }
		.tz-nav { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
		.tz-sana { font-size: 20px; font-weight: 700; flex: 1; text-align: center; }
		.tz-row { padding: 14px 16px; border: 1px solid var(--border-color);
			border-radius: 10px; margin-bottom: 10px; background: var(--card-bg); }
		.tz-row.tz-done { opacity: 0.65; background: var(--bg-light-gray, #f6f8f6); }
		.tz-top { display: flex; align-items: center; gap: 12px; }
		.tz-nom { flex: 1; }
		.tz-sku { font-size: 16px; font-weight: 600; }
		.tz-norma { font-size: 12px; color: var(--text-muted); }
		.tz-hujjat { font-size: 11px; color: var(--text-muted); }
		.tz-reja { font-size: 14px; white-space: nowrap; color: var(--text-muted); }
		.tz-ok { font-size: 16px; font-weight: 700; color: var(--green-600, #2e7d32); white-space: nowrap; }
		.tz-body { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-top: 10px; }
		.tz-chips { display: flex; flex-wrap: wrap; gap: 6px; flex: 1; min-width: 200px; }
		.tz-chip { display: inline-flex; align-items: center; gap: 6px; padding: 4px 8px;
			border: 1px solid var(--border-color); border-radius: 14px; font-size: 14px;
			font-weight: 600; background: var(--bg-light-gray, #f3f5f3); }
		.tz-chip .tz-x { cursor: pointer; color: var(--red-500, #c0392b); font-weight: 700;
			padding: 0 2px; }
		.tz-holat { font-size: 14px; font-weight: 600; white-space: nowrap; }
		.tz-holat.tz-teng { color: var(--green-600, #2e7d32); }
		.tz-holat.tz-kam { color: var(--orange-500, #e67e22); }
		.tz-holat.tz-ortiq { color: var(--red-500, #c0392b); }
		.tz-amal { display: flex; align-items: center; gap: 8px; }
		.tz-fakt { width: 100px; font-size: 18px; text-align: right; padding: 8px; }
		.tz-brak { width: 80px; font-size: 16px; text-align: right; padding: 8px;
			border-color: var(--red-300, #e8a09a); }
		.tz-brak-lbl { font-size: 13px; color: var(--red-500, #c0392b); font-weight: 600; }
		.tz-brak-badge { font-size: 12px; color: var(--red-500, #c0392b); font-weight: 600; white-space: nowrap; }
		.tz-qosh { font-size: 17px; font-weight: 700; padding: 7px 16px; }
		.tz-tasdiq { font-size: 15px; padding: 8px 16px; }
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

	const kg1 = (v) => format_number(v, null, 1);

	// qoldiq matni: "yana 50 kg (≈ 1 zames)" / ortiqcha bo'lsa qizil
	function holatHtml(reja, jami, zamesKg) {
		const qoldiq = flt(reja) - flt(jami);
		if (Math.abs(qoldiq) <= 0.05) {
			return `<span class="tz-holat tz-teng">✓ ${__("to'liq")} (${kg1(jami)} / ${kg1(reja)} kg)</span>`;
		}
		if (qoldiq > 0) {
			const zames = zamesKg > 0 ? ` (≈ ${format_number(qoldiq / zamesKg, null, 1)} ${__("zames")})` : "";
			return `<span class="tz-holat tz-kam">${kg1(jami)} / ${kg1(reja)} kg — ${__("qoldi")} <b>${kg1(qoldiq)} kg</b>${zames}</span>`;
		}
		return `<span class="tz-holat tz-ortiq">${kg1(jami)} / ${kg1(reja)} kg — ${__("ortiqcha")} <b>+${kg1(-qoldiq)} kg</b></span>`;
	}

	function render(d) {
		$nav.find(".tz-sana").text(frappe.datetime.str_to_user(d.sana));
		$list.empty();
		if (!(d.qatorlar || []).length) {
			$list.append(`<div class="tz-bosh">${__("Bu kunga tortiladigan mahsulot yo'q")}</div>`);
			return;
		}
		const zamesKg = flt(d.zames_kg);

		d.qatorlar.forEach((q) => {
			const done = q.holat !== "Kutilmoqda";
			const tortishlar = q.tortishlar || [];
			const jami = tortishlar.reduce((s, t) => s + flt(t.kg), 0);

			const chips = tortishlar
				.map(
					(t) =>
						`<span class="tz-chip" data-name="${t.name}">${kg1(t.kg)}
							${done ? "" : `<span class="tz-x" title="${__("olib tashlash")}">✕</span>`}</span>`
				)
				.join("");

			const $r = $(`
				<div class="tz-row ${done ? "tz-done" : ""}">
					<div class="tz-top">
						<div class="tz-nom">
							<div class="tz-sku">${frappe.utils.escape_html(q.sku)}</div>
							${q.norma ? `<div class="tz-norma">${frappe.utils.escape_html(q.norma)}</div>` : ""}
							<div class="tz-hujjat">${frappe.utils.escape_html(q.hujjat)}</div>
						</div>
						<div class="tz-reja">${__("reja")}: <b>${kg1(q.reja_kg)} kg</b></div>
						${
							done
								? `<div class="tz-ok">✓ ${kg1(q.fakt_kg)} kg${
										flt(q.brak_kg) > 0
											? ` <span class="tz-brak-badge">(${__("brak")} ${kg1(q.brak_kg)} kg)</span>`
											: ""
									}</div>`
								: ""
						}
					</div>
					${
						done
							? ""
							: `<div class="tz-body">
								<div class="tz-chips">${chips}</div>
								${jami > 0 || tortishlar.length ? holatHtml(q.reja_kg, jami, zamesKg) : ""}
								<div class="tz-amal">
									<input type="number" step="0.1" min="0" class="form-control tz-fakt" placeholder="kg">
									<button class="btn btn-primary tz-qosh">+ ${__("Qo'shish")}</button>
									<span class="tz-brak-lbl">${__("Brak")}:</span>
									<input type="number" step="0.1" min="0" class="form-control tz-brak" placeholder="0">
									<button class="btn btn-success tz-tasdiq" ${jami > 0 ? "" : "disabled"}>
										✓ ${__("Tasdiqlash")}${jami > 0 ? ` (${kg1(jami)} kg)` : ""}</button>
								</div>
							</div>`
					}
				</div>`);

			// [+] bo'lak qo'shish
			$r.find(".tz-qosh").on("click", () => {
				const kg = flt($r.find(".tz-fakt").val());
				if (kg <= 0) {
					frappe.show_alert({ message: __("Kg kiriting"), indicator: "orange" });
					return;
				}
				$r.find(".tz-qosh").prop("disabled", true);
				frappe
					.call({
						method: "pokiza.api.navbat.tortish_qosh",
						args: { row_name: q.row, kg: kg },
					})
					.then((res) => {
						const m = res.message || {};
						frappe.show_alert({
							message: __("+ {0} kg — jami {1} kg", [kg1(kg), kg1(m.jami)]),
							indicator: "green",
						});
						yukla();
					})
					.catch(() => $r.find(".tz-qosh").prop("disabled", false));
			});
			// Enter = [+]
			$r.find(".tz-fakt").on("keydown", (e) => {
				if (e.key === "Enter") $r.find(".tz-qosh").trigger("click");
			});

			// bo'lakni olib tashlash
			$r.find(".tz-x").on("click", function () {
				const name = $(this).closest(".tz-chip").data("name");
				frappe
					.call({ method: "pokiza.api.navbat.tortish_ochir", args: { tortish_name: name } })
					.then(() => yukla());
			});

			// yakuniy tasdiqlash (brak bilan)
			$r.find(".tz-tasdiq").on("click", () => {
				const brak = flt($r.find(".tz-brak").val());
				if (brak < 0 || brak >= jami) {
					frappe.show_alert({
						message: __("Brak 0 dan tortilgan jamigacha bo'lishi kerak"),
						indicator: "orange",
					});
					return;
				}
				const sotuv = jami - brak;
				const qoldiq = flt(q.reja_kg) - jami;
				const tasdiqla = () => {
					$r.find(".tz-tasdiq").prop("disabled", true);
					frappe
						.call({
							method: "pokiza.api.navbat.chiqarildi",
							args: { row_name: q.row, fakt_kg: jami, brak_kg: brak },
						})
						.then(() => {
							frappe.show_alert({
								message: brak > 0
									? __("✓ Tasdiqlandi: {0} — {1} kg (brak {2} kg)", [q.sku, kg1(sotuv), kg1(brak)])
									: __("✓ Tasdiqlandi: {0} — {1} kg", [q.sku, kg1(jami)]),
								indicator: "green",
							});
							yukla();
						})
						.catch(() => $r.find(".tz-tasdiq").prop("disabled", false));
				};
				const savollar = [];
				if (brak > 0) {
					savollar.push(
						__("Brak: <b>{0} kg</b> — omborga/sotuvga {1} kg kiradi, brak farshi ishlab chiqarishga qaytadi.", [
							kg1(brak), kg1(sotuv),
						])
					);
				}
				if (qoldiq > 0.05) {
					const zames = zamesKg > 0 ? ` (≈ ${format_number(qoldiq / zamesKg, null, 1)} ${__("zames")})` : "";
					savollar.push(
						__("Reja {0} kg, tortildi {1} kg — <b>qoldi {2} kg{3}</b>.", [
							kg1(q.reja_kg), kg1(jami), kg1(qoldiq), zames,
						])
					);
				}
				if (savollar.length) {
					frappe.confirm(savollar.join("<br><br>") + "<br><br>" + __("Tasdiqlaysizmi?"), tasdiqla);
				} else {
					tasdiqla();
				}
			});

			$list.append($r);
		});
	}

	frappe.realtime.on("navbat_update", () => yukla());
	yukla();
};
