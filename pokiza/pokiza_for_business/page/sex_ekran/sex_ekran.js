// Copyright (c) 2026, abdulloh and contributors
// Kolbasa sexi — planshet kartochka ekrani

frappe.pages['sex-ekran'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Sex ekran',
		single_column: true,
	});

	const app = new SexEkran(page, wrapper);
	wrapper.sex_ekran = app;
};

frappe.pages['sex-ekran'].on_page_show = function (wrapper) {
	if (wrapper.sex_ekran) wrapper.sex_ekran.start_auto_refresh();
};

frappe.pages['sex-ekran'].on_page_hide = function (wrapper) {
	if (wrapper.sex_ekran) wrapper.sex_ekran.stop_auto_refresh();
};

class SexEkran {
	constructor(page, wrapper) {
		this.page = page;
		this.$body = $(wrapper).find('.layout-main-section');
		this.timer = null;
		this.workstation = localStorage.getItem('pokiza_sex') || null;
		this.inject_styles();
		if (this.workstation) {
			this.render_board();
		} else {
			this.render_picker();
		}
	}

	inject_styles() {
		if (document.getElementById('sex-ekran-css')) return;
		const css = `
		.sx-wrap{padding:8px 4px;font-family:'Segoe UI',Arial,sans-serif;}
		.sx-head{display:flex;align-items:center;justify-content:space-between;
			background:linear-gradient(135deg,#0f2942,#1a4f72);color:#fff;
			padding:14px 20px;border-radius:12px;margin-bottom:16px;}
		.sx-head h2{margin:0;font-size:22px;font-weight:700;}
		.sx-count{font-size:13px;opacity:.8;}
		.sx-switch{background:rgba(255,255,255,.15);color:#fff;border:none;
			padding:8px 14px;border-radius:8px;font-size:13px;cursor:pointer;}
		.sx-switch:hover{background:rgba(255,255,255,.28);}
		.sx-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px;}
		.sx-card{background:#fff;border:1px solid #eef0f2;border-radius:16px;overflow:hidden;
			box-shadow:0 2px 10px rgba(0,0,0,.06);display:flex;flex-direction:column;
			transition:transform .35s ease,opacity .35s ease;}
		.sx-card.sx-out{transform:scale(.85);opacity:0;}
		.sx-img{height:150px;background:#f1f5f9;display:flex;align-items:center;justify-content:center;
			overflow:hidden;}
		.sx-img img{width:100%;height:100%;object-fit:cover;}
		.sx-img .sx-letter{font-size:56px;font-weight:800;color:#cbd5e1;}
		.sx-info{padding:12px 14px;flex:1;}
		.sx-name{font-size:16px;font-weight:700;color:#111;line-height:1.25;margin-bottom:4px;}
		.sx-qty{font-size:20px;font-weight:800;color:#0b6b3a;}
		.sx-qty small{font-size:12px;color:#94a3b8;font-weight:600;}
		.sx-izoh{margin-top:6px;font-size:12px;color:#64748b;white-space:pre-wrap;}
		.sx-wo{margin-top:6px;font-size:10px;color:#cbd5e1;}
		.sx-btn{border:none;background:#2563eb;color:#fff;font-size:16px;font-weight:700;
			padding:14px;cursor:pointer;width:100%;transition:background .2s;}
		.sx-btn:hover{background:#1d4ed8;}
		.sx-btn:active{background:#1e40af;}
		.sx-empty{text-align:center;color:#94a3b8;padding:60px 20px;font-size:18px;}
		.sx-pick{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;
			max-width:760px;margin:40px auto;}
		.sx-pick-btn{background:linear-gradient(135deg,#1a4f72,#0f2942);color:#fff;border:none;
			padding:40px 20px;border-radius:16px;font-size:22px;font-weight:700;cursor:pointer;
			box-shadow:0 3px 12px rgba(0,0,0,.12);transition:transform .15s;}
		.sx-pick-btn:hover{transform:translateY(-3px);}
		.sx-pick-title{text-align:center;font-size:20px;color:#334155;margin:30px 0 0;font-weight:600;}
		`;
		$('<style id="sex-ekran-css">').text(css).appendTo('head');
	}

