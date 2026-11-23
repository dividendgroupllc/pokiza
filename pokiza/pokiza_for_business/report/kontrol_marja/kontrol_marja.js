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
		if (data && data.indent === 0) {
			value = `<span style="font-weight:600">${value}</span>`;
		}
		return value;
	},
};
