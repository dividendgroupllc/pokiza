// Copyright (c) 2026, Sardorbek and contributors
// For license information, please see license.txt

frappe.query_reports["Kartochka Tahlili"] = {
	filters: [
		{
			fieldname: "korinish",
			label: __("Кўриниш"),
			fieldtype: "Select",
			options: "To'lov intizomi\nMijozlar kesimi\nQatorlar kesimi\nO'zgarishlar jurnali",
			default: "To'lov intizomi",
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("Davr boshi (savdo/jurnal)"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -90),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("Davr oxiri"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "mijoz",
			label: __("Mijoz"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "holat",
			label: __("Kartochka holati"),
			fieldtype: "Select",
			options: "\nQoralama\nTasdiqlangan",
			depends_on: "eval:doc.korinish != \"O'zgarishlar jurnali\"",
		},
		{
			fieldname: "status",
			label: __("Qator statusi"),
			fieldtype: "Select",
			options: "\nAktiv\nDisabled",
			depends_on: "eval:doc.korinish == 'Qatorlar kesimi'",
		},
		{
			fieldname: "faqat_muammoli",
			label: __("Faqat muammolilar"),
			fieldtype: "Check",
			depends_on: "eval:doc.korinish != \"O'zgarishlar jurnali\"",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;

		const manfiy_qizil = [
			"marja_som", "marja_foiz", "min_marja", "ortacha_marja", "qarz",
		];
		if (manfiy_qizil.includes(column.fieldname) && flt(data[column.fieldname]) < 0) {
			value = `<span style="color:var(--red-500)">${value}</span>`;
		}
		// farq ustunlari: nolmas qiymat e'tibor talab qiladi
		if (["tannarx_farq", "narx_farq"].includes(column.fieldname)
			&& Math.abs(flt(data[column.fieldname])) > 1) {
			value = `<span style="color:var(--orange-500)">${value}</span>`;
		}
		if (column.fieldname === "muammolar" && data.muammolar) {
			value = `<span style="color:var(--red-500)">${value}</span>`;
		}
		if (column.fieldname === "sinxron" && data.sinxron && data.sinxron !== "✓") {
			value = `<span style="color:var(--orange-500)">${value}</span>`;
		}
		if (column.fieldname === "holat") {
			if (["Qoralama", "to'lashi kerak", "kelishuv yo'q"].includes(data.holat)) {
				value = `<span style="color:var(--orange-500)">${value}</span>`;
			} else if (data.holat === "buzildi") {
				value = `<span style="color:var(--red-500);font-weight:600">${value}</span>`;
			} else if (["bajarildi", "yaxshi"].includes(data.holat)) {
				value = `<span style="color:var(--green-600)">${value}</span>`;
			}
		}
		if (column.fieldname === "oshgan" && flt(data.oshgan) > 1000) {
			value = `<span style="color:var(--red-500)">${value}</span>`;
		}
		if (column.fieldname === "limit_holat" && data.limit_holat) {
			value = `<span style="color:var(--red-500);font-weight:600">${value}</span>`;
		}
		if (column.fieldname === "oldingi_yopilmagan" && flt(data.oldingi_yopilmagan) > 0) {
			value = `<span style="color:var(--red-500)">${value}</span>`;
		}
		return value;
	},
};
