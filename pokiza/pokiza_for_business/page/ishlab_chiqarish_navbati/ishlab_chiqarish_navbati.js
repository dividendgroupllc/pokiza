// ============================================================================
//  ISHLAB CHIQARISH NAVBATI — zavod ish markazi (artifact spec asosida)
//  4 bo'lim (tepada o'ngda): 🛒 Zakaz urish · 🏭 Ishlab chiqarish ·
//  📦 Ombor · ⚙️ Sozlamalar
//  - Zakaz urish: faqat "Сотув махсулотлари" itemlari, kiritish -> tekshiruv
//    (limit + ombor) -> Sales Order SUBMIT -> navbatga avto tushadi.
//  - Limitga sig'masa ombordagi tayyor mahsulot taklif qilinadi (band qilish).
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
		frappe.user.has_role("System Manager");
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
		if (t === "zakaz" && !zakazQurilgan) zakazForm();
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
			</div>`).appendTo($body);
		$nav.find(".nv-prev").on("click", () => surSana(-1, d.yakshanba_dam));
		$nav.find(".nv-next").on("click", () => surSana(1, d.yakshanba_dam));
		$nav.find(".nv-bugun").on("click", () => {
			state.gBoshi = bugun;
			tanla(bugun);
		});

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
							<a href="/app/sales-order/${z.name}">${z.name}</a>
							<span class="nv-badge nv-badge-${p.rang}">${p.label}</span>
							${z.bolingan ? `<span class="nv-badge nv-badge-sariq">🔀 ${__("bo'lingan")}</span>` : ""}
							${z.ombordan > 0 ? `<span class="nv-badge nv-badge-kok">📦 ${__("ombordan")}</span>` : ""}
							<span class="nv-zakaz-kg">${kgHtml}</span>
							${
								z.progress === "tayyor" && SOTUV_ROL
									? `<button class="btn btn-xs btn-primary nv-jonat">📦 ${__("Jo'natildi")}</button>`
									: ""
							}
							<button class="btn btn-xs btn-default nv-sur">→ ${__("surish")}</button>
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
	let zakazQurilgan = false;
	let mijozCtrl = null;
	let zakazRows = []; // [{$r, ctrl}]

	function zakazForm() {
		zakazQurilgan = true;
		zakazRows = [];
		const $f = $tabs.zakaz;
		$f.empty();
		const $card = $(`
			<div class="nv-card nv-zk">
				<div class="nv-zk-title">🛒 ${__("Yangi zakaz")}
					<span class="nv-mini text-muted">(${__("faqat sotuv mahsulotlari ko'rinadi")})</span>
				</div>
				<div class="nv-zk-top">
					<div class="nv-zk-mijoz"></div>
					<div class="nv-zk-kun-wrap">
						<label class="nv-label">📅 ${__("Qaysi kunga (oldindan zakaz)")}</label>
						<input type="date" class="form-control nv-zk-kun"
							value="${frappe.datetime.get_today()}" min="${frappe.datetime.get_today()}">
					</div>
				</div>
				<div class="nv-zk-items-head">
					<span>${__("Mahsulot")}</span><span>${__("Miqdor")}</span><span></span>
					<span>${__("Ombordagi qoldiq")}</span><span>${__("Ombordan olish (kg)")}</span><span></span>
				</div>
				<div class="nv-zk-items"></div>
				<button class="btn btn-xs btn-default nv-zk-add">+ ${__("Mahsulot qo'shish")}</button>
				<div class="nv-zk-extra">
					<div>
						<label class="nv-label">🚚 ${__("Mashina vaqti")}</label>
						<div class="nv-zk-slot-row">
							<select class="form-control nv-zk-slot">
								<option>Ertalab</option>
								<option>Tushlik / abed atrofi</option>
								<option>Kechki salqin</option>
								<option selected>Boshqa vaqt</option>
							</select>
							<input type="text" class="form-control nv-zk-slot-izoh"
								placeholder="${__("aniq vaqt (mas. 15:30)")}">
						</div>
					</div>
					<div>
						<label class="nv-label">💬 ${__("Izoh")}</label>
						<textarea class="form-control nv-zk-izoh" rows="2"
							placeholder="${__("masalan: mijoz o'zi olib ketadi")}"></textarea>
					</div>
				</div>
				<button class="btn btn-primary btn-sm nv-zk-submit">➤ ${__("Tekshirish va tasdiqlash")}</button>
			</div>`).appendTo($f);

		mijozCtrl = frappe.ui.form.make_control({
			df: {
				fieldtype: "Link",
				options: "Customer",
				label: __("Mijoz"),
				reqd: 1,
				get_query: () => ({ filters: { disabled: 0 } }),
			},
			parent: $card.find(".nv-zk-mijoz"),
			render_input: true,
		});

		qatorQosh();
		$card.find(".nv-zk-add").on("click", () => qatorQosh());
		$card.find(".nv-zk-submit").on("click", () => zakazTekshir($card));
	}

	function qatorQosh() {
		const $items = $tabs.zakaz.find(".nv-zk-items");
		const $r = $(`
			<div class="nv-zk-row">
				<div class="nv-zk-item"></div>
				<input type="number" class="form-control nv-zk-qty" min="0" step="any" placeholder="0">
				<span class="nv-zk-uom text-muted"></span>
				<span class="nv-zk-ombor text-muted"></span>
				<input type="number" class="form-control nv-zk-omb" min="0" step="any"
					placeholder="0" disabled title="${__("Ombordan band qilinadigan kg")}">
				<button class="btn btn-xs btn-default nv-zk-del">✕</button>
			</div>`).appendTo($items);
		const ctrl = frappe.ui.form.make_control({
			df: {
				fieldtype: "Link",
				options: "Item",
				placeholder: __("Mahsulot tanlang..."),
				// FAQAT sotuv mahsulotlari (egasi talabi)
				get_query: () => ({
					filters: { item_group: "Сотув махсулотлари", disabled: 0 },
				}),
			},
			parent: $r.find(".nv-zk-item"),
			render_input: true,
		});
		ctrl.df.onchange = () => {
			const v = ctrl.get_value();
			if (!v) return;
			frappe.db.get_value("Item", v, "stock_uom").then((r) => {
				$r.find(".nv-zk-uom").text((r.message || {}).stock_uom || "");
			});
			// ombordagi qoldiq darhol ko'rinadi (egasi talabi):
			// foydalansa bo'ladimi-yo'qmi shu yerning o'zida ma'lum bo'ladi
			const $om = $r.find(".nv-zk-ombor");
			$om.attr("class", "nv-zk-ombor text-muted").text("...");
			const $omb = $r.find(".nv-zk-omb");
			frappe
				.call({ method: "pokiza.api.navbat.item_ombor", args: { item_code: v } })
				.then((res) => {
					const o = res.message;
					if (!o) {
						$om.attr("class", "nv-zk-ombor text-muted")
							.text(__("ombor: aniqlanmadi"));
						$omb.prop("disabled", true).val("");
					} else if (o.bosh > 0.4) {
						$om.attr("class", "nv-zk-ombor nv-yashil")
							.html(`📦 <b>${fmt(o.bosh)} kg</b> ${__("bo'sh")}${
								o.band > 0 ? ` <span class="text-muted">(${fmt(o.band)} ${__("band")})</span>` : ""
							}`);
						// ombordan foydalanish HAR DOIM mumkin (egasi talabi) —
						// limit oshishini kutmasdan shu yerda kg kiritiladi
						$omb.prop("disabled", false).attr("max", o.bosh)
							.attr("placeholder", `${__("maks")} ${fmt(o.bosh)}`);
					} else {
						$om.attr("class", "nv-zk-ombor nv-qizil")
							.html(`❌ ${__("omborda yo'q")}`);
						$omb.prop("disabled", true).val("");
					}
				});
		};
		const row = { $r, ctrl };
		zakazRows.push(row);
		$r.find(".nv-zk-del").on("click", () => {
			zakazRows = zakazRows.filter((x) => x !== row);
			$r.remove();
		});
	}

	function zakazYigish() {
		const mijoz = mijozCtrl && mijozCtrl.get_value();
		if (!mijoz) {
			frappe.msgprint({ message: __("Mijozni tanlang"), indicator: "orange" });
			return null;
		}
		const items = [];
		zakazRows.forEach((row) => {
			const code = row.ctrl.get_value();
			const qty = parseFloat(row.$r.find(".nv-zk-qty").val());
			const ombordan = parseFloat(row.$r.find(".nv-zk-omb").val()) || 0;
			if (code && qty > 0) {
				const it = { item_code: code, qty: qty };
				if (ombordan > 0) it.ombordan_kg = ombordan;
				items.push(it);
			}
		});
		if (!items.length) {
			frappe.msgprint({
				message: __("Kamida bitta mahsulot va miqdor kiriting"),
				indicator: "orange",
			});
			return null;
		}
		// oldindan zakaz: tanlangan kundan boshlab rejalashtiriladi
		const bugun = frappe.datetime.get_today();
		let kerak_kun = $tabs.zakaz.find(".nv-zk-kun").val() || bugun;
		if (kerak_kun < bugun) {
			frappe.msgprint({
				message: __("O'tgan kunga zakaz olib bo'lmaydi"),
				indicator: "red",
			});
			return null;
		}
		return { mijoz, items, kerak_kun };
	}

	function zakazTekshir($card) {
		const g = zakazYigish();
		if (!g) return;
		frappe
			.call({
				method: "pokiza.api.navbat.zakaz_korish",
				args: { items: g.items, kerak_kun: g.kerak_kun },
				freeze: true,
				freeze_message: __("Tekshirilmoqda..."),
			})
			.then((r) => korikDialog(g, r.message, $card));
	}

	// ko'rik oynasi: reja + limitga sig'magan bo'lsa ombor taklifi
	function korikDialog(g, d, $card) {
		const rejaHtml = (d.taqsimot || [])
			.map((t) => `${qisqaSana(t.sana)} — <b>${fmt(t.kg)} kg</b>`)
			.join(" · ");

		// ombor bo'limi HAR DOIM ko'rinadi (egasi talabi) — limit oshgan
		// bo'lsa ogohlantirish ham qo'shiladi
		const itemRows = d.items
			.filter((it) => !it.kg_nomalum && it.kg > 0)
			.map((it) => {
				const o = it.ombor;
				if (!o) {
					return `<div class="nv-ko-row">
						<span>${frappe.utils.escape_html(it.item_name)}</span>
						<span class="nv-mini text-muted">${__("to'plami yo'q — ombordan tekshirib bo'lmadi")}</span>
					</div>`;
				}
				if (o.bosh < 0.5 && !(it.ombordan_kg > 0)) {
					return `<div class="nv-ko-row">
						<span>${frappe.utils.escape_html(it.item_name)}</span>
						<span class="nv-qizil">❌ ${__("Omborda ham bu mahsulotdan YO'Q")}</span>
					</div>`;
				}
				const max = Math.min(o.bosh, it.kg);
				return `<div class="nv-ko-row">
					<span>${frappe.utils.escape_html(it.item_name)}
						<span class="nv-mini text-muted">(${__("zakazda")} ${fmt(it.kg)} kg)</span></span>
					<span class="nv-yashil">${__("omborda bo'sh")}: <b>${fmt(o.bosh)} kg</b></span>
					<span class="nv-ko-inp">
						<input type="number" class="nv-fakt nv-ko-ombordan" data-item="${frappe.utils.escape_html(it.item_code)}"
							min="0" max="${max}" step="any" placeholder="0"
							value="${it.ombordan_kg > 0 ? it.ombordan_kg : ""}"> kg
					</span>
				</div>`;
			})
			.join("");
		const warnHtml =
			d.yetmaydi > 0.4
				? `<div class="nv-ko-warn">
						⚠ ${__("Kunlik limitga")} <b>${fmt(d.yetmaydi)} kg</b> ${__("sig'mayapti")}
						(${qisqaSana(d.kutilgan_kun)}: ${fmt(d.kutilgan_band)} / ${fmt(d.quvvat)} kg ${__("band")}).
						${__("Xohlasangiz, yetmagan qismini OMBORDAN ishlatishingiz mumkin")}:
					</div>`
				: `<div class="nv-mini text-muted" style="margin-bottom:4px">
						📦 ${__("Xohlasangiz, mahsulotni ombordan ham ishlatishingiz mumkin (band qilinadi)")}:
					</div>`;
		const omborHtml = itemRows
			? `${warnHtml}
				<div class="nv-ko-rows">${itemRows}</div>
				<button class="btn btn-xs btn-default nv-ko-recalc">♻ ${__("Ombor bilan qayta hisoblash")}</button>`
			: "";

		const dlg = new frappe.ui.Dialog({
			title: __("Zakaz ko'rigi") + " — " + g.mijoz,
			size: "large",
			fields: [{ fieldname: "html", fieldtype: "HTML" }],
			primary_action_label: __("✅ Tasdiqlash (zakaz urish)"),
			primary_action() {
				const items = g.items.map((it) => ({ ...it }));
				dlg.$wrapper.find(".nv-ko-ombordan").each(function () {
					const code = $(this).data("item");
					const kg = parseFloat($(this).val()) || 0;
					const row = items.find((x) => x.item_code === code);
					if (row) row.ombordan_kg = kg; // 0 = ombordan olinmaydi
				});
				dlg.hide();
				zakazUr(g, items, $card);
			},
		});
		const oldindan =
			g.kerak_kun && g.kerak_kun > frappe.datetime.get_today()
				? `<div class="nv-ko-reja nv-kok">🗓 ${__("Oldindan zakaz — so'ralgan kun")}: <b>${sanaLabel(g.kerak_kun)}</b></div>`
				: "";
		dlg.fields_dict.html.$wrapper.html(`
			<div class="nv-ko">
				<div class="nv-ko-jami">
					${__("Jami")}: <b>${fmt(d.jami_kg)} kg</b>
					${d.ombordan_kg > 0 ? ` · 📦 ${__("ombordan")}: <b>${fmt(d.ombordan_kg)} kg</b> · ${__("ishlab chiqariladi")}: <b>${fmt(d.ishlab_kg)} kg</b>` : ""}
				</div>
				${oldindan}
				<div class="nv-ko-reja">📅 ${__("Reja")}: ${rejaHtml || __("(kg noma'lum — birinchi bo'sh kunga)")}</div>
				${omborHtml}
			</div>`);
		// ombor kiritilgach rejani qayta ko'rish
		dlg.$wrapper.find(".nv-ko-recalc").on("click", () => {
			const items = g.items.map((it) => ({ ...it }));
			dlg.$wrapper.find(".nv-ko-ombordan").each(function () {
				const code = $(this).data("item");
				const kg = parseFloat($(this).val()) || 0;
				const row = items.find((x) => x.item_code === code);
				if (row) row.ombordan_kg = kg; // 0 = ombordan olinmaydi
			});
			dlg.hide();
			frappe
				.call({
					method: "pokiza.api.navbat.zakaz_korish",
					args: { items: items, kerak_kun: g.kerak_kun },
					freeze: true,
				})
				.then((r) =>
					korikDialog(
						{ mijoz: g.mijoz, items: items, kerak_kun: g.kerak_kun },
						r.message,
						$card
					)
				);
		});
		dlg.show();
	}

	function zakazUr(g, items, $card) {
		frappe
			.call({
				method: "pokiza.api.navbat.zakaz_yarat",
				args: {
					mijoz: g.mijoz,
					items: items,
					kerak_kun: g.kerak_kun,
					mashina_vaqti: $card.find(".nv-zk-slot").val(),
					mashina_izoh: $card.find(".nv-zk-slot-izoh").val(),
					izoh: $card.find(".nv-zk-izoh").val(),
				},
				freeze: true,
				freeze_message: __("Zakaz urilmoqda..."),
			})
			.then((r) => {
				const m = r.message || {};
				const reja = (m.taqsimot || [])
					.map((t) => `${qisqaSana(t.sana)} — ${fmt(t.kg)} kg`)
					.join(" · ");
				frappe.msgprint({
					title: __("Zakaz urildi"),
					message: `
						<a href="/app/sales-order/${m.so}"><b>${m.so}</b></a> · ${fmt(m.jami_kg)} kg
						${m.ombordan_kg > 0 ? `<br>📦 ${__("Ombordan band qilindi")}: <b>${fmt(m.ombordan_kg)} kg</b>` : ""}
						${reja ? `<br>📅 ${__("Reja")}: ${reja}` : ""}`,
					indicator: "green",
				});
				zakazForm(); // formani tozalash
				if (m.kun) {
					state.gBoshi = frappe.datetime.get_today();
					tanla(m.kun);
				} else {
					yukla();
				}
				tabOch("ishlab");
			});
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
			/* --- zakaz urish formasi --- */
			.nv-zk { max-width: 860px; }
			.nv-zk-title { font-size: 14px; font-weight: 700; margin-bottom: 10px; }
			.nv-zk-top { display: flex; gap: 14px; align-items: flex-end;
				flex-wrap: wrap; margin-bottom: 8px; }
			.nv-zk-mijoz { width: 340px; max-width: 100%; }
			.nv-zk-mijoz .frappe-control, .nv-zk-mijoz .form-group { margin-bottom: 0 !important; }
			.nv-zk-kun-wrap { width: 190px; }
			.nv-zk-items-head { display: grid; grid-template-columns: 1fr 100px 40px 160px 110px 30px;
				gap: 8px; font-size: 10.5px; color: var(--text-muted); text-transform: uppercase; }
			.nv-zk-row { display: grid; grid-template-columns: 1fr 100px 40px 160px 110px 30px;
				gap: 8px; align-items: center; margin-bottom: 4px; }
			.nv-zk-ombor { font-size: 12px; }
			.nv-zk-omb { text-align: right; }
			.nv-zk-omb:disabled { opacity: .45; }
			@media (max-width: 700px) {
				.nv-zk-items-head { display: none; }
				.nv-zk-row { grid-template-columns: 1fr 90px 40px; }
				.nv-zk-ombor, .nv-zk-omb { grid-column: 1 / -1; }
			}
			.nv-zk-item .frappe-control { margin-bottom: 0 !important; }
			.nv-zk-item .form-group { margin-bottom: 0 !important; }
			.nv-zk-qty { text-align: right; }
			.nv-zk-uom { font-size: 12px; }
			.nv-zk-add { margin: 6px 0 12px; }
			.nv-zk-extra { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 12px; }
			@media (max-width: 700px) { .nv-zk-extra { grid-template-columns: 1fr; } }
			.nv-zk-slot-row { display: flex; gap: 8px; }
			/* --- ko'rik oynasi --- */
			.nv-ko-jami { font-size: 14px; margin-bottom: 6px; }
			.nv-ko-reja { font-size: 12.5px; margin-bottom: 10px; }
			.nv-ko-warn { background: rgba(230,126,34,.1); border: 1px solid #e67e22;
				border-radius: 8px; padding: 8px 10px; font-size: 12.5px; margin-bottom: 8px; }
			.nv-ko-row { display: flex; gap: 10px; align-items: center; font-size: 12.5px;
				padding: 4px 0; border-bottom: 1px dashed var(--border-color); flex-wrap: wrap; }
			.nv-ko-row > span:first-child { flex: 1; min-width: 200px; }
			.nv-ko-inp { white-space: nowrap; }
			.nv-ko-recalc { margin-top: 8px; }
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
