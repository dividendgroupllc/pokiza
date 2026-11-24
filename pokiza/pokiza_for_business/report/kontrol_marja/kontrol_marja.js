// Copyright (c) 2026, Sardorbek and contributors
// For license information, please see license.txt

frappe.query_reports["Kontrol Marja"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("Boshlanish"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.month_start(), -5),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("Tugash"),
			fieldtype: "Date",
			default: frappe.datetime.month_end(),
			reqd: 1,
		},
		{
			fieldname: "davr",
			label: __("Davr"),
			fieldtype: "Select",
			options: [
				{ value: "Oylik", label: __("Oylik") },
				{ value: "Kunlik", label: __("Kunlik") },
			],
			default: "Oylik",
			reqd: 1,
		},
		{
			fieldname: "customer_group",
			label: __("Mijoz guruhi"),
			fieldtype: "Link",
			options: "Customer Group",
		},
		{
			fieldname: "mijozlar",
			label: __("Mijozlar"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Customer", txt);
			},
		},
		{
			fieldname: "item_group",
			label: __("Tavar guruhi"),
			fieldtype: "Link",
			options: "Item Group",
		},
		{
			fieldname: "kategoriya",
			label: __("Kategoriya"),
			fieldtype: "Select",
			options: "\nSosiska\nKopchyonniy\nVaryonniy\nDelikates\nTushonka\nBoshqa\nBelgilanmagan",
		},
		{
			fieldname: "subkategoriya",
			label: __("Sub-kategoriya (brend)"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.xcall(
					"pokiza.pokiza_for_business.report.kontrol_marja.kontrol_marja.subkategoriyalar",
					{ txt: txt }
				);
			},
		},
		{
			fieldname: "tavarlar",
			label: __("Tavarlar"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Item", txt);
			},
		},
	],
	tree: true,
	name_field: "tavar",
	parent_field: "ota",
	initial_depth: 1,
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "tavar" && data && data.item_code) {
			value = `<a href="/app/item/${encodeURIComponent(data.item_code)}">${value}</a>`;
		}
		// son ustiga bosilganda — drill-down (qayerdan kelgani)
		const sonli =
			column.fieldname.startsWith("p_") ||
			["jami_marja", "jami_savdo", "jami_foyda"].includes(column.fieldname);
		if (sonli && data && data[column.fieldname] != null) {
			const args = {
				davr: column.fieldname.startsWith("p_") ? column.fieldname : "jami",
				davr_label: column.label,
				r_guruh: data.r_guruh || null,
				r_subkat: data.r_subkat || null,
				item_code: data.item_code || null,
				tavar_label: data.tavar,
			};
			const b64 = btoa(unescape(encodeURIComponent(JSON.stringify(args))));
			value = `<a href="#" onclick="event.preventDefault(); frappe.query_reports['Kontrol Marja'].detal('${b64}')">${value}</a>`;
		}
		if (data && data.indent === 0) {
			value = `<span style="font-weight:600">${value}</span>`;
		}
		return value;
	},
	detal: function (b64) {
		const args = JSON.parse(decodeURIComponent(escape(atob(b64))));
		const f = frappe.query_report.get_filter_values();
		frappe.call({
			method: "pokiza.pokiza_for_business.report.kontrol_marja.kontrol_marja.detal",
			args: { args: Object.assign({}, f, args) },
			freeze: true,
			callback: function (r) {
				const m = r.message;
				if (!m || !m.rows.length) {
					frappe.msgprint(__("Bu katak bo'yicha qator topilmadi"));
					return;
				}
				const pul = (v) => format_currency(v, frappe.defaults.get_default("currency"), 0);
				const pc = (v) => (v == null ? "-" : flt(v).toFixed(1) + "%");
				let satrlar = m.rows
					.map(
						(d) => `<tr${d.vozvrat ? ' style="color:var(--red-500)"' : ""}>
							<td><a href="/app/sales-invoice/${encodeURIComponent(d.schyot)}">${d.schyot}</a>${d.vozvrat ? " (vozvrat)" : ""}</td>
							<td>${frappe.datetime.str_to_user(d.sana)}</td>
							<td>${frappe.utils.escape_html(d.mijoz || "")}</td>
							<td><a href="/app/item/${encodeURIComponent(d.tavar)}">${frappe.utils.escape_html(d.tavar)}</a></td>
							<td class="text-right">${flt(d.kg, 1)}</td>
							<td class="text-right">${pul(d.savdo)}</td>
							<td class="text-right">${pul(d.tannarx)}</td>
							<td class="text-right">${pul(d.foyda)}</td>
							<td class="text-right">${pc(d.marja)}</td>
						</tr>`
					)
					.join("");
				const j = m.jami;
				satrlar += `<tr style="font-weight:600;border-top:2px solid var(--border-color)">
					<td colspan="4">${__("Jami")} (${m.rows.length} ${__("qator")})</td>
					<td class="text-right">${flt(j.kg, 1)}</td>
					<td class="text-right">${pul(j.savdo)}</td>
					<td class="text-right">${pul(j.tannarx)}</td>
					<td class="text-right">${pul(j.foyda)}</td>
					<td class="text-right">${pc(j.marja)}</td>
				</tr>`;
				const ogoh = m.qirqildi
					? `<p class="text-muted">${__("Faqat eng katta {0} qator ko'rsatildi — jami qatori ham faqat shular bo'yicha.", [500])}</p>`
					: "";
				const sarlavha = [args.tavar_label, args.davr_label].filter(Boolean).join(" · ");
				const d = new frappe.ui.Dialog({
					title: __("Manba: {0}", [sarlavha]),
					size: "extra-large",
				});
				d.$body.html(`${ogoh}
					<div style="max-height:65vh;overflow:auto">
					<table class="table table-bordered" style="font-size:12px">
						<thead><tr>
							<th>${__("Schyot")}</th><th>${__("Sana")}</th><th>${__("Mijoz")}</th><th>${__("Tavar")}</th>
							<th class="text-right">${__("Kg")}</th><th class="text-right">${__("Savdo")}</th>
							<th class="text-right">${__("Tannarx")}</th><th class="text-right">${__("Foyda")}</th>
							<th class="text-right">${__("Marja %")}</th>
						</tr></thead>
						<tbody>${satrlar}</tbody>
					</table></div>`);
				d.show();
			},
		});
	},
};
