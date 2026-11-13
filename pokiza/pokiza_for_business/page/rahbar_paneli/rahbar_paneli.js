// Rahbar paneli — Telegram hisobotlari bilan bir xil KPI dvigateli (pokiza.nazorat.panel)
const RP_API = "pokiza.nazorat.panel.";
// dataviz status palitrasi: holat doim shakl + so'z bilan, faqat rang emas
const RP_HOLAT = {
	yashil: { color: "#0ca30c", icon: "●", label: __("Yaxshi") },
	sariq: { color: "#fab219", icon: "▲", label: __("Diqqat") },
	qizil: { color: "#d03b3b", icon: "■", label: __("Yomon") },
};
const RP_SERIES = "#2a78d6";
const RP_TURLAR = {
	oylik: {
		label: __("Oylik"),
		qadam: (s, n) => frappe.datetime.add_months(s, n),
		tez: [["joriy_oy", __("Joriy oy")], ["otgan_oy", __("O'tgan oy")]],
	},
	haftalik: {
		label: __("Haftalik"),
		qadam: (s, n) => frappe.datetime.add_days(s, 7 * n),
		tez: [["joriy_hafta", __("Joriy hafta")], ["otgan_hafta", __("O'tgan hafta")]],
	},
	kunlik: {
		label: __("Kunlik"),
		qadam: (s, n) => frappe.datetime.add_days(s, n),
		tez: [["bugun", __("Bugun")], ["kecha", __("Kecha")]],
	},
};
// TZ bo'limlari (oylik hisobot)
const RP_GURUH = {
	A: __("Strategik fokus"),
	B: __("Mijozlar va sotish"),
	C: __("Moliya va to'lovlar"),
	D: __("Vazifalar va jamoa"),
};

frappe.pages["rahbar-paneli"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Rahbar paneli"), single_column: true });
	wrapper.rahbar_paneli = new RahbarPaneli(page);
};

function rp_num(v, d = 0) {
	if (v === null || v === undefined || isNaN(v)) return "—";
	return Number(v).toLocaleString("ru-RU", { minimumFractionDigits: d, maximumFractionDigits: d });
}

function rp_qiymat(v, birlik) {
	if (v === null || v === undefined) return "—";
	const a = Math.abs(v);
	if (birlik === "so'm") {
		if (a >= 1e9) return rp_num(v / 1e9, 2) + " mlrd";
		if (a >= 1e6) return rp_num(v / 1e6, 1) + " mln";
		return rp_num(v) + " so'm";
	}
	if (birlik === "$") return "$" + rp_num(v);
	if (birlik === "%") return rp_num(v, a > 0 && a < 1 ? 2 : 1) + "%";
	if (birlik === "tonna") return rp_num(v, 1) + " t";
	if (birlik === "so'm/kg") return rp_num(v) + " so'm/kg";
	return rp_num(v, Number.isInteger(v) ? 0 : 1) + (birlik ? " " + birlik : "");
}

