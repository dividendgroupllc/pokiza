// Pokiza AI — biznes ma'lumotlari bo'yicha chat (Claude)
const PAI_API = "pokiza.ai.api.";
const PAI_MAX_FILES = 5;
const PAI_ACCEPT = ".jpg,.jpeg,.png,.webp,.gif,.pdf,.xlsx,.xls,.csv,.ogg,.oga,.opus,.mp3,.m4a,.wav,.webm,.aac";
const PAI_VOICE_MAX_SEC = 300;

const PAI_EXAMPLES = [
	{ topic: "Sotuv", q: "Shu oy qancha sotdik? O'tgan oy bilan solishtir" },
	{ topic: "Qarzlar", q: "Eng ko'p qarzi bor 10 ta mijoz kim?" },
	{ topic: "Pul", q: "Kassa va bankda hozir qancha pul bor?" },
	{ topic: "Ishlab chiqarish", q: "Ertangi navbatda necha kg bor?" },
	{ topic: "Excel", q: "Oktyabr sotuvini mijozlar bo'yicha Excel qilib ber" },
	{ topic: "PDF", q: "Oktyabr oyi foyda-zarar hisobotini PDF qilib ber" },
];

const PAI_TOOL_LABELS = {
	run_report: "Hisobot",
	sql_query: "SQL so'rov",
	list_records: "Yozuvlar ro'yxati",
	get_record: "Hujjat",
	describe_doctype: "Jadval tuzilishi",
	search_doctypes: "Jadval qidiruvi",
	get_cash_balances: "Kassa qoldig'i",
	get_party_balances: "Qarzdorlik",
	get_production_queue: "Ishlab chiqarish navbati",
	get_scale_list: "Tarozi ro'yxati",
	get_defect_list: "Brak ro'yxati",
	create_file: "Fayl tayyorlash",
	show_dashboard: "Dashboard",
};

// dataviz reference palitrasi: kategoriyalar qat'iy tartibda (CVD tekshirilgan), light/dark alohida
const PAI_SERIES = {
	light: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"],
	dark: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
};

function pai_num(v, digits) {
	if (v === null || v === undefined || isNaN(v)) return "—";
	const d = digits ?? (Math.abs(v) < 100 && !Number.isInteger(v) ? 1 : 0);
	const [i, f] = Math.abs(v).toFixed(d).split(".");
	return (v < 0 ? "−" : "") + i.replace(/\B(?=(\d{3})+(?!\d))/g, "\u202f") + (f ? "," + f : "");
}

function pai_short(v) {
	const a = Math.abs(v);
	if (a >= 1e9) return pai_num(v / 1e9, 2) + " mlrd";
	if (a >= 1e6) return pai_num(v / 1e6, 1) + " mln";
	return pai_num(v);
}

const PAI_ICONS = {
	clip: '<path d="M21 11.5 12.6 19.9a5.5 5.5 0 0 1-7.8-7.8l8.5-8.5a3.7 3.7 0 0 1 5.2 5.2l-8.5 8.5a1.8 1.8 0 0 1-2.6-2.6l7.8-7.8"/>',
	mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
	send: '<path d="M12 19V5M5 12l7-7 7 7"/>',
	stop: '<rect x="7" y="7" width="10" height="10" rx="1.5" fill="currentColor" stroke="none"/>',
	copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h8"/>',
	download: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
	menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
	plus: '<path d="M12 5v14M5 12h14"/>',
	x: '<path d="M6 6l12 12M18 6 6 18"/>',
	down: '<path d="M12 5v14M5 12l7 7 7-7"/>',
	retry: '<path d="M4 12a8 8 0 1 0 2.3-5.7M4 4v5h5"/>',
	edit: '<path d="M4 20h4L19 9l-4-4L4 16v4z"/>',
	trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
	play: '<path d="M8 5v14l11-7z" fill="currentColor" stroke="none"/>',
	pause: '<rect x="7" y="5" width="3.5" height="14" rx="1" fill="currentColor" stroke="none"/><rect x="13.5" y="5" width="3.5" height="14" rx="1" fill="currentColor" stroke="none"/>',
};

function pai_icon(name, size = 18) {
	return `<svg class="pai-ico" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${PAI_ICONS[name]}</svg>`;
}

function pai_size(bytes) {
	if (!bytes) return "";
	if (bytes < 1024 * 1024) return Math.max(1, Math.round(bytes / 1024)) + " KB";
	return (bytes / 1024 / 1024).toFixed(1) + " MB";
}

function pai_ext(name) {
	return ((name || "").split(".").pop() || "").toLowerCase();
}

frappe.pages["pokiza-ai"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: "Pokiza AI", single_column: true });
	wrapper.pokiza_ai = new PokizaAI(page, wrapper);
};

frappe.pages["pokiza-ai"].on_page_show = function (wrapper) {
	if (wrapper.pokiza_ai) {
		wrapper.pokiza_ai.fit_height();
		wrapper.pokiza_ai.focus();
	}
};

class PokizaAI {
	constructor(page, wrapper) {
		this.page = page;
		this.wrapper = wrapper;
		this.suhbat = null;
		this.running = null; // {xabar, $el, text, thinking}
		this.attachments = []; // {id, file, status: uploading|ready|error, info, preview}
		this.last_user = null; // {text, files}
		this.lang = localStorage.getItem("pai_lang") || "uz-UZ";
		this.render();
		this.bind_realtime();
		this.load_list();
		this.show_empty();
	}

