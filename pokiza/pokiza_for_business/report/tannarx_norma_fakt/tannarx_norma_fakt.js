// Copyright (c) 2026, Sardorbek and contributors
// For license information, please see license.txt

frappe.query_reports["Tannarx Norma Fakt"] = {
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
			fieldname: "mijoz",
			label: __("Mijoz (ixtiyoriy)"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "min_farq",
			label: __("Faqat shundan katta farq, %"),
			fieldtype: "Float",
			default: 0,
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "farq_foiz" && data && data.farq_foiz != null) {
			const f = Math.abs(data.farq_foiz);
			// 10%+ — texnolog bilan normani ko'rish kerak; 5-10% — kuzatish
			const rang = f >= 10 ? "#c0392b" : f >= 5 ? "#d68910" : "#1e8449";
			value = `<b style="color:${rang}">${value}</b>`;
		}
		return value;
	},
};