// Ichki kalitlar -> odam tushunadigan ustun nomi. [nom, format]: som | kg | foiz | son | sana | matn
const RP_USTUN = {
	mijoz: [__("Mijoz")], nomi: [__("Nomi")], brak_summa: [__("Brak tannarxi"), "som"], nomi: [__("Nomi")], brak_summa: [__("Brak tannarxi"), "som"], mahsulot: [__("Mahsulot")], norma: [__("Mahsulot (norma)")], kategoriya: [__("Kategoriya")],
	postavshik: [__("Postavshik")], kim: [__("Kim")], xodim: [__("Xodim")], vazifa: [__("Vazifa")], hisob: [__("Hisob")],
	turi: [__("Turi")], holat: [__("Holat")], sabab: [__("Sabab")], izoh: [__("Izoh")], shart: [__("To'lov sharti")],
	hujjat: [__("Hujjat")], valyuta: [__("Valyuta")], birlik: [__("Birlik")], oyna: [__("Davr oynasi")],
	solishtirildi: [__("Solishtirilgan davr")], sana: [__("Sana"), "sana"], muddat: [__("Muddat"), "sana"],
	oxirgi_xarid: [__("Oxirgi xarid"), "sana"], kurs_sanasi: [__("Kurs sanasi"), "sana"],
	summa: [__("Summa"), "som"], savdo: [__("Savdo"), "som"], jami_savdo: [__("Jami savdo"), "som"],
	kg_savdo: [__("Kg'li mahsulot savdosi"), "som"], donali_savdo_kirmagan: [__("Donali savdo (hisobga kirmagan)"), "som"],
	tannarx: [__("Tannarx"), "som"], tannarx_xomashyo: [__("Tannarx (xomashyo)"), "som"], foyda: [__("Foyda"), "som"],
	yalpi_foyda: [__("Yalpi foyda"), "som"], sof_foyda: [__("Sof foyda"), "som"], sof_foyda_som: [__("Sof foyda (so'm)"), "som"],
	daromad_gl: [__("Daromad (buxgalteriya)"), "som"], xarajatlar: [__("Xarajatlar"), "som"], jami_xarajat: [__("Jami xarajat"), "som"],
	ombor_tuzatish: [__("Ombor tuzatishlari"), "som"], boshqa: [__("Boshqa (kurs farqi va h.k.)"), "som"],
	bonus: [__("Bonus"), "som"], qarz: [__("Qarz"), "som"], ruxsat_qarz: [__("Ruxsat etilgan qarz"), "som"],
	oshgan: [__("Oshgan qism"), "som"], olingan: [__("Olingan tovar"), "som"], olingan_M: [__("O'tgan oy olgan tovari"), "som"],
	yopilgan: [__("Yopilgan"), "som"], ostatka: [__("Ostatka"), "som"], jami_ostatka: [__("Jami ostatka"), "som"],
	farq: [__("Farq"), "som"], hozir: [__("Shu davr"), "som"], oldin: [__("Oldingi davr"), "som"],
	oy_boshidan: [__("Oy boshidan"), "som"], oylik_reja: [__("Oylik reja"), "som"], yechilgan: [__("Dividend olingan"), "som"],
	oborotda_qolgan: [__("Oborotda qolgan"), "som"], buzilgan_summa: [__("Shart buzilgan summa"), "som"],
	kelishuvsiz_qarz: [__("Kelishuvsiz qarz"), "som"], muddati_kelmagan_tolashi_kerak: [__("Hali muddati kelmagan qarz"), "som"],
	vozvrat_summa: [__("Vozvrat summasi"), "som"], narx_kg: [__("1 kg narxi"), "som"], kurs: [__("Dollar kursi"), "som"],
	kg: [__("Hajm, kg"), "kg"], brak_kg: [__("Brak, kg"), "kg"], vozvrat_kg: [__("Vozvrat, kg"), "kg"],
	ishlab_chiqarilgan_kg: [__("Ishlab chiqarilgan, kg"), "kg"], kunlik_ortacha_kg: [__("Kunlik o'rtacha, kg"), "kg"],
	kunlik_quvvat_kg: [__("Kunlik to'liq quvvat, kg"), "kg"], miqdor: [__("Miqdor"), "kg"],
	"ulush_%": [__("Ulushi"), "foiz"], "kg_ulush_%": [__("Hajmdagi ulushi"), "foiz"], "savdo_ulush_%": [__("Savdodagi ulushi"), "foiz"],
	"kumulativ_%": [__("Yig'ma ulush"), "foiz"], "rentabellik_%": [__("Rentabellik"), "foiz"], "yalpi_marja_%": [__("Yalpi marja"), "foiz"],
	"ozgarish_%": [__("O'zgarish"), "foiz"], "yopish_%": [__("Yopilgan qismi"), "foiz"], "savdoga_%": [__("Savdoga nisbatan"), "foiz"],
	"tannarx_savdoga_%": [__("Tannarx savdoga nisbatan"), "foiz"], "foydadan_%": [__("Foydaga nisbatan"), "foiz"],
	"vozvrat_kg_%": [__("Vozvrat ulushi"), "foiz"], "bajarilish_%": [__("Bajarilishi"), "foiz"],
	"oylik_bajarilish_%": [__("Oylik reja bajarilishi"), "foiz"], rejadan_farq_pp: [__("Rejadan farq (foiz punkt)"), "pp"],
	pe: [__("Ishlab chiqarish hujjatlari")], faktura: [__("Fakturalar")], faktura_soni: [__("Fakturalar soni")],
	mijozlar: [__("Mijozlar")], mijozlar_soni: [__("Mijozlar soni")], ishlangan_kunlar: [__("Ishlangan kunlar")],
	kalendar_ish_kunlari: [__("Ish kunlari (kalendar)")], jim_kun: [__("Necha kun jim")], ortacha_oraliq_kun: [__("Odatiy oraliq, kun")],
	chegara_kun: [__("Jimlik chegarasi, kun")], faol_mijozlar_90_kun: [__("Faol mijozlar (90 kun)")],
	tushgan: [__("Savdosi tushgan")], osgan: [__("Savdosi o'sgan")], yangi: [__("Yangi mijozlar")], yoqolgan: [__("Yo'qolgan mijozlar")],
	buzgan: [__("Shartni buzganlar")], kelishuvli_mijozlar: [__("Kelishuvli mijozlar")], kelishuvsiz_qarzdorlar: [__("Kelishuvsiz qarzdorlar")],
	kam_yopganlar: [__("Kam yopganlar")], ortiqcha_yopganlar: [__("Ortiqcha yopganlar")], jami_mahsulot: [__("Jami mahsulot")],
	hujjatlar: [__("Hujjatlar")], yozuvlar: [__("Yozuvlar")], jami: [__("Jami")], bajarilgan: [__("Bajarilgan")],
	bajarilmagan: [__("Bajarilmagan")], ochiq: [__("Ochiq")], berilgan: [__("Berilgan")], rad_etilgan: [__("Rad etilgan")],
	muddati_otgan: [__("Muddati o'tgan")], nazoratdagi: [__("Nazoratdagi")], yopmaganlar: [__("Yopmaganlar")],
	kim_boyicha: [__("Kim bo'yicha"), "som"], valyuta_boyicha: [__("Valyuta bo'yicha")], belgilanmagan: [__("Turi belgilanmagan")],
};