	// ---------- karkas ----------
	render() {
		$(this.wrapper).find(".page-head").addClass("pai-hide-head");
		$(this.page.body).html(`
			<div class="pai-root">
				<aside class="pai-side" aria-label="Suhbatlar">
					<button class="pai-new" type="button">${pai_icon("plus", 16)}<span>Yangi suhbat</span></button>
					<nav class="pai-list"></nav>
				</aside>
				<div class="pai-scrim"></div>
				<main class="pai-main">
					<header class="pai-top">
						<button class="pai-icon-btn pai-menu" type="button" aria-label="Suhbatlar ro'yxati" title="Suhbatlar ro'yxatini yashirish / ko'rsatish (Ctrl+Shift+S)">${pai_icon("menu")}</button>
						<div class="pai-top-title">Pokiza AI</div>
						<button class="pai-icon-btn pai-new-mobile" type="button" aria-label="Yangi suhbat">${pai_icon("plus")}</button>
					</header>
					<div class="pai-scroll"><div class="pai-thread"></div></div>
					<button class="pai-to-bottom hidden" type="button" aria-label="Pastga">${pai_icon("down", 16)}</button>
					<div class="pai-composer">
						<div class="pai-box">
							<div class="pai-chips"></div>
							<textarea rows="1" placeholder="Savol yozing yoki ovozli xabar yuboring…" aria-label="Savol"></textarea>
							<div class="pai-recorder hidden" aria-live="polite">
								<button class="pai-icon-btn pai-rec-cancel" type="button" aria-label="Bekor qilish" title="Bekor qilish (Esc)">${pai_icon("trash")}</button>
								<span class="pai-rec-dot"></span><span class="pai-rec-time">0:00</span>
								<div class="pai-rec-wave" aria-hidden="true"></div>
								<span class="pai-rec-hint">Tugatish va yuborish →</span>
								<button class="pai-send pai-rec-send" type="button" aria-label="Yozishni tugatib yuborish" title="Tugatish va yuborish (Enter)">${pai_icon("send")}</button>
							</div>
							<div class="pai-tools">
								<button class="pai-icon-btn pai-attach" type="button" title="Fayl biriktirish: rasm, PDF, Excel" aria-label="Fayl biriktirish">${pai_icon("clip")}</button>
								<input type="file" class="pai-file" multiple accept="${PAI_ACCEPT}" hidden>
								<span class="pai-spacer"></span>
								<button class="pai-icon-btn pai-mic" type="button" aria-label="Ovozli xabar yozish" title="Ovozli xabar">${pai_icon("mic")}</button>
								<button class="pai-send" type="button" aria-label="Yuborish" disabled>${pai_icon("send")}</button>
								<button class="pai-stop hidden" type="button" aria-label="To'xtatish">${pai_icon("stop")}</button>
							</div>
						</div>
						<div class="pai-hint">Raqamlar bazadan olinadi. Muhim qarordan oldin "Manba"ni tekshiring.</div>
					</div>
					<div class="pai-drop hidden"><div>Faylni shu yerga tashlang<small>Rasm, PDF, Excel yoki audio · ko'pi bilan ${PAI_MAX_FILES} ta</small></div></div>
				</main>
			</div>`);
		const $r = (this.$root = $(this.page.body).find(".pai-root"));
		this.$list = $r.find(".pai-list");
		this.$thread = $r.find(".pai-thread");
		this.$scroll = $r.find(".pai-scroll");
		this.$input = $r.find("textarea");
		this.$send = $r.find(".pai-tools .pai-send");
		this.$stop = $r.find(".pai-stop");
		this.$chips = $r.find(".pai-chips");
		this.$mic = $r.find(".pai-mic");
		this.$title = $r.find(".pai-top-title");

		$r.find(".pai-new, .pai-new-mobile").on("click", () => this.new_chat());
		$r.find(".pai-menu").on("click", () => this.toggle_side());
		this.set_collapsed(localStorage.getItem("pai_side_collapsed") === "1");
		$(document).on("keydown.pokiza_ai", (e) => {
			if (e.ctrlKey && e.shiftKey && (e.key === "S" || e.key === "s") && $r.is(":visible")) {
				e.preventDefault();
				this.toggle_side();
			}
		});
		$r.find(".pai-scrim").on("click", () => $r.removeClass("pai-side-open"));
		this.$send.on("click", () => this.send());
		this.$stop.on("click", () => this.stop());
		this.$input.on("keydown", (e) => {
			if (e.key === "Enter" && !e.shiftKey && !e.originalEvent.isComposing) {
				e.preventDefault();
				this.send();
			}
		});
		this.$input.on("input", () => {
			this.autosize();
			this.update_send();
		});
		this.$input.on("paste", (e) => {
			const files = [...(e.originalEvent.clipboardData?.files || [])];
			if (files.length) {
				e.preventDefault();
				this.add_files(files);
			}
		});

		const $file = $r.find(".pai-file");
		$r.find(".pai-attach").on("click", () => $file.trigger("click"));
		$file.on("change", (e) => {
			this.add_files([...e.target.files]);
			e.target.value = "";
		});
		this.bind_drop();
		this.bind_voice();

		this.$scroll.on("scroll", () => {
			const el = this.$scroll.get(0);
			const far = el.scrollHeight - el.scrollTop - el.clientHeight > 400;
			$r.find(".pai-to-bottom").toggleClass("hidden", !far);
		});
		$r.find(".pai-to-bottom").on("click", () => this.scroll_bottom(true, true));

		this.fit_height();
		$(window).on("resize.pokiza_ai", frappe.utils.debounce(() => this.fit_height(), 100));
	}

	is_mobile() {
		return window.matchMedia("(max-width: 860px)").matches;
	}

	toggle_side() {
		if (this.is_mobile()) this.$root.toggleClass("pai-side-open");
		else this.set_collapsed(!this.$root.hasClass("pai-collapsed"));
	}

	set_collapsed(collapsed) {
		this.$root.toggleClass("pai-collapsed", collapsed);
		this.$root.find(".pai-side").attr("aria-hidden", collapsed && !this.is_mobile() ? "true" : null);
		this.$root.find(".pai-menu").attr("aria-expanded", String(!collapsed));
		localStorage.setItem("pai_side_collapsed", collapsed ? "1" : "0");
	}

	fit_height() {
		const el = this.$root && this.$root.get(0);
		if (!el || !el.offsetParent) return;
		const top = el.getBoundingClientRect().top + window.scrollY;
		el.style.height = Math.max(460, window.innerHeight - top - 16) + "px";
	}

	focus() {
		if (this.$input && window.matchMedia("(pointer: fine)").matches) this.$input.trigger("focus");
	}

	autosize() {
		const el = this.$input.get(0);
		el.style.height = "auto";
		el.style.height = Math.min(el.scrollHeight, 240) + "px";
	}

	update_send() {
		const has = (this.$input.val() || "").trim() || this.attachments.some((a) => a.status === "ready");
		const uploading = this.attachments.some((a) => a.status === "uploading");
		this.$send.prop("disabled", !has || uploading || !!this.running);
	}

