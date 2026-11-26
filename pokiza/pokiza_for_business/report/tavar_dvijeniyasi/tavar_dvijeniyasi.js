// Copyright (c) 2026, Sardorbek and contributors
// For license information, please see license.txt

// Tavar dvijeniyasi — davr ichidagi kirim/chiqim lentasi.
// Kirim yashil, chiqim qizil; hujjat ustuni bosilsa o'sha hujjat ochiladi.

frappe.query_reports["Tavar Dvijeniyasi"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("Dan"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("Gacha"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "warehouse",
			label: __("Sklad"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query: () => ({ filters: { is_group: 0, disabled: 0 } }),
		},
		{
			fieldname: "item_code",
			label: __("Tavar"),
			fieldtype: "Link",
			options: "Item",
		},
		{
			fieldname: "item_group",
			label: __("Tavar guruhi"),
			fieldtype: "Link",
			options: "Item Group",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (
			(column.fieldname === "kirim_dona" || column.fieldname === "kirim_tannarx") &&
			flt(data.kirim_dona || data.kirim_tannarx)
		) {
			value = `<span style="color:var(--green-600,#1e7e34)">${value}</span>`;
		}
		if (
			(column.fieldname === "chiqim_dona" || column.fieldname === "chiqim_tannarx") &&
			flt(data.chiqim_dona || data.chiqim_tannarx)
		) {
			value = `<span style="color:var(--red-500,#c0392b)">${value}</span>`;
		}
		return value;
	},
};