function rp_ustun(k) {
	if (RP_USTUN[k]) return RP_USTUN[k][0];
	const t = k.replace(/_%$/, " %").replace(/_/g, " ");
	return t.charAt(0).toUpperCase() + t.slice(1);
}

function rp_format(k, v) {
	if (v === null || v === undefined || v === "") return "—";
	const f = (RP_USTUN[k] || [])[1] || (/_%$/.test(k) ? "foiz" : null);
	if (f === "sana" && /^\d{4}-\d{2}-\d{2}/.test(v)) return frappe.datetime.str_to_user(String(v).slice(0, 10));
	if (typeof v !== "number") return v;
	if (f === "foiz") return rp_num(v, 1) + "%";
	if (f === "pp") return (v > 0 ? "+" : "") + rp_num(v, 2) + " pp";
	if (f === "kg") return rp_num(v, v >= 100 ? 0 : 1);
	if (f === "som") return rp_num(v, Math.abs(v) < 100 && !Number.isInteger(v) ? 2 : 0);
	return rp_num(v, Number.isInteger(v) ? 0 : 1);
}

const RP_OY = ["yan", "fev", "mar", "apr", "may", "iyn", "iyl", "avg", "sen", "okt", "noy", "dek"];
function rp_yorliq(t) {
	const k = String(t.davr || "");
	let m;
	if ((m = k.match(/^(\d{4})-(\d{2})$/))) return `${RP_OY[+m[2] - 1]} ${m[1].slice(2)}`;
	if ((m = k.match(/^(\d{4})-(\d{2})-(\d{2})$/))) return `${+m[3]} ${RP_OY[+m[2] - 1]}`;
	return k.replace(/^\d{4}-W/, "H");
}
const esc = (v) => frappe.utils.escape_html(String(v ?? ""));