	// ---------- suhbatlar ro'yxati ----------
	async load_list() {
		const r = await frappe.call({ method: PAI_API + "list_conversations" });
		const rows = r.message || [];
		this.$list.empty();
		if (!rows.length) {
			this.$list.html(`<div class="pai-list-empty">Savollaringiz shu yerda saqlanadi</div>`);
			return;
		}
		let group = null;
		rows.forEach((row) => {
			const g = this.date_group(row.last_message_at || row.modified);
			if (g !== group) {
				group = g;
				this.$list.append(`<div class="pai-list-group">${g}</div>`);
			}
			const $item = $(`
				<div class="pai-item ${row.name === this.suhbat ? "active" : ""}" data-name="${row.name}" tabindex="0" role="button">
					<span class="pai-item-title"></span>
					<span class="pai-item-actions">
						<button type="button" class="pai-rename" title="Nomini o'zgartirish" aria-label="Nomini o'zgartirish">${pai_icon("edit", 14)}</button>
						<button type="button" class="pai-delete" title="O'chirish" aria-label="O'chirish">${pai_icon("trash", 14)}</button>
					</span>
				</div>`);
			$item.find(".pai-item-title").text(row.title || "Suhbat");
			$item.toggleClass("busy", row.status === "Ishlayapti");
			$item.on("click", () => this.open(row.name));
			$item.on("keydown", (e) => {
				if (e.key === "Enter" && e.target === $item.get(0)) this.open(row.name);
			});
			$item.find(".pai-rename").on("click", (e) => {
				e.stopPropagation();
				this.rename(row);
			});
			$item.find(".pai-delete").on("click", (e) => {
				e.stopPropagation();
				this.remove(row);
			});
			this.$list.append($item);
		});
	}

	date_group(dt) {
		const days = frappe.datetime.get_day_diff(frappe.datetime.now_date(), (dt || "").slice(0, 10));
		if (days <= 0) return "Bugun";
		if (days === 1) return "Kecha";
		if (days <= 7) return "Oxirgi 7 kun";
		if (days <= 30) return "Oxirgi 30 kun";
		return "Avvalroq";
	}

	rename(row) {
		frappe.prompt(
			{ fieldname: "title", fieldtype: "Data", label: "Sarlavha", default: row.title, reqd: 1 },
			async (v) => {
				await frappe.call({ method: PAI_API + "rename_conversation", args: { suhbat: row.name, title: v.title } });
				if (row.name === this.suhbat) this.$title.text(v.title);
				this.load_list();
			},
			"Suhbat nomini o'zgartirish",
			"Saqlash"
		);
	}

	remove(row) {
		frappe.confirm(
			`"${frappe.utils.escape_html(row.title || "Suhbat")}" suhbati va undagi fayllar o'chiriladi.`,
			async () => {
				await frappe.call({ method: PAI_API + "delete_conversation", args: { suhbat: row.name } });
				if (row.name === this.suhbat) this.new_chat();
				this.load_list();
			}
		);
	}

	new_chat() {
		if (this.running) {
			frappe.show_alert({ message: "Avval joriy javob tugashini kuting yoki to'xtating", indicator: "orange" });
			return;
		}
		this.suhbat = null;
		this.$title.text("Pokiza AI");
		this.$list.find(".pai-item").removeClass("active");
		this.$root.removeClass("pai-side-open");
		this.show_empty();
		this.focus();
	}

	show_empty() {
		const name = frappe.utils.escape_html(frappe.boot.user.first_name || "");
		this.$thread.html(`
			<div class="pai-empty">
				<div class="pai-mark pai-mark-lg">P</div>
				<h2 class="pai-empty-title">${name ? name + ", n" : "N"}imani bilmoqchisiz?</h2>
				<p class="pai-empty-sub">Sotuv, qarzlar, kassa, ombor va ishlab chiqarish bo'yicha so'rang. Ovozli xabar, chek yoki nakladnoy rasmini yuborishingiz, Excel yoki PDF hisobot so'rashingiz mumkin.</p>
				<div class="pai-examples"></div>
			</div>`);
		const $ex = this.$thread.find(".pai-examples");
		PAI_EXAMPLES.forEach(({ topic, q }) => {
			const $b = $(`<button type="button" class="pai-example"><span class="pai-example-topic"></span><span class="pai-example-q"></span></button>`);
			$b.find(".pai-example-topic").text(topic);
			$b.find(".pai-example-q").text(q);
			$b.on("click", () => {
				this.$input.val(q);
				this.send();
			});
			$ex.append($b);
		});
	}

	async open(name) {
		if (this.running && name !== this.suhbat) {
			frappe.show_alert({ message: "Avval joriy javob tugashini kuting yoki to'xtating", indicator: "orange" });
			return;
		}
		this.suhbat = name;
		this.$root.removeClass("pai-side-open");
		this.$list.find(".pai-item").removeClass("active");
		this.$list.find(`.pai-item[data-name="${name}"]`).addClass("active");
		this.$thread.html(`<div class="pai-loading">Yuklanmoqda…</div>`);
		const r = await frappe.call({ method: PAI_API + "get_conversation", args: { suhbat: name } });
		const data = r.message;
		this.$title.text(data.suhbat.title || "Suhbat");
		this.$thread.empty();
		let pending = null;
		data.messages.forEach((m) => {
			if (m.role === "user") {
				this.add_user(m.text, m.files);
				this.last_user = { text: m.text, files: (m.files || []).map((f) => f.name), shown: m.files || [] };
			} else {
				const $el = this.add_assistant();
				if (m.status === "Ishlayapti") pending = { xabar: m.name, $el };
				else this.finish_assistant($el, m);
			}
		});
		if (pending) this.start_running(pending.xabar, pending.$el);
		this.mark_last();
		this.scroll_bottom(true);
	}

	// ---------- xabarlar ----------
	add_user(text, files) {
		this.$thread.find(".pai-empty").remove();
		const $m = $(`<div class="pai-msg pai-user"><div class="pai-user-files"></div></div>`);
		(files || []).forEach((f) => $m.find(".pai-user-files").append(this.file_thumb(f)));
		if (text) $(`<div class="pai-bubble"></div>`).text(text).appendTo($m);
		this.$thread.append($m);
		return $m;
	}

	file_thumb(f) {
		if (f.kind === "audio") return this.voice_bubble(f);
		if (f.kind === "image") {
			const $a = $(`<a class="pai-thumb" target="_blank" rel="noopener"><img alt=""></a>`);
			$a.attr("href", f.file_url).find("img").attr("src", f.file_url).attr("alt", f.file_name);
			return $a;
		}
		return this.file_card(f, false);
	}