	// ---- Sex tanlash ekrani ----
	render_picker() {
		this.stop_auto_refresh();
		const me = this;
		this.$body.html('<div class="sx-wrap"><div class="sx-pick-title">Sexingizni tanlang</div><div class="sx-pick" id="sx-pick"></div></div>');
		frappe.call('pokiza.api.sex_ekran.get_sexlar').then(r => {
			const list = r.message || [];
			const $p = me.$body.find('#sx-pick').empty();
			if (!list.length) {
				$p.html('<div class="sx-empty">Workstation topilmadi</div>');
				return;
			}
			list.forEach(ws => {
				$(`<button class="sx-pick-btn">${frappe.utils.escape_html(ws)}</button>`)
					.on('click', () => {
						me.workstation = ws;
						localStorage.setItem('pokiza_sex', ws);
						me.render_board();
					}).appendTo($p);
			});
		});
	}

	// ---- Asosiy kartochka ekrani ----
	render_board() {
		const me = this;
		this.$body.html(`
			<div class="sx-wrap">
			  <div class="sx-head">
			    <div><h2>${frappe.utils.escape_html(this.workstation)}</h2>
			      <div class="sx-count" id="sx-count">Yuklanmoqda…</div></div>
			    <button class="sx-switch" id="sx-switch">Sexni o'zgartirish</button>
			  </div>
			  <div class="sx-grid" id="sx-grid"></div>
			</div>
		`);
		this.$body.find('#sx-switch').on('click', () => {
			localStorage.removeItem('pokiza_sex');
			me.workstation = null;
			me.render_picker();
		});
		this.load_cards();
		this.start_auto_refresh();
	}

	load_cards() {
		const me = this;
		if (!this.workstation) return;
		frappe.call({
			method: 'pokiza.api.sex_ekran.get_cards',
			args: { workstation: this.workstation },
			callback: (r) => me.render_cards(r.message || []),
		});
	}

	render_cards(cards) {
		const me = this;
		const $grid = this.$body.find('#sx-grid');
		if (!$grid.length) return;
		this.$body.find('#sx-count').text(`${cards.length} ta buyurtma`);
		$grid.empty();

		if (!cards.length) {
			$grid.html('<div class="sx-empty">✓ Hozircha bajariladigan ish yo\'q</div>');
			return;
		}

		cards.forEach(c => {
			const img = c.image
				? `<img src="${frappe.utils.escape_html(c.image)}" onerror="this.style.display='none'">`
				: `<span class="sx-letter">${frappe.utils.escape_html((c.item_name || '?').charAt(0))}</span>`;
			const izoh = c.izoh ? `<div class="sx-izoh">📝 ${frappe.utils.escape_html(c.izoh)}</div>` : '';
			const $card = $(`
				<div class="sx-card" data-jc="${frappe.utils.escape_html(c.job_card)}">
				  <div class="sx-img">${img}</div>
				  <div class="sx-info">
				    <div class="sx-name">${frappe.utils.escape_html(c.item_name)}</div>
				    <div class="sx-qty">${format_number(c.qty)} <small>${frappe.utils.escape_html(c.uom || '')}</small></div>
				    ${izoh}
				    <div class="sx-wo">${frappe.utils.escape_html(c.work_order)}</div>
				  </div>
				  <button class="sx-btn">Bajarildi ✓</button>
				</div>
			`);
			$card.find('.sx-btn').on('click', () => me.complete(c, $card));
			$grid.append($card);
		});
	}

	complete(card, $card) {
		const me = this;
		const $btn = $card.find('.sx-btn');
		$btn.prop('disabled', true).text('…');
		frappe.call({
			method: 'pokiza.api.sex_ekran.complete_card',
			args: { job_card: card.job_card },
			callback: () => {
				$card.addClass('sx-out');
				setTimeout(() => { $card.remove(); me.load_cards(); }, 350);
				frappe.show_alert({ message: `${card.item_name} — bajarildi`, indicator: 'green' });
			},
			error: () => {
				$btn.prop('disabled', false).text('Bajarildi ✓');
			},
		});
	}

	start_auto_refresh() {
		if (this.timer || !this.workstation) return;
		this.timer = setInterval(() => this.load_cards(), 12000);
	}

	stop_auto_refresh() {
		if (this.timer) { clearInterval(this.timer); this.timer = null; }
	}
}
