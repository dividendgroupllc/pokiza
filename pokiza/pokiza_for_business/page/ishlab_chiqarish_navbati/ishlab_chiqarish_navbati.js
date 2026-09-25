// ============================================================================
//  ISHLAB CHIQARISH NAVBATI — zavod ish markazi (artifact spec asosida)
//  4 bo'lim (tepada o'ngda): 🛒 Zakaz urish · 🏭 Ishlab chiqarish ·
//  📦 Ombor · ⚙️ Sozlamalar
//  - Zakaz urish: sales orderdan kelgan zakazlar ro'yxati — faqat jadval
//    (kimdan, qancha mahsulot, qachonga). Omborga bog'lanmagan.
//  - Ombor: tayyor mahsulot qoldig'i (qoldiq / band / bo'sh).
//  - Sozlamalar: kunlik sig'im, kesim vaqti, zames kg, yakshanba, gorizont.
// ============================================================================

frappe.pages["ishlab-chiqarish-navbati"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Ishlab chiqarish navbati"),
		single_column: true,
	});

	if (frappe.user.has_role("System Manager")) {
		page.add_menu_item(__("Sozlamalar (forma)"), () =>
			frappe.set_route("Form", "Ishlab Chiqarish Sozlamalari")
		);
		page.add_menu_item(__("O'zgarishlar jurnali"), () =>
			frappe.set_route("List", "Reja Ozgarish Jurnali")
		);
	}

	// sahifa to'liq ekran bo'ylab yoyiladi (standart tor konteyner o'rniga)
	$(wrapper).addClass("nv-full");

	const state = {
		sana: frappe.datetime.get_today(),
		// gorizont lentasi boshi — tanlangan kun lentadan chiqmasligi uchun suriladi
		gBoshi: frappe.datetime.get_today(),
		gLen: 7,
	};
	const $wrap = $('<div class="navbat-wrap"></div>').appendTo(page.main);
	injectCss();

	const ICH_ROL =
		frappe.user.has_role("Manufacturing Manager") ||
		frappe.user.has_role("Manufacturing User") ||
		frappe.user.has_role("System Manager") ||
		frappe.user.has_role("tarozi");
	const SOTUV_ROL =
		frappe.user.has_role("Sales Manager") ||
		frappe.user.has_role("Sales User") ||
		frappe.user.has_role("System Manager");

	const PROGRESS = {
		kutilmoqda: { label: __("Kutilmoqda"), rang: "kul" },
		jarayonda: { label: __("Jarayonda"), rang: "sariq" },
		tayyor: { label: __("Tayyor"), rang: "yashil" },
		jonatildi: { label: __("Jo'natildi"), rang: "kok" },
	};

	// ------------------------------------------------------------------ tablar
	const $tabbar = $(`
		<div class="nv-tabs">
			${SOTUV_ROL ? `<button class="nv-tab-btn" data-tab="zakaz">🛒 ${__("Zakaz urish")}</button>` : ""}
			<button class="nv-tab-btn nv-tab-active" data-tab="ishlab">🏭 ${__("Ishlab chiqarish")}</button>
			<button class="nv-tab-btn" data-tab="ombor">📦 ${__("Ombor")}</button>
			<button class="nv-tab-btn" data-tab="sozlama">⚙️ ${__("Sozlamalar")}</button>
		</div>`).appendTo($wrap);

	const $tabs = {
		zakaz: $('<div class="nv-tab-body" style="display:none"></div>').appendTo($wrap),
		ishlab: $('<div class="nv-tab-body"></div>').appendTo($wrap),
		ombor: $('<div class="nv-tab-body" style="display:none"></div>').appendTo($wrap),
		sozlama: $('<div class="nv-tab-body" style="display:none"></div>').appendTo($wrap),
	};
	const $body = $tabs.ishlab; // mavjud render shu joyga chizadi

	function tabOch(t) {
		$tabbar.find(".nv-tab-btn").removeClass("nv-tab-active");
		$tabbar.find(`[data-tab="${t}"]`).addClass("nv-tab-active");
		Object.keys($tabs).forEach((k) => $tabs[k].toggle(k === t));
		if (t === "zakaz") zakazYukla();
		if (t === "ombor") omborYukla();
		if (t === "sozlama") sozlamaYukla();
	}
	$tabbar.on("click", ".nv-tab-btn", (e) => tabOch($(e.currentTarget).data("tab")));

	function yukla() {
		frappe
			.call({
				method: "pokiza.api.navbat.get_navbat",
				args: { sana: state.sana, gorizont_boshi: state.gBoshi },
			})
			.then((r) => render(r.message));
	}

	// kun tanlash: lenta tanlangan kunni doim ko'rsatadi —
	// orqaga o'tsak lenta boshi tanlangan kun bo'ladi (18 -> 18..24),
	// oldinga chiqib ketsak tanlangan kun lenta oxirida turadi (28 -> 22..28)
	function tanla(sana) {
		state.sana = sana;
		const oxiri = frappe.datetime.add_days(state.gBoshi, state.gLen - 1);
		if (sana < state.gBoshi) {
			state.gBoshi = sana;
		} else if (sana > oxiri) {
			state.gBoshi = frappe.datetime.add_days(sana, -(state.gLen - 1));
		}
		yukla();
	}

	// realtime: boshqa joyda zakaz tasdiqlansa/surilsa ekran o'zi yangilanadi
	frappe.realtime.on("navbat_update", () => yukla());

	// ------------------------------------------------------------------ render
	function render(d) {
		const bugun = frappe.datetime.get_today();
		state.gLen = (d.gorizont || []).length || state.gLen;
		const foiz = d.quvvat > 0 ? Math.round((d.jami_kg / d.quvvat) * 100) : 0;
		const rang = foiz > 100 ? "qizil" : foiz > 85 ? "sariq" : "yashil";

		$body.empty();

		// --- sana navigatsiyasi
		const $nav = $(`
			<div class="nv-card nv-nav">
				<button class="btn btn-default btn-sm nv-prev">‹</button>
				<div class="nv-nav-mid">
					<div class="nv-sana">${sanaLabel(d.sana)}</div>
					<div class="nv-sub">${
						d.sana === bugun
							? __("Bugungi ishlab chiqarish")
							: __("Ishlab chiqarish kuni")
					} · ${__("yetkazish")}: ${sanaLabel(frappe.datetime.add_days(d.sana, 1))}</div>
				</div>
				<button class="btn btn-default btn-sm nv-next">›</button>
				<button class="btn btn-default btn-sm nv-bugun">${__("Bugun")}</button>
				<button class="btn btn-default btn-sm nv-qogoz">🖨 ${__("Qog'ozlar")}</button>
			</div>`).appendTo($body);
		$nav.find(".nv-prev").on("click", () => surSana(-1, d.yakshanba_dam));
		$nav.find(".nv-next").on("click", () => surSana(1, d.yakshanba_dam));
		$nav.find(".nv-bugun").on("click", () => {
			state.gBoshi = bugun;
			tanla(bugun);
		});
		$nav.find(".nv-qogoz").on("click", () => qogozChiqar(d.sana));

		// --- umumiy uchyot plitkalari (butun tizim + shu kun)
		const u = d.umumiy || {};
		const k = d.kun_uchyot || {};
		const $tiles = $(`
			<div class="nv-tiles">
				<div class="nv-tile">
					<div class="nv-tile-num">${u.aktiv_soni || 0}</div>
					<div class="nv-tile-label">${__("Aktiv zakaz (jami)")}</div>
					<div class="nv-tile-sub">${fmt(u.aktiv_kg || 0)} kg</div>
				</div>
				<div class="nv-tile ${u.kechikkan_soni ? "nv-tile-qizil nv-click" : ""}" data-act="kechikkan">
					<div class="nv-tile-num">${u.kechikkan_soni || 0}</div>
					<div class="nv-tile-label">${__("Kechikkan")}</div>
					<div class="nv-tile-sub">${u.kechikkan_soni ? __("bosib ko'ring") : "—"}</div>
				</div>
				<div class="nv-tile">
					<div class="nv-tile-num">${(k.kutilmoqda || 0) + (k.jarayonda || 0)}</div>
					<div class="nv-tile-label">${__("Bu kunda navbatda")}</div>
					<div class="nv-tile-sub">${k.jarayonda || 0} ${__("jarayonda")}</div>
				</div>
				<div class="nv-tile">
					<div class="nv-tile-num">${k.tayyor || 0}</div>
					<div class="nv-tile-label">${__("Tayyor (jo'natilmagan)")}</div>
					<div class="nv-tile-sub">${k.jonatildi || 0} ${__("jo'natildi")}</div>
				</div>
				<div class="nv-tile ${(d.pe_qoralama || {}).soni ? "nv-tile-sariq nv-click" : ""}" data-act="pe">
					<div class="nv-tile-num">${(d.pe_qoralama || {}).soni || 0}</div>
					<div class="nv-tile-label">${__("Ombor kirimi tasdiqlanmagan")}</div>
					<div class="nv-tile-sub">${(d.pe_qoralama || {}).soni ? fmt(d.pe_qoralama.kg) + " kg · " + __("bosib ko'ring") : "—"}</div>
				</div>
				<div class="nv-tile ${(d.si_qoralama || {}).soni ? "nv-tile-sariq nv-click" : ""}" data-act="si">
					<div class="nv-tile-num">${(d.si_qoralama || {}).soni || 0}</div>
					<div class="nv-tile-label">${__("Schyot tasdiqlanmagan")}</div>
					<div class="nv-tile-sub">${(d.si_qoralama || {}).soni ? fmt(d.si_qoralama.summa) + " · " + __("bosib ko'ring") : "—"}</div>
				</div>
			</div>`).appendTo($body);
		$tiles.find('[data-act="kechikkan"]').on("click", () => kechikkanDialog(u.kechikkan || []));
		$tiles.find('[data-act="pe"]').on("click", () => peQoralamaDialog(d.pe_qoralama || {}));
		$tiles.find('[data-act="si"]').on("click", () => siQoralamaDialog(d.si_qoralama || {}));

		// --- sig'im chizig'i
		$(`
			<div class="nv-card">
				<div class="nv-row-между">
					<span class="nv-label">${__("Kunlik sig'im")}</span>
					<span class="nv-kg nv-${rang}">${fmt(d.jami_kg)} / ${fmt(d.quvvat)} kg (${foiz}%)</span>
				</div>
				<div class="nv-bar"><div class="nv-bar-fill nv-bg-${rang}" style="width:${Math.min(foiz, 100)}%"></div></div>
				${d.qoralama ? `<div class="nv-mini text-muted">${__("Qoralama (joy olmagan) zakazlar")}: ${d.qoralama}</div>` : ""}
			</div>`).appendTo($body);

		// --- ortiqcha + tavsiyalar
		if (d.ortiqcha > 0) {
			const $of = $(`
				<div class="nv-card nv-overflow">
					<div class="nv-of-title">⚠ ${__("Sig'imdan")} <b>${fmt(d.ortiqcha)} kg</b> ${__("ortiqcha zakaz bor")}</div>
					<div class="nv-of-sub">${__("Tavsiya: quyidagi zakaz(lar)ni keyingi kunga surish")}:</div>
					<div class="nv-of-list"></div>
				</div>`).appendTo($body);
			const $list = $of.find(".nv-of-list");
			(d.tavsiyalar || []).forEach((t) => {
				$(`<button class="btn btn-xs btn-default nv-of-btn">
					${t.so} · ${fmt(t.kg)} kg → ${__("surish")}
				</button>`)
					.on("click", () => surishDialog(t.so, d.sana))
					.appendTo($list);
			});
		}

		// --- gorizont (kelgusi kunlar chizig'i)
		const $gz = $('<div class="nv-gorizont"></div>').appendTo($body);
		(d.gorizont || []).forEach((g) => {
			const gf = d.quvvat > 0 ? Math.round((g.band / d.quvvat) * 100) : 0;
			const gr = g.yakshanba ? "dam" : gf > 100 ? "qizil" : gf > 85 ? "sariq" : "yashil";
			const $k = $(`
				<div class="nv-gz-kun ${g.sana === d.sana ? "nv-gz-active" : ""} ${g.yakshanba ? "nv-gz-dam" : ""}">
					<div class="nv-gz-sana ${g.sana === bugun ? "nv-gz-bugun" : ""}">${qisqaSana(g.sana)}${g.sana === bugun ? " •" : ""}</div>
					<div class="nv-gz-bar"><div class="nv-bg-${gr}" style="height:${Math.min(gf, 100)}%"></div></div>
					<div class="nv-gz-kg">${g.yakshanba ? __("dam") : fmt(g.band)}</div>
				</div>`);
			$k.on("click", () => tanla(g.sana));
			$gz.append($k);
		});

		// --- asosiy maydon: chapda mijoz kartochkalari, keng ekranda o'ngda kesim
		const $main = $('<div class="nv-main"></div>').appendTo($body);
		const $left = $('<div class="nv-main-left"></div>').appendTo($main);
		const $right = $('<div class="nv-main-right"></div>').appendTo($main);
		const $cards = $('<div class="nv-cards"></div>').appendTo($left);
		if (!d.guruhlar.length) {
			$cards.append(`<div class="nv-card nv-empty">${__("Bu kunga zakaz yo'q")}</div>`);
		}
		d.guruhlar.forEach((g, i) => {
			const $c = $(`
				<div class="nv-card nv-mijoz">
					<div class="nv-mijoz-head">
						<div class="nv-mijoz-nom"><span class="nv-idx">${i + 1}</span> ${frappe.utils.escape_html(g.mijoz)}</div>
						<div class="nv-mijoz-right">
							<span class="nv-slot">🚚 ${g.slot}${g.slot_izoh ? " · " + frappe.utils.escape_html(g.slot_izoh) : ""}</span>
							<span class="nv-mijoz-kg">${fmt(g.jami_kg)} kg</span>
						</div>
					</div>
					<div class="nv-items"></div>
				</div>`);
			const $items = $c.find(".nv-items");
			g.zakazlar.forEach((z) => {
				const p = PROGRESS[z.progress] || PROGRESS.kutilmoqda;
				const kgHtml = z.bolingan
					? `${fmt(z.kun_kg)} <span class="nv-mini text-muted">/ ${fmt(z.kg)} kg</span>`
					: `${fmt(z.kg)} kg`;
				const $z = $(`
					<div class="nv-zakaz">
						<div class="nv-zakaz-head">
							<a href="/app/${z.zapas ? "material-request" : "sales-order"}/${z.name}">${z.name}</a>
							<span class="nv-badge nv-badge-${p.rang}">${z.zapas && z.progress === "jonatildi" ? __("Omborga kirdi") : p.label}</span>
							${z.bolingan ? `<span class="nv-badge nv-badge-sariq">🔀 ${__("bo'lingan")}</span>` : ""}
							${z.ombordan > 0 ? `<span class="nv-badge nv-badge-kok">📦 ${__("ombordan")}</span>` : ""}
							<span class="nv-zakaz-kg">${kgHtml}</span>
							${
								!z.zapas && z.progress === "tayyor" && SOTUV_ROL
									? `<button class="btn btn-xs btn-primary nv-jonat">📦 ${__("Jo'natildi")}</button>`
									: ""
							}
							${z.zapas ? "" : `<button class="btn btn-xs btn-default nv-sur">→ ${__("surish")}</button>`}
						</div>
						${
							z.bolingan
								? `<div class="nv-mini text-muted">🔀 ${__("Kunlarga bo'lingan")}: ${(z.taqsimot || [])
										.map((t) => `${qisqaSana(t.sana)} — ${fmt(t.kg)} kg`)
										.join(" · ")}</div>`
								: ""
						}
						${
							z.ombordan > 0
								? `<div class="nv-mini nv-kok">📦 ${__("Ombordan band qilingan")}: <b>${fmt(z.ombordan)} kg</b> · ${__("ishlab chiqariladi")}: ${fmt(z.kg - z.ombordan)} kg</div>`
								: ""
						}
						${z.izoh ? `<div class="nv-mini text-muted">💬 ${frappe.utils.escape_html(z.izoh)}</div>` : ""}
						${
							z.kg_nomalum
								? `<div class="nv-mini nv-warn">⚠ ${__("Kg aniqlanmagan qatorlar bor")}: ${frappe.utils.escape_html(z.kg_nomalum)}</div>`
								: ""
						}
					</div>`);
				$z.find(".nv-sur").on("click", () => surishDialog(z.name, d.sana));
				$z.find(".nv-jonat").on("click", () => jonatish(z.name));
				const $tbl = $('<div class="nv-item-rows"></div>').appendTo($z);
				z.items.forEach((it) => $tbl.append(itemRow(it)));
				$items.append($z);
			});
			$cards.append($c);
		});

		// --- mahsulot kesimi (zames)
		if (d.kesim && d.kesim.length) {
			const $k = $(`
				<div class="nv-card">
					<div class="nv-label" style="margin-bottom:8px">
						${__("Mahsulot kesimida jami")} (${__("zames hisobi")}, ${fmt(d.zames_kg)} kg/zames)
					</div>
					<div class="nv-kesim-head nv-kesim-row">
						<span>${__("Tayyor mahsulot")}</span><span>${__("Reja")}</span><span>${__("Zames")}</span>
					</div>
				</div>`).appendTo($right);
			let jamiZames = 0;
			d.kesim.forEach((r) => {
				jamiZames += r.zames;
				$k.append(`
					<div class="nv-kesim-row">
						<span>${frappe.utils.escape_html(r.gp)}</span>
						<span>${fmt(r.kg)} kg</span>
						<span class="nv-zames">${r.zames}</span>
					</div>`);
			});
			$k.append(`
				<div class="nv-kesim-row nv-kesim-jami">
					<span>${__("Jami")}</span>
					<span>${fmt(d.jami_kg)} kg</span>
					<span class="nv-zames">${jamiZames}</span>
				</div>`);
		}
	}

	// -------------------------------------------------------------- qator UI
	function itemRow(it) {
		const nom = frappe.utils.escape_html(it.item_name);
		const qty = `${fmt(it.qty)} ${frappe.utils.escape_html(it.uom || "")}`;
		// ishlab chiqariladigan qism = jami kg − ombordan band qilingani
		const ishlabKg = Math.max(flt(it.kg) - flt(it.ombordan_kg), 0);
		const kg = it.kg_nomalum ? "? kg" : fmt(ishlabKg) + " kg";
		const omborBadge =
			it.ombordan_kg > 0
				? ` <span class="nv-mini nv-kok">📦 ${fmt(it.ombordan_kg)} kg ${__("ombordan")}</span>`
				: "";
		const toliqOmbordan = it.ombordan_kg > 0 && ishlabKg < 0.05 && !it.kg_nomalum;

		// KUTILMOQDA: ishlab chiqarish xodimi fakt kg kiritib tasdiqlaydi
		if (it.holat === "Kutilmoqda") {
			const $r = $(`
				<div class="nv-item-row ${it.kg_nomalum ? "nv-warn" : ""}">
					<span class="nv-holat-ikon">○</span>
					<span class="nv-item-nom">${nom} <span class="text-muted">(${qty})</span>${omborBadge}</span>
					${
						ICH_ROL
							? `<input type="number" class="nv-fakt" value="${ishlabKg || ""}" placeholder="kg">
							   <button class="btn btn-xs btn-success nv-tasdiq">${__("Tasdiqlash")}</button>`
							: `<span class="nv-item-kg">${kg}</span>`
					}
				</div>`);
			$r.find(".nv-tasdiq").on("click", () => {
				const fakt = $r.find(".nv-fakt").val();
				frappe
					.call({
						method: "pokiza.api.navbat.chiqarildi",
						args: { row_name: it.row, fakt_kg: fakt },
					})
					.then((res) => {
						const m = res.message || {};
						// ombor kirimi uchun avtomatik tayyorlangan qoralama(lar)
						if ((m.pe || []).length) {
							frappe.msgprint({
								title: __("Ombor kirimi tayyorlandi"),
								message:
									__("Tasdiqlandi. Ombor kirimi uchun qoralama tayyor — ochib tekshiring va tasdiqlang:") +
									"<br>" +
									m.pe
										.map((p) => `<a href="/app/production-entry/${p}"><b>${p}</b></a>`)
										.join(", "),
								indicator: "blue",
							});
						}
						if (m.pe_xabar) {
							frappe.msgprint({ message: m.pe_xabar, indicator: "orange" });
						}
						yukla();
					});
			});
			return $r;
		}

		// CHIQARILDI / JONATILDI: fakt bilan reja farqi ko'rinadi.
		// Fakt kiritilmagan bo'lsa (masalan schyot to'g'ridan-to'g'ri submit
		// qilingan) — yolg'on "-N kg" farq o'rniga "fakt kiritilmagan" belgisi.
		// To'liq ombordan qoplangan qator ishlab chiqarilmaydi — fakt so'ralmaydi.
		const faktBor = flt(it.fakt_kg) > 0;
		const farq = flt(it.fakt_kg) - ishlabKg;
		const farqHtml =
			faktBor && !it.kg_nomalum && Math.abs(farq) > 0.05
				? `<span class="nv-mini ${farq < 0 ? "nv-qizil" : "nv-warn"}">(${farq > 0 ? "+" : ""}${fmt(farq)})</span>`
				: "";
		const faktHtml = faktBor
			? `<span class="nv-mini text-muted">${fmt(ishlabKg)} / <b>${fmt(it.fakt_kg)} kg</b></span> ${farqHtml}${omborBadge}`
			: toliqOmbordan
				? `<span class="nv-mini nv-kok">📦 ${__("to'liq ombordan")} (${fmt(it.ombordan_kg)} kg)</span>`
				: `<span class="nv-mini text-muted">${fmt(ishlabKg)} kg</span> <span class="nv-mini nv-warn">⚠ ${__("fakt kiritilmagan")}</span>${omborBadge}`;
		const ikon = it.holat === "Jonatildi" ? "📦" : "✓";
		const rang = it.holat === "Jonatildi" ? "nv-kok" : "nv-yashil";
		// ombor kirimi (PE) havolasi: qoralama — sariq "tasdiqlang",
		// tasdiqlangan — yashil "omborga kirdi"
		const peHtml = (it.pe || [])
			.map((p) =>
				p.docstatus === 1
					? `<a class="nv-pe nv-yashil" href="/app/production-entry/${p.name}">📋 ${p.name} ✓ ${__("omborga kirdi")}</a>`
					: `<a class="nv-pe nv-warn" href="/app/production-entry/${p.name}">📋 ${p.name} — ${__("tasdiqlang!")}</a>`
			)
			.join(" ");
		const $r = $(`
			<div class="nv-item-row">
				<span class="nv-holat-ikon ${rang}">${ikon}</span>
				<span class="nv-item-nom">${nom} ${faktHtml}${peHtml ? " " + peHtml : ""}</span>
				<span class="nv-mini text-muted">${it.chiqargan ? frappe.utils.escape_html(it.chiqargan.split("@")[0]) : ""}</span>
				${
					it.holat === "Chiqarildi" && ICH_ROL && !toliqOmbordan
						? `<button class="btn btn-xs btn-default nv-bekor">${__("bekor")}</button>`
						: ""
				}
			</div>`);
		$r.find(".nv-bekor").on("click", () => {
			frappe
				.call({ method: "pokiza.api.navbat.chiqarish_bekor", args: { row_name: it.row } })
				.then((res) => {
					const m = res.message || {};
					if (m.pe_xabar) {
						frappe.msgprint({ message: m.pe_xabar, indicator: "orange" });
					}
					yukla();
				});
		});
		return $r;
	}

	function jonatish(so) {
		frappe.confirm(
			__("Zakaz {0} jo'natilgan deb belgilansinmi?", [so]),
			() => {
				frappe
					.call({ method: "pokiza.api.navbat.jonatildi", args: { sales_order: so } })
					.then((r) => {
						const m = r.message || {};
						if (m.draft_si) {
							frappe.msgprint({
								message: __(
									"Belgilandi. Qoralama schyot tayyor — tekshirib tasdiqlang: {0}",
									[`<a href="/app/sales-invoice/${m.draft_si}"><b>${m.draft_si}</b></a>`]
								),
								indicator: "blue",
							});
						}
						yukla();
					});
			}
		);
	}

	function peQoralamaDialog(d) {
		if (!d.soni) return;
		const rows = (d.royxat || [])
			.map(
				(r) =>
					`<div class="nv-item-row">
						<a href="/app/production-entry/${r.name}"><b>${r.name}</b></a>
						<span class="nv-item-nom">${frappe.utils.escape_html(r.item || "")}${r.so ? ` <span class="text-muted">(${r.so})</span>` : ""}</span>
						<span class="nv-item-qty">${r.sana ? qisqaSana(r.sana) : ""}</span>
						<span class="nv-item-kg">${fmt(r.kg)} kg</span>
					</div>`
			)
			.join("");
		frappe.msgprint({
			title: __("Tasdiqlanmagan ombor kirimlari") + ` (${d.soni} ${__("ta")}, ${fmt(d.kg)} kg)`,
			message: `
				<div class="nv-mini nv-warn" style="margin-bottom:8px">
					⚠ ${__("Bu mahsulotlar hali OMBORGA KIRMAGAN — qoldiq haqiqatdan kam ko'rinadi, schyot tasdiqlashda 'qoldiq yetmaydi' xatosi chiqishi mumkin.")}
				</div>
				<div class="nv-item-rows">${rows}</div>
				${d.soni > (d.royxat || []).length ? `<div class="nv-mini text-muted">${__("...va yana")} ${d.soni - d.royxat.length} ${__("ta")} — <a href="/app/production-entry?docstatus=0">${__("to'liq ro'yxat")}</a></div>` : ""}`,
			indicator: "orange",
		});
	}

	function siQoralamaDialog(d) {
		if (!d.soni) return;
		const rows = (d.royxat || [])
			.map(
				(r) =>
					`<div class="nv-item-row">
						<a href="/app/sales-invoice/${r.name}"><b>${r.name}</b></a>
						<span class="nv-item-nom">${frappe.utils.escape_html(r.mijoz || "")}</span>
						<span class="nv-item-qty">${r.sana ? qisqaSana(r.sana) : ""}</span>
						<span class="nv-item-kg">${fmt(r.summa)}</span>
					</div>`
			)
			.join("");
		frappe.msgprint({
			title: __("Tasdiqlanmagan schyotlar") + ` (${d.soni} ${__("ta")}, ${fmt(d.summa)})`,
			message: `
				<div class="nv-mini nv-warn" style="margin-bottom:8px">
					⚠ ${__("Bu schyotlar tasdiqlanmaguncha: pul/qarzdorlik hisobga TUSHMAGAN va mahsulot ombordan CHIQMAGAN.")}
				</div>
				<div class="nv-item-rows">${rows}</div>
				${d.soni > (d.royxat || []).length ? `<div class="nv-mini text-muted">${__("...va yana")} ${d.soni - d.royxat.length} ${__("ta")} — <a href="/app/sales-invoice?docstatus=0">${__("to'liq ro'yxat")}</a></div>` : ""}`,
			indicator: "orange",
		});
	}

	function kechikkanDialog(list) {
		if (!list.length) return;
		const rows = list
			.map(
				(r) =>
					`<div class="nv-item-row">
						<a href="/app/sales-order/${r.so}">${r.so}</a>
						<span class="nv-item-qty">${sanaLabel(r.kun)}</span>
						<span class="nv-item-kg">${fmt(r.kg)} kg</span>
					</div>`
			)
			.join("");
		frappe.msgprint({
			title: __("Kechikkan zakazlar (reja kuni o'tgan, jo'natilmagan)"),
			message: `<div class="nv-item-rows">${rows}</div>`,
			indicator: "red",
		});
	}

	// ------------------------------------------------------------- harakatlar
	function surSana(step, yakshanbaDam) {
		let yangi = frappe.datetime.add_days(state.sana, step);
		// yakshanba dam bo'lsa navigatsiya uni sakrab o'tadi
		if (yakshanbaDam && moment(yangi).day() === 0) {
			yangi = frappe.datetime.add_days(yangi, step);
		}
		tanla(yangi);
	}

	function surishDialog(so, joriySana) {
		const dlg = new frappe.ui.Dialog({
			title: __("Zakazni boshqa kunga surish") + " — " + so,
			fields: [
				{
					fieldname: "yangi_kun",
					label: __("Yangi kun"),
					fieldtype: "Date",
					reqd: 1,
					default: frappe.datetime.add_days(joriySana, 1),
				},
				{
					fieldname: "sabab",
					label: __("Sabab (jurnalga yoziladi)"),
					fieldtype: "Small Text",
				},
			],
			primary_action_label: __("Surish"),
			primary_action(v) {
				frappe
					.call({
						method: "pokiza.api.navbat.surish",
						args: { sales_order: so, yangi_kun: v.yangi_kun, sabab: v.sabab },
					})
					.then((r) => {
						dlg.hide();
						const m = r.message || {};
						if (m.toldi) {
							frappe.msgprint({
								message: __(
									"Zakaz surildi, lekin yangi kun sig'imdan oshib ketdi ({0} / {1} kg)",
									[fmt(m.yangi_kun_band), fmt(m.quvvat)]
								),
								indicator: "orange",
							});
						}
						yukla();
					});
			},
		});
		dlg.show();
	}

	// ======================================================== ZAKAZ URISH TAB
	// ------------------------------------------------- 3 QOG'OZ (print)
	// 1-Farsh rejasi (texnolog) · 2-Shprits rejasi · 3-Tarozi varaqasi.
	// Ma'lumot serverdan (kun_qogozlari), yangi oynada chop etiladi.
	function qogozChiqar(sana) {
		frappe
			.call({ method: "pokiza.api.navbat.kun_qogozlari", args: { sana } })
			.then((r) => {
				const d = r.message;
				if (!d || !(d.farsh || []).length) {
					frappe.show_alert({ message: __("Bu kunga ishlab chiqarish rejasi yo'q"), indicator: "orange" });
					return;
				}
				const w = window.open("", "_blank");
				if (!w) {
					frappe.msgprint(__("Brauzer yangi oynani blokladi — ruxsat bering"));
					return;
				}
				w.document.write(qogozHtml(d));
				w.document.close();
				w.focus();
				setTimeout(() => w.print(), 400);
			});
	}

	function esc(t) {
		return String(t == null ? "" : t)
			.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
	}

	function qogozHtml(d) {
		const sana = sanaLabel(d.sana);
		const kesimga = (rows) => rows.map((f) => `
			<tr><td>${esc(f.norma)}</td>
				<td class="num">${fmt(f.kg)}</td>
				<td class="num">${f.zames}</td></tr>`).join("");
		const shpritsga = (rows) => rows.map((n) => `
			<tr class="norma-row"><td colspan="2"><b>${esc(n.norma)}</b></td>
				<td class="num"><b>${fmt(n.jami)} kg</b></td></tr>
			${n.skular.map((s) => `
			<tr><td class="indent"></td><td>${esc(s.nom)}</td>
				<td class="num">${fmt(s.kg)}</td></tr>`).join("")}`).join("");
		const tarozga = (rows) => rows.map((t) => t.normalar.map((n, i) => `
			<tr>${i === 0 ? `<td rowspan="${t.normalar.length}">${esc(t.nom)}</td>` : ""}
				<td>${esc(n.norma)}</td>
				<td class="num">${fmt(n.kg)}</td>
				<td class="fakt"></td><td class="fakt"></td></tr>`).join("")).join("");

		return `<!doctype html><html><head><meta charset="utf-8">
		<title>${esc(d.sana)} qog'ozlar</title>
		<style>
			body { font-family: Arial, sans-serif; font-size: 13px; margin: 24px; color: #000; }
			h2 { margin: 0 0 2px; font-size: 17px; }
			.sub { color: #444; margin-bottom: 10px; font-size: 12px; }
			table { width: 100%; border-collapse: collapse; margin-bottom: 8px; }
			th, td { border: 1px solid #999; padding: 5px 8px; text-align: left; }
			th { background: #eee; }
			.num { text-align: right; white-space: nowrap; }
			.fakt { width: 90px; }
			.indent { width: 20px; border-right: none; }
			.norma-row td { background: #f5f5f5; }
			.imzo { margin: 14px 0 0; font-size: 12px; }
			.page { page-break-after: always; }
			.page:last-child { page-break-after: auto; }
		</style></head><body>

		<div class="page">
			<h2>1-QOG'OZ · FARSH ISHLAB CHIQARISH REJASI</h2>
			<div class="sub">${sana} · jami ${fmt(d.jami_kg)} kg · (texnolog uchun)</div>
			<table><tr><th>Norma / retsept</th><th class="num">Kg</th><th class="num">Zames</th></tr>
			${kesimga(d.farsh)}</table>
			<div class="imzo">Texnolog: ________________ &nbsp;&nbsp; Imzo: ________ &nbsp;&nbsp; Vaqt: ________</div>
		</div>

		<div class="page">
			<h2>2-QOG'OZ · SHPRITS REJASI</h2>
			<div class="sub">${sana} · qaysi farsh qaysi mahsulotga urilishi</div>
			<table><tr><th colspan="2">Norma → SKU</th><th class="num">Kg</th></tr>
			${shpritsga(d.shprits)}</table>
			<div class="imzo">Shpritschi: ________________ &nbsp;&nbsp; Imzo: ________ &nbsp;&nbsp; Vaqt: ________</div>
		</div>

		<div class="page">
			<h2>3-QOG'OZ · TAROZI VARAQASI</h2>
			<div class="sub">${sana} · pishirishdan keyin fakt og'irlik yoziladi</div>
			<table><tr><th>Mahsulot (SKU)</th><th>Norma</th><th class="num">Reja kg</th><th>Fakt kg</th><th>Izoh</th></tr>
			${tarozga(d.tarozi)}</table>
			<div class="imzo">Tarozichi: ________________ &nbsp;&nbsp; Imzo: ________ &nbsp;&nbsp; Vaqt: ________</div>
		</div>

		</body></html>`;
	}

	// Faqat jadval: sales orderdan kelgan zakazlar ro'yxati (faqat ko'rish).
	// Kimdan, qancha mahsulot, qachonga — hech narsaga bog'lanmagan (ombor ham).
	function zakazYukla() {
		const $f = $tabs.zakaz;
		$f.empty().append(`<div class="nv-card nv-empty">${__("Yuklanmoqda...")}</div>`);
		frappe.call({ method: "pokiza.api.navbat.zakaz_royxat" }).then((r) => {
			const rows = (r.message || {}).rows || [];
			$f.empty();
			const $card = $(`
				<div class="nv-card nv-zk">
					<div class="nv-zk-title">🛒 ${__("Zakazlar ro'yxati")}
						<span class="nv-mini text-muted">(${__("oxirgi")} ${rows.length} ${__("ta")})</span>
					</div>
					<input type="text" class="form-control nv-zr-search"
						placeholder="🔍 ${__("Qidirish: mijoz yoki mahsulot...")}">
					<div class="nv-zr-table">
						<div class="nv-zr-row nv-zr-head">
							<span class="nv-zr-sana">${__("Olingan vaqt")}</span>
							<span>${__("Mijoz")}</span>
							<span class="nv-zr-mahs">${__("Mahsulot")}</span>
							<span class="nv-zr-num">${__("Jami kg")}</span>
							<span class="nv-zr-sana">${__("Qachonga")}</span>
						</div>
					</div>
				</div>`).appendTo($f);
			const $t = $card.find(".nv-zr-table");
			if (!rows.length) {
				$t.append(`<div class="nv-zr-empty">${__("Hozircha zakaz yo'q")}</div>`);
				return;
			}
			rows.forEach((z) => {
				const mahs = (z.items || [])
					.map((it) =>
						`${frappe.utils.escape_html(it.nom)} — ${fmt(it.qty)} ${it.uom || ""}` +
						(it.kg !== null && Math.abs(it.kg - it.qty) > 0.05
							? ` <span class="text-muted">(${fmt(it.kg)} kg)</span>` : ""))
					.join("<br>");
				$t.append(`
					<div class="nv-zr-row">
						<span class="nv-zr-sana">${vaqtLabel(z.kelgan)}</span>
						<span class="nv-zr-mijoz">${frappe.utils.escape_html(z.mijoz)}</span>
						<span class="nv-zr-mahs">${mahs || "—"}</span>
						<span class="nv-zr-num">${z.kg_nomalum ? "?" : fmt(z.jami_kg)}</span>
						<span class="nv-zr-sana">${z.qachonga ? qisqaSana(z.qachonga) : "—"}</span>
					</div>`);
			});
			$card.find(".nv-zr-search").on("input", function () {
				const q = ($(this).val() || "").toLowerCase();
				$t.find(".nv-zr-row").not(".nv-zr-head").each(function () {
					$(this).toggle(!q || $(this).text().toLowerCase().includes(q));
				});
			});
		});
	}

	function vaqtLabel(dt) {
		if (!dt) return "—";
		const [sana, vaqt] = String(dt).split(" ");
		return qisqaSana(sana) + (vaqt ? " " + vaqt.slice(0, 5) : "");
	}

	// ============================================================= OMBOR TAB
	function omborYukla() {
		const $o = $tabs.ombor;
		$o.empty().append(`<div class="nv-card nv-empty">${__("Yuklanmoqda...")}</div>`);
		frappe.call({ method: "pokiza.api.navbat.get_ombor" }).then((r) => {
			const d = r.message || { rows: [] };
			$o.empty();
			const $c = $(`
				<div class="nv-card">
					<div class="nv-row-между">
						<span class="nv-label">📦 ${__("Tayyor mahsulot ombori")}</span>
						<span class="nv-mini text-muted">
							${__("jami")}: <b>${fmt(d.jami_qoldiq)} kg</b> · ${__("band")}: <b>${fmt(d.jami_band)} kg</b>
						</span>
					</div>
					<input type="text" class="form-control nv-om-search"
						placeholder="🔍 ${__("qidirish...")}" style="margin:8px 0">
					<div class="nv-om-rows">
						<div class="nv-om-row nv-om-head">
							<span>${__("Mahsulot")}</span><span>${__("Qoldiq")}</span>
							<span>${__("Band")}</span><span>${__("Bo'sh")}</span>
						</div>
					</div>
					${!d.rows.length ? `<div class="nv-empty">${__("Omborda tayyor mahsulot yo'q")}</div>` : ""}
				</div>`).appendTo($o);
			const $rows = $c.find(".nv-om-rows");
			d.rows.forEach((row) => {
				$rows.append(`
					<div class="nv-om-row" data-nom="${frappe.utils.escape_html(row.gp.toLowerCase())}">
						<span>${frappe.utils.escape_html(row.gp)}</span>
						<span>${fmt(row.qoldiq)}</span>
						<span class="${row.band > 0 ? "nv-kok" : "text-muted"}">${row.band > 0 ? fmt(row.band) : "—"}</span>
						<span class="${row.bosh <= 0 ? "nv-qizil" : "nv-yashil"}"><b>${fmt(row.bosh)}</b></span>
					</div>`);
			});
			$c.find(".nv-om-search").on("input", function () {
				const q = ($(this).val() || "").toLowerCase();
				$rows.find(".nv-om-row").not(".nv-om-head").each(function () {
					$(this).toggle(($(this).data("nom") || "").includes(q));
				});
			});
		});
	}

	// ========================================================= SOZLAMALAR TAB
	function sozlamaYukla() {
		const $s = $tabs.sozlama;
		$s.empty().append(`<div class="nv-card nv-empty">${__("Yuklanmoqda...")}</div>`);
		frappe.call({ method: "pokiza.api.navbat.sozlamalar_get" }).then((r) => {
			const d = r.message || {};
			$s.empty();
			const dis = d.tahrir_mumkin ? "" : "disabled";
			const $c = $(`
				<div class="nv-card nv-soz">
					<div class="nv-label" style="margin-bottom:10px">⚙️ ${__("Ishlab chiqarish sozlamalari")}</div>
					<div class="nv-soz-grid">
						<label>${__("Kunlik sig'im (kg)")}
							<input type="number" class="form-control" data-f="kunlik_quvvat_kg"
								value="${d.kunlik_quvvat_kg || ""}" min="1" step="any" ${dis}></label>
						<label>${__("Kesim vaqti (shu vaqtdan keyingi zakaz ertaga)")}
							<input type="time" class="form-control" data-f="kesim_vaqti"
								value="${(d.kesim_vaqti || "13:00:00").slice(0, 5)}" ${dis}></label>
						<label>${__("Zames hajmi (kg)")}
							<input type="number" class="form-control" data-f="zames_kg"
								value="${d.zames_kg || ""}" min="1" step="any" ${dis}></label>
						<label>${__("Gorizont (necha kun ko'rinadi)")}
							<input type="number" class="form-control" data-f="gorizont_kun"
								value="${d.gorizont_kun || 7}" min="3" max="14" ${dis}></label>
						<label class="nv-soz-check">
							<input type="checkbox" data-f="yakshanba_ishlaydi"
								${d.yakshanba_ishlaydi ? "checked" : ""} ${dis}>
							${__("Yakshanba ham ishlaydi")}</label>
					</div>
					${
						d.tahrir_mumkin
							? `<button class="btn btn-primary btn-sm nv-soz-save">💾 ${__("Saqlash")}</button>`
							: `<div class="nv-mini text-muted">${__("O'zgartirish faqat rahbarga ruxsat etilgan")}</div>`
					}
				</div>`).appendTo($s);
			$c.find(".nv-soz-save").on("click", () => {
				const v = {};
				$c.find("[data-f]").each(function () {
					const f = $(this).data("f");
					v[f] = $(this).attr("type") === "checkbox"
						? ($(this).prop("checked") ? 1 : 0)
						: $(this).val();
				});
				if (v.kesim_vaqti && v.kesim_vaqti.length === 5) v.kesim_vaqti += ":00";
				frappe
					.call({
						method: "pokiza.api.navbat.sozlamalar_saqla",
						args: v,
						freeze: true,
					})
					.then(() => {
						frappe.show_alert({ message: __("Sozlamalar saqlandi"), indicator: "green" });
						yukla();
					});
			});
		});
	}

	// --------------------------------------------------------------- yordamchi
	function fmt(n) {
		return cint(n) === flt(n)
			? cint(n).toLocaleString("ru-RU")
			: flt(n).toLocaleString("ru-RU");
	}
	function sanaLabel(s) {
		const kunlar = [
			__("Yakshanba"), __("Dushanba"), __("Seshanba"), __("Chorshanba"),
			__("Payshanba"), __("Juma"), __("Shanba"),
		];
		const m = moment(s);
		return `${m.format("D.MM")}, ${kunlar[m.day()]}`;
	}
	function qisqaSana(s) {
		return moment(s).format("D.MM");
	}

	function injectCss() {
		if ($("#navbat-css").length) return;
		$(`<style id="navbat-css">
			/* to'liq ekran: frappening tor konteyneri shu sahifada ochiladi */
			.nv-full .container { max-width: 100%; width: 100%; }
			.navbat-wrap { max-width: none; margin: 0; }
			/* tepadagi bo'lim tugmalari (o'ng tarafda) */
			.nv-tabs { display: flex; justify-content: flex-end; gap: 6px;
				margin-bottom: 12px; flex-wrap: wrap; }
			.nv-tab-btn { border: 1px solid var(--border-color); background: var(--card-bg);
				border-radius: 8px; padding: 6px 14px; font-size: 12.5px; font-weight: 600;
				cursor: pointer; color: var(--text-color); }
			.nv-tab-active { background: var(--primary, #7c3aed); color: #fff;
				border-color: var(--primary, #7c3aed); }
			/* keng ekranda: chapda zakazlar, o'ngda mahsulot kesimi (zames) */
			.nv-main { display: flex; flex-direction: column; }
			.nv-main-left { min-width: 0; }
			.nv-main-right { min-width: 0; }
			@media (min-width: 1200px) {
				.nv-main { flex-direction: row; gap: 14px; align-items: flex-start; }
				.nv-main-left { flex: 3; }
				.nv-main-right { flex: 2; max-width: 480px; position: sticky; top: 70px; }
			}
			.nv-card { background: var(--card-bg); border: 1px solid var(--border-color);
				border-radius: 10px; padding: 12px 14px; margin-bottom: 12px; }
			.nv-nav { display: flex; align-items: center; gap: 8px; }
			.nv-nav-mid { flex: 1; text-align: center; }
			.nv-sana { font-size: 15px; font-weight: 600; }
			.nv-sub { font-size: 11px; color: var(--text-muted); }
			.nv-row-между { display: flex; justify-content: space-between; align-items: baseline; }
			.nv-label { font-size: 12px; color: var(--text-muted); font-weight: 600; }
			.nv-kg { font-weight: 700; }
			.nv-yashil { color: var(--green-600, #28a745); }
			.nv-sariq { color: var(--orange-600, #e67e22); }
			.nv-qizil { color: var(--red-600, #dc3545); }
			.nv-kok { color: #0d6efd; }
			.nv-tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
				gap: 8px; margin-bottom: 12px; }
			.nv-tile { background: var(--card-bg); border: 1px solid var(--border-color);
				border-radius: 10px; padding: 10px 12px; text-align: center; }
			.nv-tile-num { font-size: 20px; font-weight: 700; }
			.nv-tile-label { font-size: 11px; color: var(--text-muted); }
			.nv-tile-sub { font-size: 10.5px; color: var(--text-muted); margin-top: 2px; }
			.nv-tile-qizil { border-color: #dc3545; }
			.nv-tile-qizil .nv-tile-num { color: #dc3545; }
			.nv-tile-sariq { border-color: #e67e22; }
			.nv-tile-sariq .nv-tile-num { color: #e67e22; }
			.nv-click { cursor: pointer; }
			.nv-badge { font-size: 10px; font-weight: 700; padding: 1px 8px; border-radius: 9px; text-transform: uppercase; }
			.nv-badge-kul { background: var(--control-bg); color: var(--text-muted); }
			.nv-badge-sariq { background: rgba(230,126,34,.15); color: #e67e22; }
			.nv-badge-yashil { background: rgba(40,167,69,.15); color: #28a745; }
			.nv-badge-kok { background: rgba(13,110,253,.15); color: #0d6efd; }
			.nv-holat-ikon { width: 18px; text-align: center; }
			.nv-fakt { width: 74px; border: 1px solid var(--border-color); border-radius: 6px;
				padding: 2px 6px; font-size: 12px; text-align: right; background: var(--control-bg); }
			.nv-zakaz-kg { font-weight: 600; margin-left: auto; }
			.nv-bar { height: 9px; background: var(--control-bg); border-radius: 6px; overflow: hidden; margin-top: 6px; }
			.nv-bar-fill { height: 100%; border-radius: 6px; transition: width .3s; }
			.nv-bg-yashil { background: #28a745; } .nv-bg-sariq { background: #e67e22; }
			.nv-bg-qizil { background: #dc3545; } .nv-bg-dam { background: var(--control-bg); }
			.nv-mini { font-size: 11px; margin-top: 5px; }
			.nv-pe { font-size: 11px; font-weight: 600; white-space: nowrap; }
			.nv-warn { color: #e67e22; }
			.nv-overflow { border-color: #dc3545; background: rgba(220,53,69,.05); }
			.nv-of-title { font-size: 13px; color: #dc3545; }
			.nv-of-sub { font-size: 11.5px; color: var(--text-muted); margin: 5px 0; }
			.nv-of-list { display: flex; flex-wrap: wrap; gap: 6px; }
			.nv-gorizont { display: flex; gap: 6px; margin-bottom: 12px; }
			.nv-gz-kun { flex: 1; text-align: center; cursor: pointer; background: var(--card-bg);
				border: 1px solid var(--border-color); border-radius: 8px; padding: 6px 2px; }
			.nv-gz-active { border-color: var(--primary, #7c3aed); box-shadow: 0 0 0 1px var(--primary, #7c3aed); }
			.nv-gz-dam { opacity: .5; }
			.nv-gz-sana { font-size: 10.5px; color: var(--text-muted); }
			.nv-gz-bugun { color: var(--primary, #7c3aed); font-weight: 700; }
			.nv-gz-bar { height: 34px; background: var(--control-bg); border-radius: 4px; margin: 4px 4px;
				display: flex; align-items: flex-end; overflow: hidden; }
			.nv-gz-bar > div { width: 100%; }
			.nv-gz-kg { font-size: 10.5px; font-weight: 600; }
			.nv-mijoz-head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; flex-wrap: wrap; }
			.nv-mijoz-nom { font-size: 14px; font-weight: 600; }
			.nv-idx { display: inline-flex; width: 20px; height: 20px; border-radius: 50%;
				background: var(--control-bg); font-size: 11px; align-items: center; justify-content: center; margin-right: 4px; }
			.nv-mijoz-right { display: flex; gap: 10px; align-items: baseline; }
			.nv-slot { font-size: 11px; color: var(--text-muted); }
			.nv-mijoz-kg { font-weight: 700; font-size: 13px; }
			.nv-zakaz { border-top: 1px dashed var(--border-color); margin-top: 8px; padding-top: 8px; }
			.nv-zakaz-head { display: flex; gap: 10px; align-items: baseline; font-size: 12.5px; }
			.nv-zakaz-head a { font-weight: 600; }
			.nv-item-rows { margin-top: 5px; }
			.nv-item-row { display: flex; gap: 8px; font-size: 12px; padding: 2.5px 0; }
			.nv-item-nom { flex: 1; }
			.nv-item-qty { color: var(--text-muted); min-width: 90px; text-align: right; }
			.nv-item-kg { min-width: 80px; text-align: right; font-weight: 600; }
			.nv-kesim-row { display: grid; grid-template-columns: 1fr 110px 70px; gap: 6px;
				font-size: 12.5px; padding: 3px 0; }
			.nv-kesim-row span:nth-child(2), .nv-kesim-row span:nth-child(3) { text-align: right; }
			.nv-kesim-head { font-size: 10.5px; color: var(--text-muted); text-transform: uppercase;
				border-bottom: 1px solid var(--border-color); padding-bottom: 4px; }
			.nv-kesim-jami { border-top: 1px solid var(--border-color); font-weight: 700; margin-top: 4px; padding-top: 6px; }
			.nv-zames { font-weight: 700; color: #e67e22; }
			.nv-empty { text-align: center; color: var(--text-muted); padding: 30px; }
			/* --- zakazlar ro'yxati (jadval) --- */
			.nv-zk { max-width: 1000px; }
			.nv-zk-title { font-size: 14px; font-weight: 700; margin-bottom: 10px; }
			.nv-zr-search { max-width: 340px; margin-bottom: 10px; }
			.nv-zr-table { overflow-x: auto; }
			.nv-zr-row { display: grid; grid-template-columns: 110px 1.2fr 2fr 80px 90px;
				gap: 10px; padding: 7px 4px; font-size: 12.5px;
				border-bottom: 1px solid var(--border-color); align-items: start; }
			.nv-zr-head { font-size: 10.5px; text-transform: uppercase;
				color: var(--text-muted); font-weight: 600;
				border-bottom: 2px solid var(--border-color); }
			.nv-zr-num { text-align: right; font-weight: 600; }
			.nv-zr-mijoz { font-weight: 600; }
			.nv-zr-sana { white-space: nowrap; }
			.nv-zr-empty { text-align: center; color: var(--text-muted); padding: 20px; }
			@media (max-width: 700px) {
				.nv-zr-row { grid-template-columns: 90px 1fr 70px; }
				.nv-zr-mahs { grid-column: 1 / -1; padding-left: 8px; }
				.nv-zr-row > .nv-zr-sana:last-child { display: none; }
			}
			/* --- ombor jadvali --- */
			.nv-om-row { display: grid; grid-template-columns: 1fr 100px 100px 100px; gap: 8px;
				font-size: 12.5px; padding: 4px 0; border-bottom: 1px solid var(--border-color); }
			.nv-om-row span:nth-child(n+2) { text-align: right; }
			.nv-om-head { font-size: 10.5px; color: var(--text-muted); text-transform: uppercase; }
			/* --- sozlamalar --- */
			.nv-soz { max-width: 560px; }
			.nv-soz-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 14px; }
			@media (max-width: 600px) { .nv-soz-grid { grid-template-columns: 1fr; } }
			.nv-soz-grid label { font-size: 12px; color: var(--text-muted); font-weight: 600; }
			.nv-soz-check { display: flex; align-items: center; gap: 8px; }
		</style>`).appendTo("head");
	}

	yukla();
};