	file_card(f, primary) {
		const ext = pai_ext(f.file_name);
		const $a = $(`
			<a class="pai-file-card ${primary ? "primary" : ""}" target="_blank" rel="noopener" download>
				<span class="pai-file-badge" data-ext="${ext}"></span>
				<span class="pai-file-meta"><span class="pai-file-name"></span><span class="pai-file-sub"></span></span>
				${primary ? `<span class="pai-file-dl">${pai_icon("download", 16)}</span>` : ""}
			</a>`);
		$a.attr("href", f.file_url);
		$a.find(".pai-file-badge").text(ext.toUpperCase());
		$a.find(".pai-file-name").text(f.title || f.file_name);
		$a.find(".pai-file-sub").text([primary ? "Yuklab olish" : "", pai_size(f.size)].filter(Boolean).join(" · "));
		return $a;
	}

	add_assistant() {
		const $m = $(`
			<div class="pai-msg pai-assistant">
				<div class="pai-mark">P</div>
				<div class="pai-body">
					<details class="pai-thinking hidden"><summary>Fikrlash jarayoni</summary><div class="pai-thinking-text"></div></details>
					<div class="pai-steps"></div>
					<div class="pai-dashes"></div>
					<div class="pai-content"></div>
					<div class="pai-files"></div>
					<div class="pai-meta"></div>
				</div>
			</div>`);
		this.$thread.append($m);
		return $m;
	}

	finish_assistant($el, m) {
		$el.find(".pai-steps").empty();
		const $c = $el.find(".pai-content").html(this.md(m.text || ""));
		$el.data("text", m.text || "");
		if (m.error) {
			const $err = $(`<div class="pai-error"><span></span></div>`);
			$err.find("span").text(m.error);
			$(`<button type="button" class="pai-retry">${pai_icon("retry", 14)} Qayta urinish</button>`)
				.on("click", () => this.retry())
				.appendTo($err);
			$c.append($err);
		} else if (m.status === "To'xtatildi") {
			$c.append(`<div class="pai-muted">To'xtatildi</div>`);
		}
		const $dashes = $el.find(".pai-dashes").empty();
		(m.dashboards || []).forEach((d) => this.render_dashboard($dashes, d));
		const $files = $el.find(".pai-files").empty();
		(m.files || []).forEach((f) => $files.append(this.file_card(f, true)));
		this.render_meta($el, m.sources || []);
	}

	render_meta($el, sources) {
		const $meta = $el.find(".pai-meta").empty();
		const text = $el.data("text");
		if (text) {
			$(`<button type="button" class="pai-act" title="Nusxa olish" aria-label="Nusxa olish">${pai_icon("copy", 15)}</button>`)
				.on("click", () => frappe.utils.copy_to_clipboard(text))
				.appendTo($meta);
		}
		const ok = sources.filter((s) => !s.is_error && s.name !== "describe_doctype" && s.name !== "search_doctypes");
		if (sources.length) {
			const names = [...new Set(ok.map((s) => (s.report ? s.report : PAI_TOOL_LABELS[s.name] || s.name)))];
			const $d = $(`<details class="pai-sources"><summary></summary><div class="pai-source-list"></div></details>`);
			$d.find("summary").text(names.length ? `Manba: ${names.slice(0, 3).join(", ")}${names.length > 3 ? ` va yana ${names.length - 3}` : ""}` : "Manba");
			const $box = $d.find(".pai-source-list");
			sources.forEach((s) => {
				const $s = $(`<div class="pai-source"><div class="pai-source-head"></div></div>`);
				let head = PAI_TOOL_LABELS[s.name] || s.name;
				if (s.report) head += `: ${s.report}`;
				if (s.purpose) head += `. ${s.purpose}`;
				$s.find(".pai-source-head").text(head + (s.is_error ? " (xato, AI qayta urindi)" : "") + (s.ms ? ` · ${(s.ms / 1000).toFixed(1)} s` : ""));
				if (s.sql) $(`<pre></pre>`).text(s.sql).appendTo($s);
				else if (s.input && Object.keys(s.input).length) $(`<pre></pre>`).text(JSON.stringify(s.input, null, 1)).appendTo($s);
				$box.append($s);
			});
			$meta.append($d);
		}
	}

	// ---------- dashboard ----------
	render_dashboard($into, dash) {
		const $d = $(`<section class="pai-dash"><h3 class="pai-dash-title"></h3><div class="pai-kpis"></div><div class="pai-charts"></div></section>`);
		$d.find(".pai-dash-title").text(dash.title);
		const $k = $d.find(".pai-kpis");
		(dash.kpis || []).forEach((k) => $k.append(this.kpi_tile(k)));
		if (!(dash.kpis || []).length) $k.remove();
		$into.append($d);
		(dash.charts || []).forEach((c) => this.render_chart($d.find(".pai-charts"), c));
	}

	kpi_tile(k) {
		const unit = k.unit ? ` ${k.unit}` : "";
		const $t = $(`
			<div class="pai-kpi">
				<div class="pai-kpi-label"></div>
				<div class="pai-kpi-value"></div>
				<div class="pai-kpi-delta"></div>
			</div>`);
		$t.find(".pai-kpi-label").text(k.label);
		const big = k.value !== null && Math.abs(k.value) >= 1e7;
		$t.find(".pai-kpi-value").text(k.value === null ? "—" : (big ? pai_short(k.value) : pai_num(k.value)) + unit);
		if (k.value !== null) $t.attr("title", pai_num(k.value, Number.isInteger(k.value) ? 0 : 2) + unit);
		const $delta = $t.find(".pai-kpi-delta");
		if (k.delta_pct !== null && k.delta_pct !== undefined) {
			const up = k.delta_pct > 0;
			const flat = k.delta_pct === 0;
			const good = flat ? null : (up ? k.good_when !== "down" : k.good_when === "down");
			$delta.addClass(good === null ? "flat" : good ? "good" : "bad");
			const arrow = flat ? "→" : up ? "▲" : "▼";
			$delta.text(`${arrow} ${up ? "+" : ""}${pai_num(k.delta_pct, 1)}%`);
			const prev = k.prev !== null ? ` (${big ? pai_short(k.prev) : pai_num(k.prev)}${unit})` : "";
			$(`<span class="pai-kpi-cmp"></span>`).text(` ${k.compare_label || "oldingi davrga nisbatan"}${prev}`).appendTo($delta);
		} else {
			$delta.remove();
		}
		return $t;
	}