class RahbarPaneli {
	constructor(page) {
		this.page = page;
		this.turi = "oylik";
		this.sana = null; // sana tanlagichdan
		this.davr = null; // tezkor tugma kaliti (joriy_oy ...)
		this.$body = $(`<div class="rp-root"></div>`).appendTo(page.main);
		this.page.set_secondary_action(__("Yangilash"), () => this.load(), "refresh");
		this.render_controls();
		this.$head = $(`<div class="rp-head"></div>`).appendTo(this.$body);
		this.$grid = $(`<div class="rp-content"></div>`).appendTo(this.$body);
		this.load();
	}

	// ---------- boshqaruv ----------
	render_controls() {
		const $c = $(`<div class="rp-controls">
			<div class="rp-seg" role="tablist" aria-label="${__("Hisobot turi")}"></div>
			<div class="rp-picker">
				<button class="btn btn-default btn-sm rp-prev" aria-label="${__("Oldingi davr")}">${frappe.utils.icon("left", "sm")}</button>
				<div class="rp-date"></div>
				<button class="btn btn-default btn-sm rp-next" aria-label="${__("Keyingi davr")}">${frappe.utils.icon("right", "sm")}</button>
			</div>
			<div class="rp-quick"></div>
		</div>`).appendTo(this.$body);
		this.$c = $c;

		Object.entries(RP_TURLAR).forEach(([k, t]) => {
			$(`<button class="rp-seg-btn" role="tab" data-turi="${k}">${t.label}</button>`)
				.on("click", () => {
					if (this.turi === k) return;
					this.turi = k;
					this.sana = null;
					this.davr = null;
					this.load();
				})
				.appendTo($c.find(".rp-seg"));
		});

		this.date = frappe.ui.form.make_control({
			parent: $c.find(".rp-date"),
			df: {
				fieldtype: "Date",
				fieldname: "rp_sana",
				placeholder: __("Sana tanlang"),
				change: () => {
					if (this._jim) return;
					const v = this.date.get_value();
					if (!v || v === this.sana) return;
					this.sana = v;
					this.davr = null;
					this.load();
				},
			},
			render_input: true,
		});
		this.date.refresh();
		this.date.$wrapper.find(".control-label, .help-box").remove();
		this.date.$wrapper.css("margin", 0);
		this.date.$input.attr("aria-label", __("Davr sanasi")).addClass("rp-date-input");
		// input ichida bitta sana emas, butun davr oralig'i ko'rinadi (kalendar o'sha input'da ochiladi)
		this.$oraliq = $(`<div class="rp-date-label" aria-hidden="true"></div>`).appendTo(this.date.$input.parent());

		$c.find(".rp-prev").on("click", () => this.siljit(-1));
		$c.find(".rp-next").on("click", () => this.siljit(1));
	}

	sync_controls() {
		const t = RP_TURLAR[this.turi];
		this.$c.find(".rp-seg-btn").each((_, b) => {
			const on = $(b).data("turi") === this.turi;
			$(b).toggleClass("active", on).attr("aria-selected", on);
		});
		const $q = this.$c.find(".rp-quick").empty();
		t.tez.forEach(([k, label]) => {
			$(`<button class="rp-chip">${label}</button>`)
				.toggleClass("active", this.davr === k)
				.on("click", () => {
					this.davr = k;
					this.sana = null;
					this.load();
				})
				.appendTo($q);
		});
		if (this.data) {
			const d = this.data.davr;
			this._jim = true;
			this.date.set_value(this.sana || d.from).then(() => (this._jim = false));
			const u = (x) => frappe.datetime.str_to_user(x);
			this.$oraliq.text(d.from === d.to ? u(d.from) : `${u(d.from)} – ${u(d.to)}`);
			const keyingi = t.qadam(d.from, 1);
			this.$c.find(".rp-next").prop("disabled", keyingi > this.data.bugun);
		}
	}

