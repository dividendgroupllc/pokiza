frappe.query_reports["Kirim Hisoboti"] = {
    "filters": [
        {
            "fieldname": "from_date",
            "label": __("Сана дан"),
            "fieldtype": "Date",
            "default": frappe.datetime.month_start(),
            "reqd": 1
        },
        {
            "fieldname": "to_date",
            "label": __("Сана гача"),
            "fieldtype": "Date",
            "default": frappe.datetime.get_today(),
            "reqd": 1
        },
        {
            "fieldname": "supplier",
            "label": __("Таъминотчи"),
            "fieldtype": "Link",
            "options": "Supplier"
        }
    ],

    "formatter": function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        // Currency fieldlarida $ ni olib tashlash
        if (column.fieldtype == "Currency" && value) {
            value = value.replace(/\$/g, '');
        }

        // Total qatorini highlight qilish
        if (data && data.is_total_row) {
            value = `<span style="font-weight: bold; background-color: #e3f2fd;">${value}</span>`;
        }

        return value;
    }
}
