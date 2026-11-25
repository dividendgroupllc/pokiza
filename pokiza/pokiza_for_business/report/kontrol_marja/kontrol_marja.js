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
		// son ustiga bosilganda — Kontrol Marja Detal sahifasi (filtrlar avto-to'ldirilgan)
		const sonli =
			column.fieldname.startsWith("p_") ||
			["jami_marja", "jami_savdo", "jami_foyda"].includes(column.fieldname);
		if (sonli && data && data[column.fieldname] != null) {
			const args = {
				davr: column.fieldname.startsWith("p_") ? column.fieldname : "jami",
				r_guruh: data.r_guruh || null,
				r_subkat: data.r_subkat || null,
				item_code: data.item_code || null,
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

		// bosilgan ustun davri -> sana oralig'i (hisobot oralig'iga qirqiladi)
		let from = f.from_date,
			to = f.to_date;
		if (args.davr !== "jami") {
			const q = args.davr.slice(2).split("_"); // p_YYYY_MM yoki p_YYYY_MM_DD
			if (q.length === 3) {
				from = to = `${q[0]}-${q[1]}-${q[2]}`;
			} else {
				const oy_boshi = `${q[0]}-${q[1]}-01`;
				const oy_oxiri = moment(oy_boshi).endOf("month").format("YYYY-MM-DD");
				from = from > oy_boshi ? from : oy_boshi;
				to = to < oy_oxiri ? to : oy_oxiri;
			}
		}

		frappe.route_options = {
			from_date: from,
			to_date: to,
			customer_group: f.customer_group || "",
			mijozlar: f.mijozlar || [],
			kategoriya: f.kategoriya || "",
			// bosilgan tugun hisobot filtridan ustun turadi
			item_group: args.r_guruh || f.item_group || "",
			subkategoriya: args.r_subkat ? [args.r_subkat] : f.subkategoriya || [],
			tavarlar: args.item_code ? [args.item_code] : f.tavarlar || [],
			vozvrat: "",
		};
		frappe.set_route("query-report", "Kontrol Marja Detal");
	},
};