	siljit(n) {
		if (!this.data) return;
		this.sana = RP_TURLAR[this.turi].qadam(this.data.davr.from, n);
		this.davr = null;
		this.load();
	}

	args() {
		return { turi: this.turi, sana: this.sana, davr: this.sana ? null : this.davr };
	}

	// ---------- ma'lumot ----------
	load() {
		this.sync_controls();
		this.$grid.html(this.skeleton());
		frappe
			.call({ method: RP_API + "get_panel", args: this.args() })
			.then(({ message: r }) => {
				this.data = r;
				this.sync_controls();
				this.render_head(r);
				this.render_grid(r.korsatkichlar);
			})
			.catch(() => this.$grid.html(`<div class="rp-empty">${__("Ma'lumot olinmadi. Sanani tekshirib, qayta urinib ko'ring.")}</div>`));
	}

	skeleton() {
		return `<div class="rp-hero-grid">${'<div class="rp-skel"></div>'.repeat(4)}</div>`;
	}

	render_head(r) {
		const son = { yashil: 0, sariq: 0, qizil: 0 };
		r.korsatkichlar.forEach((m) => son[m.rang] !== undefined && son[m.rang]++);
		const tally = Object.entries(RP_HOLAT)
			.map(([k, h]) => `<span class="rp-tally-i"><span style="color:${h.color}" aria-hidden="true">${h.icon}</span>
				<b>${son[k]}</b> ${h.label.toLowerCase()}</span>`)
			.join("");
		const KUN = [__("Yakshanba"), __("Dushanba"), __("Seshanba"), __("Chorshanba"), __("Payshanba"), __("Juma"), __("Shanba")];
		const oraliq = r.davr.turi === "kun"
			? KUN[frappe.datetime.str_to_obj(r.davr.from).getDay()]
			: r.davr.turi === "hafta"
				? __("Dushanba – yakshanba")
				: `${frappe.datetime.str_to_user(r.davr.from)} – ${frappe.datetime.str_to_user(r.davr.to)}`;
		this.$head.html(`
			<div class="rp-title">
				<h2>${esc(r.davr.nom)}</h2>
				<div class="rp-subtitle">${oraliq}${r.davr.qisman ? ` · <span class="rp-qisman">${__("davr tugamagan, reja shu kungacha")}</span>` : ""}
					· ${__("Doira")}: ${esc(r.bolim)}</div>
			</div>
			<div class="rp-tally" aria-label="${__("Holatlar")}">${tally}</div>`);
	}

	render_grid(rows) {
		this.$grid.empty();
		if (!rows.length) {
			this.$grid.html(`<div class="rp-empty">${__("Bu doirada ko'rsatkich yo'q")}</div>`);
			return;
		}
		if (this.turi !== "oylik") {
			const $g = $(`<div class="rp-hero-grid"></div>`).appendTo(this.$grid);
			rows.forEach((m) => $g.append(this.tile(m)));
			return;
		}
		const guruh = {};
		rows.forEach((m) => (guruh[m.code[0]] = guruh[m.code[0]] || []).push(m));
		Object.entries(RP_GURUH).forEach(([k, nom]) => {
			if (!guruh[k]) return;
			const $s = $(`<section class="rp-section"><h3 class="rp-section-h">${nom}</h3></section>`).appendTo(this.$grid);
			if (k === "A") {
				const $g = $(`<div class="rp-hero-grid"></div>`).appendTo($s);
				guruh[k].forEach((m) => $g.append(this.tile(m)));
			} else {
				const $l = $(`<div class="rp-list" role="list"></div>`).appendTo($s);
				guruh[k].forEach((m) => $l.append(this.row(m)));
			}
		});
	}

	// ---------- kartalar ----------
	holat(m) {
		const h = RP_HOLAT[m.rang];
		if (m.xato) return `<span class="rp-holat rp-muted">${__("Xato")}</span>`;
		return h
			? `<span class="rp-holat"><span style="color:${h.color}" aria-hidden="true">${h.icon}</span> ${h.label}</span>`
			: `<span class="rp-holat"></span>`;
	}

