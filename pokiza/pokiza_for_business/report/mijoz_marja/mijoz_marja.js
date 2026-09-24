// Copyright (c) 2026, Sardorbek and contributors
// For license information, please see license.txt

frappe.query_reports["Mijoz Marja"] = {
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
			label: __("Mijoz (SKU kesimi uchun)"),
			fieldtype: "Link",
			options: "Customer",
		},
	],
};