	render_chart($into, c) {
		const dark = document.documentElement.getAttribute("data-theme") === "dark";
		const colors = PAI_SERIES[dark ? "dark" : "light"];
		const unit = c.unit ? ` ${c.unit}` : "";
		const $c = $(`
			<figure class="pai-chart">
				<figcaption><span class="pai-chart-title"></span><button type="button" class="pai-chart-toggle">Jadval</button></figcaption>
				<div class="pai-chart-plot"></div>
				<div class="pai-chart-table hidden"></div>
				<div class="pai-chart-src"></div>
			</figure>`);
		$c.find(".pai-chart-title").text(c.title + (c.unit ? `, ${c.unit}` : ""));
		$c.find(".pai-chart-src").text(c.source_label + (c.truncated ? " · faqat birinchi qismi" : ""));
		$into.append($c);

		// jadval ko'rinishi: rang ko'ra olmaydiganlar va aniq raqam kerak bo'lganda
		const $tbl = $(`<div class="pai-table-wrap"><table class="pai-table"><thead><tr><th></th></tr></thead><tbody></tbody></table></div>`);
		c.datasets.forEach((ds) => $(`<th class="pai-num"></th>`).text(ds.name).appendTo($tbl.find("thead tr")));
		c.labels.forEach((l, i) => {
			const $tr = $(`<tr><td></td></tr>`);
			$tr.find("td").text(l);
			c.datasets.forEach((ds) => $(`<td class="pai-num"></td>`).text(pai_num(ds.values[i])).appendTo($tr));
			$tbl.find("tbody").append($tr);
		});
		$c.find(".pai-chart-table").append($tbl);
		$c.find(".pai-chart-toggle").on("click", (e) => {
			const showing = $c.find(".pai-chart-table").toggleClass("hidden").hasClass("hidden");
			$c.find(".pai-chart-plot").toggleClass("hidden", !showing);
			$(e.currentTarget).text(showing ? "Jadval" : "Grafik");
		});

		// bitta qatorli taqqoslash va ulush: gorizontal ustunlar (uzun nomlar to'liq o'qiladi)
		if (c.type === "share" || (c.type === "bar" && c.datasets.length === 1)) {
			this.render_hbars($c.find(".pai-chart-plot"), c, colors[0], unit);
			return;
		}
		const type = c.type;
		const opts = {
			animate: 0,
			disableEntryAnimation: 1,
			data: { labels: c.labels, datasets: c.datasets },
			type,
			height: 240,
			colors: colors.slice(0, c.datasets.length),
			axisOptions: { xAxisMode: "tick", yAxisMode: "span", xIsSeries: c.type === "line", shortenYAxisNumbers: 1 },
			lineOptions: { hideDots: c.labels.length > 24 ? 1 : 0, dotSize: 4, regionFill: c.datasets.length === 1 ? 1 : 0 },
			barOptions: { spaceRatio: 0.35 },
			tooltipOptions: { formatTooltipY: (v) => pai_num(v) + unit },
			truncateLegends: 1,
		};
		try {
			new frappe.Chart($c.find(".pai-chart-plot").get(0), opts);
		} catch (e) {
			// grafik chizilmasa jadvalni ko'rsatamiz
			$c.find(".pai-chart-plot").addClass("hidden");
			$c.find(".pai-chart-table").removeClass("hidden");
			$c.find(".pai-chart-toggle").remove();
		}
	}

	render_hbars($plot, c, color, unit) {
		const vals = c.datasets[0].values;
		const total = vals.reduce((a, b) => a + b, 0);
		const max = Math.max(...vals.map((v) => Math.abs(v)), 1);
		const $list = $(`<div class="pai-hbars" role="list"></div>`);
		c.labels.forEach((label, i) => {
			const v = vals[i];
			const share = c.type === "share" && total ? ` · ${pai_num((v / total) * 100, 1)}%` : "";
			const $row = $(`
				<div class="pai-hbar" role="listitem">
					<div class="pai-hbar-label"></div>
					<div class="pai-hbar-track"><div class="pai-hbar-fill"></div></div>
					<div class="pai-hbar-value"></div>
				</div>`);
			$row.find(".pai-hbar-label").text(label).attr("title", label);
			$row.find(".pai-hbar-fill").css({ width: `${Math.max((Math.abs(v) / max) * 100, 0.5)}%`, background: color });
			$row.find(".pai-hbar-value").text((Math.abs(v) >= 1e7 ? pai_short(v) : pai_num(v)) + share);
			$row.attr("title", `${label}: ${pai_num(v)}${unit}${share}`);
			$list.append($row);
		});
		$plot.append($list);
	}

	mark_last() {
		this.$thread.find(".pai-assistant").removeClass("last");
		this.$thread.find(".pai-assistant").last().addClass("last");
	}

	// ---------- fayl biriktirish ----------
	bind_drop() {
		const $main = this.$root.find(".pai-main");
		const $drop = this.$root.find(".pai-drop");
		let depth = 0;
		$main.on("dragenter", (e) => {
			if (![...(e.originalEvent.dataTransfer?.types || [])].includes("Files")) return;
			e.preventDefault();
			depth++;
			$drop.removeClass("hidden");
		});
		$main.on("dragover", (e) => e.preventDefault());
		$main.on("dragleave", () => {
			depth = Math.max(0, depth - 1);
			if (!depth) $drop.addClass("hidden");
		});
		$main.on("drop", (e) => {
			e.preventDefault();
			depth = 0;
			$drop.addClass("hidden");
			this.add_files([...(e.originalEvent.dataTransfer?.files || [])]);
		});
	}

	add_files(files) {
		const ok = PAI_ACCEPT.split(",");
		for (const file of files) {
			if (this.attachments.length >= PAI_MAX_FILES) {
				frappe.show_alert({ message: `Bitta xabarga ko'pi bilan ${PAI_MAX_FILES} ta fayl`, indicator: "orange" });
				break;
			}
			const ext = "." + pai_ext(file.name || "rasm.png");
			if (!ok.includes(ext)) {
				frappe.show_alert({ message: `${file.name}: faqat rasm, PDF yoki Excel/CSV`, indicator: "orange" });
				continue;
			}
			if (file.size > 20 * 1024 * 1024) {
				frappe.show_alert({ message: `${file.name}: 20 MB dan katta`, indicator: "orange" });
				continue;
			}
			const att = {
				id: frappe.utils.get_random(8),
				file,
				name: file.name || `rasm-${Date.now()}.png`,
				status: "uploading",
				preview: file.type.startsWith("image/") ? URL.createObjectURL(file) : null,
			};
			this.attachments.push(att);
			this.upload(att);
		}
		this.render_chips();
		this.focus();
	}

