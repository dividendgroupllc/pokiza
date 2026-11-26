// Copyright (c) 2026, Sardorbek and contributors
// For license information, please see license.txt

// Pokiza Balans — oy oxiri holatiga boshqaruv balansi.
// «Ko'rinish» filtri 4 sahifani almashtiradi: Balans / Debitorlar / Kreditorlar / Zaxiralar
// (egasining Excel formati bilan bir xil tartib).

frappe.query_reports["Pokiza Balans"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("Dan (oy)"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.month_start(), -5),
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
			fieldname: "korinish",
			label: __("Ko'rinish"),
			fieldtype: "Select",
			options: ["Balans", "Debitorlar", "Kreditorlar", "Zaxiralar"].join("\n"),
			default: "Balans",
			reqd: 1,
		},
	],
	formatter(value, row, column, data, default_formatter) {
		if (data && data.fmt === "pct" && column.fieldname.startsWith("oy_")) {
			const v = data[column.fieldname];
			if (v == null) return "";
			return `<div style="text-align:right">${format_number(v, null, 1)}%</div>`;
		}
		value = default_formatter(value, row, column, data);
		if (data && data.bold) value = `<b>${value}</b>`;
		if (data && data.indent && column.fieldname === "korsatkich") {
			value = `<span style="padding-left:18px">${value}</span>`;
		}
		// manfiy summalar qizil (Check, dividend, kamomad darhol ko'rinsin)
		if (column.fieldname.startsWith("oy_") || column.fieldname === "ozgarish") {
			if (data && flt(data[column.fieldname]) < 0) {
				value = `<span style="color:var(--red-500,#c0392b)">${value}</span>`;
			}
		}
		return value;
	},
};
