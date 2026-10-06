// Copyright (c) 2026, Sardorbek and contributors
// For license information, please see license.txt

// Ombor qoldig'i (fakt) — daraxt: guruh (yig'ma) → itemlar.
// Guruh qatori bosilsa ochiladi/yopiladi (moliyaviy hisobotlardagi kabi).

frappe.query_reports["Ombor Qoldigi Fakt"] = {
	filters: [
		{
			fieldname: "warehouse",
			label: __("Ombor"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query: () => ({ filters: { is_group: 0, disabled: 0 } }),
		},
		{
			fieldname: "item_group",
			label: __("Guruh"),
			fieldtype: "Link",
			options: "Item Group",
		},
		{
			fieldname: "nol_korsat",
			label: __("Nol qoldiqni ham ko'rsatish"),
			fieldtype: "Check",
			default: 0,
		},
	],
	tree: true,
	name_field: "nomi",
	parent_field: "ota",
	initial_depth: 1,
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.is_group) {
			value = `<b>${value}</b>`;
		}
		// manfiy qoldiq — qizil (omborchi darhol ko'rsin)
		if (column.fieldname === "qoldiq" && data && flt(data.qoldiq) < 0) {
			value = `<span style="color:var(--red-500,#c0392b)">${value}</span>`;
		}
		return value;
	},
};