	qiymat(m) {
		if (m.xato) return "—";
		return m.mavjud === false ? "—" : rp_qiymat(m.fakt, m.birlik);
	}

	rail(m) {
		const b = m["bajarilish_%"];
		if (b === null || b === undefined) return "";
		const h = RP_HOLAT[m.rang];
		const fill = Math.max(0, Math.min(b, 120)) / 1.2;
		return `<div class="rp-rail" role="img" aria-label="${__("Reja bajarilishi")} ${rp_num(b, 1)}%">
			<div class="rp-rail-fill" style="width:${fill}%;background:${h ? h.color : RP_SERIES}"></div>
			<div class="rp-rail-tick" title="${__("Reja")} 100%"></div>
		</div>`;
	}

	reja_matn(m) {
		if (m.reja === undefined || m.reja === null) return "";
		const b = m["bajarilish_%"];
		return `${__("Reja")} ${rp_qiymat(m.reja, m.birlik)}${b != null ? ` · <b>${rp_num(b, 1)}%</b>` : ""}`;
	}

	ozgarish(m) {
		const o = m["ozgarish_%"];
		if (o === null || o === undefined || !m.oldingi) return "";
		const strelka = o > 0 ? "↑" : o < 0 ? "↓" : "→";
		return `<span class="rp-ozg">${strelka} ${rp_num(Math.abs(o), 1)}%</span> <span class="rp-muted">${__("vs")} ${esc(m.oldingi.davr)}</span>`;
	}

	edge(m) {
		const h = RP_HOLAT[m.rang];
		return h ? h.color : "var(--border-color)";
	}

	tile(m) {
		const $t = $(`<button class="rp-tile" type="button" style="--rp-edge:${this.edge(m)}">
			<div class="rp-tile-top"><span class="rp-name">${esc(m.nom)}</span>${this.holat(m)}</div>
			<div class="rp-value">${this.qiymat(m)}</div>
			${this.rail(m)}
			<div class="rp-sub">${this.reja_matn(m)}</div>
			<div class="rp-sub">${this.ozgarish(m)}</div>
		</button>`);
		$t.on("click", () => this.detail(m.code));
		return $t;
	}

	row(m) {
		const $r = $(`<button class="rp-row" type="button" role="listitem" style="--rp-edge:${this.edge(m)}">
			<span class="rp-row-name">${esc(m.nom)}</span>
			<span class="rp-row-val">${this.qiymat(m)}</span>
			<span class="rp-row-meta">${this.reja_matn(m) || this.ozgarish(m)}</span>
			${this.holat(m)}
		</button>`);
		$r.on("click", () => this.detail(m.code));
		return $r;
	}

	// ---------- batafsil ----------
	detail(code) {
		frappe
			.call({ method: RP_API + "get_detail", args: { code, ...this.args() }, freeze: true })
			.then(({ message: m }) => this.show_detail(m));
	}

