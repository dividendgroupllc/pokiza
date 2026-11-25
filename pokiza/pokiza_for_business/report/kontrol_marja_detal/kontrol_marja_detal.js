// Copyright (c) 2026, Sardorbek and contributors
// For license information, please see license.txt

frappe.query_reports["Kontrol Marja Detal"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("Boshlanish"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
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
		{
			fieldname: "vozvrat",
			label: __("Vozvrat"),
			fieldtype: "Select",
			options: [
				{ value: "", label: __("Hammasi") },
				{ value: "Vozvratsiz", label: __("Vozvratsiz") },
				{ value: "Faqat vozvrat", label: __("Faqat vozvrat") },
			],
			default: "",
		},
	],
	// jadval ichida har bir ustun uchun qidiruv qatori
	get_datatable_options(options) {
		return Object.assign(options, { inlineFilters: true });
	},
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "schyot" && data) {
			if (data.is_jami) {
				value = `<span style="font-weight:600">${value}</span>`;
			} else if (data.schyot) {
				value = `<a href="/app/sales-invoice/${encodeURIComponent(data.schyot)}">${value}</a>`;
			}
		}
		if (data && data.is_jami && column.fieldname !== "schyot") {
			value = `<span style="font-weight:600">${value}</span>`;
		}
		if (data && data.is_vozvrat && !data.is_jami) {
			value = `<span style="color:var(--red-500)">${value}</span>`;
		}
		return value;
	},
};