	async upload(att) {
		const fd = new FormData();
		fd.append("file", att.file, att.name);
		try {
			const res = await fetch(`/api/method/${PAI_API}upload`, {
				method: "POST",
				headers: { "X-Frappe-CSRF-Token": frappe.csrf_token, Accept: "application/json" },
				body: fd,
			});
			const data = await res.json();
			if (!res.ok) throw new Error(this.server_error(data) || "Yuklab bo'lmadi");
			att.info = data.message;
			att.status = "ready";
		} catch (e) {
			att.status = "error";
			att.error = e.message;
		}
		this.render_chips();
	}

	server_error(data) {
		try {
			const msgs = JSON.parse(data._server_messages || "[]").map((m) => JSON.parse(m).message);
			return frappe.utils.html2text(msgs.join(" ")) || data.exception;
		} catch (e) {
			return data.exception;
		}
	}

	render_chips() {
		this.attachments = this.attachments.filter((a) => !a.removed);
		this.$chips.empty().toggleClass("has", this.attachments.length > 0);
		this.attachments.forEach((a) => {
			const ext = pai_ext(a.name);
			const $c = $(`
				<div class="pai-chip ${a.status}">
					${a.preview ? `<img alt="">` : `<span class="pai-file-badge" data-ext="${ext}"></span>`}
					<span class="pai-chip-meta"><span class="pai-chip-name"></span><span class="pai-chip-sub"></span></span>
					<button type="button" class="pai-chip-x" aria-label="Olib tashlash">${pai_icon("x", 14)}</button>
				</div>`);
			if (a.preview) $c.find("img").attr("src", a.preview);
			else $c.find(".pai-file-badge").text(ext.toUpperCase());
			$c.find(".pai-chip-name").text(a.name);
			$c.find(".pai-chip-sub").text(
				a.status === "uploading" ? "Yuklanmoqda…" : a.status === "error" ? a.error : pai_size(a.info?.size || a.file.size)
			);
			$c.attr("title", a.status === "error" ? a.error : a.name);
			$c.find(".pai-chip-x").on("click", () => {
				a.removed = true;
				if (a.preview) URL.revokeObjectURL(a.preview);
				this.render_chips();
			});
			this.$chips.append($c);
		});
		this.update_send();
	}

	// ---------- ovozli xabar ----------
	bind_voice() {
		const $r = this.$root;
		this.$mic.on("click", () => this.start_recording());
		$r.find(".pai-rec-cancel").on("click", () => this.stop_recording(false));
		$r.find(".pai-rec-send").on("click", () => this.stop_recording(true));
		// yozish paytida: Enter — yuborish, Esc — bekor qilish
		$(document).on("keydown.pokiza_ai_rec", (e) => {
			if (!this.rec) return;
			if (e.key === "Escape") {
				e.preventDefault();
				this.stop_recording(false);
			} else if (e.key === "Enter") {
				e.preventDefault();
				this.stop_recording(true);
			}
		});
		const $wave = $r.find(".pai-rec-wave");
		for (let i = 0; i < 40; i++) $wave.append("<span></span>");
	}