	show_detail(m) {
		const d = new frappe.ui.Dialog({ title: m.nom, size: "extra-large" });
		const $b = $(d.body).addClass("rp-detail");
		$b.append(`<div class="rp-hero" style="--rp-edge:${this.edge(m)}">
			<div class="rp-hero-main">
				<div class="rp-subtitle rp-cap">${esc(m.davr.nom)}</div>
				<div class="rp-value rp-value-xl">${rp_qiymat(m.fakt, m.birlik)}</div>
				${this.rail(m)}
				<div class="rp-sub">${this.reja_matn(m)}</div>
			</div>
			<div class="rp-hero-side">
				${this.holat(m)}
				${m.oldingi ? `<div class="rp-sub">${__("Oldingi")}: <b>${rp_qiymat(m.oldingi.fakt, m.birlik)}</b> <span class="rp-muted">(${esc(m.oldingi.davr)})</span></div>` : ""}
				<div class="rp-sub">${this.ozgarish(m)}</div>
			</div>
		</div>`);
		(m.izoh || []).forEach((t) => $b.append(`<div class="rp-izoh">⚠️ ${esc(t)}</div>`));
		let trend = m.trend || [];
		const birinchi = trend.findIndex((t) => t.fakt);
		trend = birinchi > 0 ? trend.slice(birinchi) : trend;
		if (trend.length) {
			$b.append(`<h6 class="rp-h">${__("Trend")}</h6>`);
			const $ch = $(`<div class="rp-chart" role="img" aria-label="${__("Trend")}: ${esc(m.nom)}"></div>`).appendTo($b);
			setTimeout(() => {
				new frappe.Chart($ch[0], {
					type: "bar",
					height: 240,
					colors: [RP_SERIES],
					data: { labels: trend.map((t) => rp_yorliq(t)), datasets: [{ name: m.nom, values: trend.map((t) => t.fakt || 0) }] },
					barOptions: { spaceRatio: 0.4 },
					axisOptions: { xIsSeries: 1, shortenYAxisNumbers: 1 },
					tooltipOptions: { formatTooltipY: (v) => rp_qiymat(v, m.birlik) },
				});
			}, 50);
			$b.append(this.table([__("Davr"), m.nom], trend.map((t) => [t.nom, rp_qiymat(t.fakt, m.birlik)]), true));
		}
		if (m.qism) {
			const rows = [];
			Object.entries(m.qism).forEach(([k, v]) => {
				if (v && typeof v === "object") {
					Object.entries(v).forEach(([k2, v2]) => rows.push([`${rp_ustun(k)}: ${k2}`, rp_format(k, v2)]));
				} else rows.push([rp_ustun(k), rp_format(k, v)]);
			});
			if (rows.length) {
				$b.append(`<h6 class="rp-h">${__("Tarkibi")}</h6>`);
				$b.append(`<dl class="rp-kv">${rows.map(([a, b]) => `<div><dt>${esc(a)}</dt><dd>${esc(b)}</dd></div>`).join("")}</dl>`);
			}
		}
		if (m.tafsilot && m.tafsilot.length) {
			const cols = Object.keys(m.tafsilot[0]).filter((k) => k !== "rang");
			const rangli = m.tafsilot.some((r) => r.rang);
			$b.append(`<h6 class="rp-h">${__("Tafsilot")} <span class="rp-muted">(${m.tafsilot.length})</span></h6>`);
			const head = (rangli ? [""] : []).concat(cols.map(rp_ustun));
			const raqamli = (rangli ? [false] : []).concat(cols.map((c) => typeof m.tafsilot[0][c] === "number"));
			$b.append(this.table(head, m.tafsilot.map((r) => {
				const h = RP_HOLAT[r.rang];
				const bel = h ? { html: `<span style="color:${h.color}" title="${h.label}">${h.icon}</span>` } : "";
				return (rangli ? [bel] : []).concat(cols.map((c) => rp_format(c, r[c])));
			}), false, raqamli));
		}
		$b.append(`<div class="rp-muted small rp-manba">${__("Manba")}: ${esc(m.manba || "")}</div>`);
		d.show();
	}

	table(head, rows, collapsed, raqamli) {
		const cls = (i) => ((raqamli ? raqamli[i] : i > 0) ? "text-right" : "");
		const cell = (x) => (x && x.html ? x.html : esc(x));
		const html = `<div class="rp-table-wrap"><table class="table table-sm rp-table">
			<thead><tr>${head.map((x, i) => `<th class="${cls(i)}">${esc(x)}</th>`).join("")}</tr></thead>
			<tbody>${rows.map((r) => `<tr>${r.map((x, i) => `<td class="${cls(i)}">${cell(x)}</td>`).join("")}</tr>`).join("")}</tbody>
		</table></div>`;
		return collapsed ? `<details class="rp-details"><summary>${__("Jadval ko'rinishi")}</summary>${html}</details>` : html;
	}
}