	async start_recording() {
		if (this.running || this.rec) return;
		if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
			frappe.msgprint(
				window.isSecureContext
					? "Bu brauzer ovoz yozishni qo'llab-quvvatlamaydi. Chrome, Edge yoki Safari'ning yangi versiyasini ishlating."
					: "Mikrofon faqat xavfsiz (https://) manzilda ishlaydi. Administratorga sayt uchun SSL yoqishni ayting.",
				"Ovozli xabar"
			);
			return;
		}
		let stream;
		try {
			stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
		} catch (e) {
			frappe.show_alert({
				message: e.name === "NotAllowedError"
					? "Mikrofonga ruxsat berilmagan. Manzil qatoridagi qulf belgisini bosib, ruxsat bering."
					: "Mikrofon topilmadi yoki band.",
				indicator: "orange",
			}, 7);
			return;
		}
		const mime = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4", "audio/webm"].find((m) => MediaRecorder.isTypeSupported(m)) || "";
		const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
		const rec = (this.rec = { stream, recorder, chunks: [], started: Date.now(), send: false });
		recorder.ondataavailable = (e) => e.data.size && rec.chunks.push(e.data);
		recorder.onstop = () => this.finish_recording(rec);
		recorder.start(250);
		this.start_meter(rec);
		this.recorder_ui(true);
	}

	start_meter(rec) {
		const $time = this.$root.find(".pai-rec-time").text("0:00");
		const bars = this.$root.find(".pai-rec-wave span").toArray();
		bars.forEach((b) => (b.style.height = "3px"));
		rec.timer = setInterval(() => {
			const sec = (Date.now() - rec.started) / 1000;
			$time.text(`${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, "0")}`);
			if (sec >= PAI_VOICE_MAX_SEC) this.stop_recording(true);
		}, 250);
		if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
		try {
			const ctx = (rec.ctx = new (window.AudioContext || window.webkitAudioContext)());
			const analyser = ctx.createAnalyser();
			analyser.fftSize = 512;
			ctx.createMediaStreamSource(rec.stream).connect(analyser);
			const buf = new Uint8Array(analyser.fftSize);
			const levels = [];
			let last = 0;
			const tick = (t) => {
				if (!this.rec || this.rec !== rec) return;
				if (t - last > 90) {
					last = t;
					analyser.getByteTimeDomainData(buf);
					let peak = 0;
					for (const v of buf) peak = Math.max(peak, Math.abs(v - 128));
					levels.push(Math.min(1, peak / 64));
					if (levels.length > bars.length) levels.shift();
					const off = bars.length - levels.length;
					bars.forEach((b, i) => (b.style.height = `${3 + Math.round((levels[i - off] || 0) * 21)}px`));
				}
				rec.raf = requestAnimationFrame(tick);
			};
			rec.raf = requestAnimationFrame(tick);
		} catch (e) {
			// to'lqin ko'rsatkichi ixtiyoriy
		}
	}

	stop_recording(send) {
		const rec = this.rec;
		if (!rec) return;
		rec.send = send;
		rec.duration = (Date.now() - rec.started) / 1000;
		if (rec.recorder.state !== "inactive") rec.recorder.stop();
	}

	async finish_recording(rec) {
		clearInterval(rec.timer);
		cancelAnimationFrame(rec.raf);
		rec.stream.getTracks().forEach((t) => t.stop());
		rec.ctx && rec.ctx.close();
		this.rec = null;
		this.recorder_ui(false);
		if (!rec.send) return;
		if (rec.duration < 0.8 || !rec.chunks.length) {
			frappe.show_alert({ message: "Ovozli xabar juda qisqa. Tugmani bosib, gapirib bo'lgach yuboring.", indicator: "orange" });
			return;
		}
		const type = rec.recorder.mimeType || rec.chunks[0].type || "audio/webm";
		const ext = type.includes("ogg") ? "ogg" : type.includes("mp4") ? "m4a" : "webm";
		const blob = new Blob(rec.chunks, { type: type.split(";")[0] });
		const name = `ovozli-xabar-${frappe.datetime.now_datetime().replace(/[^0-9]/g, "").slice(0, 14)}.${ext}`;
		const local_url = URL.createObjectURL(blob);
		const shown = { kind: "audio", file_name: name, file_url: local_url, duration: Math.round(rec.duration), uploading: true };
		try {
			const info = await this.upload_blob(blob, name, rec.duration);
			this.send({ text: "", files: [info.name], shown: [{ ...info, file_url: local_url, duration: info.duration || shown.duration }] });
		} catch (e) {
			frappe.show_alert({ message: `Ovozli xabar yuborilmadi: ${e.message}`, indicator: "red" }, 7);
		}
	}

	async upload_blob(blob, name, duration) {
		const fd = new FormData();
		fd.append("file", blob, name);
		if (duration) fd.append("duration", String(Math.round(duration * 10) / 10));
		const res = await fetch(`/api/method/${PAI_API}upload`, {
			method: "POST",
			headers: { "X-Frappe-CSRF-Token": frappe.csrf_token, Accept: "application/json" },
			body: fd,
		});
		const data = await res.json();
		if (!res.ok) throw new Error(this.server_error(data) || "Yuklab bo'lmadi");
		return data.message;
	}

	recorder_ui(on) {
		const $box = this.$root.find(".pai-box");
		$box.toggleClass("recording", on);
		$box.find("textarea, .pai-tools, .pai-chips").toggleClass("hidden", on);
		$box.find(".pai-recorder").toggleClass("hidden", !on);
		if (!on) this.render_chips();
		if (on) $box.find(".pai-rec-send").trigger("focus");
		else this.focus();
	}

	voice_bubble(f) {
		const $v = $(`
			<div class="pai-voice-wrap">
				<div class="pai-voice" data-file="">
					<button type="button" class="pai-voice-play" aria-label="Eshitish">${pai_icon("play", 16)}</button>
					<div class="pai-voice-track" role="slider" aria-label="Ovozli xabar" tabindex="0" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><div class="pai-voice-fill"></div></div>
					<span class="pai-voice-time"></span>
					<audio preload="metadata"></audio>
				</div>
				<div class="pai-voice-text"></div>
			</div>`);
		$v.find(".pai-voice").attr("data-file", f.name || "");
		const audio = $v.find("audio").get(0);
		audio.src = f.file_url;
		const fmt = (sec) => `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, "0")}`;
		const total = () => (isFinite(audio.duration) && audio.duration > 0 ? audio.duration : f.duration || 0);
		const $time = $v.find(".pai-voice-time").text(f.duration ? fmt(f.duration) : "0:00");
		const $fill = $v.find(".pai-voice-fill");
		const $play = $v.find(".pai-voice-play");
		$play.on("click", () => {
			if (audio.paused) {
				document.querySelectorAll(".pai-voice audio").forEach((a) => a !== audio && a.pause());
				audio.play().catch(() => frappe.show_alert({ message: "Audio'ni ijro etib bo'lmadi", indicator: "orange" }));
			} else audio.pause();
		});
		audio.addEventListener("play", () => $play.html(pai_icon("pause", 16)).attr("aria-label", "To'xtatish"));
		audio.addEventListener("pause", () => $play.html(pai_icon("play", 16)).attr("aria-label", "Eshitish"));
		audio.addEventListener("loadedmetadata", () => total() && $time.text(fmt(total())));
		audio.addEventListener("timeupdate", () => {
			const t = total();
			const pct = t ? Math.min(100, (audio.currentTime / t) * 100) : 0;
			$fill.css("width", pct + "%");
			$v.find(".pai-voice-track").attr("aria-valuenow", Math.round(pct));
			$time.text(fmt(audio.paused && !audio.currentTime ? t : audio.currentTime));
		});
		audio.addEventListener("ended", () => {
			$fill.css("width", "0%");
			$time.text(fmt(total()));
		});
		const seek = (ratio) => {
			const t = total();
			if (t) audio.currentTime = Math.max(0, Math.min(t, ratio * t));
		};
		$v.find(".pai-voice-track").on("click", (e) => {
			const r = e.currentTarget.getBoundingClientRect();
			seek((e.clientX - r.left) / r.width);
		}).on("keydown", (e) => {
			const t = total();
			if (!t) return;
			if (e.key === "ArrowRight") seek((audio.currentTime + 5) / t);
			if (e.key === "ArrowLeft") seek((audio.currentTime - 5) / t);
		});
		this.set_transcript($v, f.transcript);
		return $v;
	}

	set_transcript($wrap, text) {
		const $t = $wrap.find(".pai-voice-text");
		$t.toggleClass("hidden", !text).text(text || "");
	}

	// ---------- yuborish / streaming ----------
	async send(override) {
		if (this.running) return;
		const text = override ? override.text : (this.$input.val() || "").trim();
		const ready = override ? [] : this.attachments.filter((a) => a.status === "ready");
		const file_names = override ? override.files : ready.map((a) => a.info.name);
		if (!override && this.attachments.some((a) => a.status === "uploading")) return;
		if (!text && !file_names.length) return;

		const shown = override ? override.shown : ready.map((a) => a.info);
		if (!override) {
			this.$input.val("");
			this.autosize();
			this.attachments.forEach((a) => a.preview && URL.revokeObjectURL(a.preview));
			this.attachments = [];
			this.render_chips();
		}
		this.last_user = { text, files: file_names, shown };
		this.add_user(text, shown);
		const $el = this.add_assistant();
		this.mark_last();
		this.set_step($el, "Yuborilmoqda…");
		this.scroll_bottom(true);
		this.running = { xabar: null, $el, text: "", thinking: "" };
		this.set_busy(true);
		try {
			const r = await frappe.call({
				method: PAI_API + "send_message",
				args: { text, suhbat: this.suhbat, files: JSON.stringify(file_names) },
				freeze: false,
			});
			const isNew = !this.suhbat;
			this.suhbat = r.message.suhbat;
			if (isNew) {
				this.$title.text(text.slice(0, 80) || (file_names.length && shown.every((f) => f.kind === "audio") ? "Ovozli xabar" : "Suhbat"));
				this.load_list();
			}
			this.start_running(r.message.xabar, $el);
		} catch (e) {
			this.set_busy(false);
			this.finish_assistant($el, { status: "Xato", error: "Xabar yuborilmadi. Internet aloqasini tekshirib, qayta urining." });
		}
	}

	retry() {
		if (!this.last_user || this.running) return;
		this.send({ text: this.last_user.text, files: this.last_user.files || [], shown: this.last_user.shown || [] });
	}

	start_running(xabar, $el) {
		this.running = { xabar, $el, text: "", thinking: "" };
		this.set_busy(true);
		this.set_step($el, "O'ylayapti…");
	}

	set_busy(busy) {
		this.$send.toggleClass("hidden", busy);
		this.$stop.toggleClass("hidden", !busy);
		if (!busy) this.running = null;
		this.update_send();
	}

	async stop() {
		if (!this.running || !this.running.xabar) return;
		this.set_step(this.running.$el, "To'xtatilmoqda…");
		await frappe.call({ method: PAI_API + "stop", args: { xabar: this.running.xabar } });
	}

	set_step($el, text) {
		const $steps = $el.find(".pai-steps");
		$steps.find(".pai-step.live").remove();
		$(`<div class="pai-step live"><span class="pai-dot"></span></div>`).append(document.createTextNode(text)).appendTo($steps);
	}

	bind_realtime() {
		frappe.realtime.on("pokiza_ai", (d) => {
			const r = this.running;
			if (!r || d.xabar !== r.xabar) return;
			const $el = r.$el;
			if (d.type === "status") {
				this.set_step($el, d.text);
			} else if (d.type === "tool_start" || d.type === "tool_run") {
				const label = PAI_TOOL_LABELS[d.name] || d.name;
				const what = d.input && d.input.report ? `${label}: ${d.input.report}` : label;
				this.set_step($el, d.name === "create_file" ? "Fayl tayyorlanmoqda…" : `${what}…`);
			} else if (d.type === "tool_end") {
				$el.find(".pai-steps .pai-step.live").remove();
				$(`<div class="pai-step ${d.is_error ? "err" : "ok"}"></div>`)
					.text(`${d.is_error ? "✕" : "✓"} ${PAI_TOOL_LABELS[d.name] || d.name}`)
					.appendTo($el.find(".pai-steps"));
			} else if (d.type === "transcript") {
				const $w = this.$thread.find(`.pai-voice[data-file="${d.file}"]`).closest(".pai-voice-wrap");
				this.set_transcript($w, d.text);
			} else if (d.type === "dashboard") {
				this.render_dashboard($el.find(".pai-dashes"), d.dashboard);
				this.scroll_bottom();
			} else if (d.type === "file") {
				$el.find(".pai-files").append(this.file_card(d.file, true));
				this.scroll_bottom();
			} else if (d.type === "delta") {
				if (d.kind === "thinking") {
					r.thinking += d.text;
					$el.find(".pai-thinking").removeClass("hidden");
					$el.find(".pai-thinking-text").text(r.thinking);
				} else {
					r.text += d.text;
					$el.find(".pai-steps .pai-step.live").remove();
					$el.find(".pai-content").html(this.md(r.text)).addClass("streaming");
				}
				this.scroll_bottom();
			} else if (d.type === "done") {
				this.set_busy(false);
				$el.find(".pai-content").removeClass("streaming");
				// manba va fayllarni serverdan olamiz (audit bilan bir xil)
				frappe.call({ method: PAI_API + "get_conversation", args: { suhbat: d.suhbat } }).then((res) => {
					const m = (res.message.messages || []).find((x) => x.name === d.xabar) || {
						text: d.text,
						status: d.status,
						error: d.error,
					};
					this.finish_assistant($el, m);
					this.scroll_bottom();
				});
				this.load_list();
			}
		});
	}

	scroll_bottom(force, smooth) {
		const el = this.$scroll.get(0);
		const near = el.scrollHeight - el.scrollTop - el.clientHeight < 160;
		if (force || near) el.scrollTo({ top: el.scrollHeight, behavior: smooth ? "smooth" : "auto" });
	}

	// ---------- markdown (xavfsiz) ----------
	md(text) {
		return this.sanitize(frappe.markdown(text || ""));
	}

	sanitize(html) {
		const ALLOWED = new Set([
			"P", "BR", "STRONG", "B", "EM", "I", "CODE", "PRE", "UL", "OL", "LI", "BLOCKQUOTE",
			"H1", "H2", "H3", "H4", "H5", "H6", "TABLE", "THEAD", "TBODY", "TR", "TH", "TD", "HR", "A", "DEL", "SPAN",
		]);
		const doc = new DOMParser().parseFromString(`<div>${html}</div>`, "text/html");
		const walk = (node) => {
			[...node.children].forEach((el) => {
				if (!ALLOWED.has(el.tagName)) {
					el.replaceWith(document.createTextNode(el.textContent));
					return;
				}
				[...el.attributes].forEach((a) => {
					const keep = el.tagName === "A" && a.name === "href" && /^https?:\/\//i.test(a.value);
					if (!keep) el.removeAttribute(a.name);
				});
				if (el.tagName === "A") {
					el.setAttribute("target", "_blank");
					el.setAttribute("rel", "noopener noreferrer");
				}
				walk(el);
			});
		};
		const root = doc.body.firstChild;
		walk(root);
		// raqamli ustunlarni o'ngga tekislash
		const NUM = /^[−\-+]?[\d\s  .,]+\s*(%|so'm|so‘m|sum|kg|uzs|\$|usd)?$/i;
		root.querySelectorAll("table").forEach((t) => {
			t.className = "pai-table";
			const rows = [...t.querySelectorAll("tr")];
			const cols = Math.max(0, ...rows.map((r) => r.children.length));
			for (let i = 0; i < cols; i++) {
				const cells = rows.map((r) => r.children[i]).filter((c) => c && c.tagName === "TD");
				const filled = cells.filter((c) => c.textContent.trim());
				if (filled.length && filled.every((c) => NUM.test(c.textContent.trim()))) {
					rows.forEach((r) => r.children[i] && r.children[i].classList.add("pai-num"));
				}
			}
			const w = doc.createElement("div");
			w.className = "pai-table-wrap";
			t.replaceWith(w);
			w.appendChild(t);
		});
		return root.innerHTML;
	}
}
