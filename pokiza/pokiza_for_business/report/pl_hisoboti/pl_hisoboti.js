// Copyright (c) 2026, abdulloh and contributors
// For license information, please see license.txt

frappe.query_reports["PL Hisoboti"] = {
    "filters": [
        {
            "fieldname": "company",
            "label": __("Компания"),
            "fieldtype": "Link",
            "options": "Company",
            "default": frappe.defaults.get_user_default("Company") || "Pokiza",
            "reqd": 1
        },
        {
            "fieldname": "from_date",
            "label": __("Дан"),
            "fieldtype": "Date",
            "default": frappe.datetime.year_start(),
            "reqd": 1
        },
        {
            "fieldname": "to_date",
            "label": __("Гача"),
            "fieldtype": "Date",
            "default": frappe.datetime.year_end(),
            "reqd": 1
        },
        {
            "fieldname": "periodicity",
            "label": __("Давр"),
            "fieldtype": "Select",
            "options": "Yearly\nHalf-Yearly\nQuarterly\nMonthly",
            "default": "Yearly",
            "reqd": 1
        }
    ],

    "formatter": function (value, row, column, data, default_formatter) {
        const rt = data ? data.row_type : null;

        // ── Chap ustun (Кўрсаткич) — ierarxiya bo'yicha ajratilgan ──────────────
        if (column.fieldname === "label") {
            if (!data || rt === "divider") return "";
            const level = data.indent_level || 0;
            const pad = 6 + level * 22;
            let s = `padding-left:${pad}px;white-space:nowrap;`;
            if (rt === "root") {
                s += "font-weight:700;text-transform:uppercase;color:#0f2942;letter-spacing:.3px;";
            } else if (rt === "result") {
                s += "font-weight:800;color:#0b6b3a;";
            } else if (rt === "sub") {
                s += "font-weight:600;color:#334155;";
            } else if (rt === "detail") {
                s += "color:#64748b;font-size:12px;";
            } else if (rt === "percent" || rt === "ratio") {
                s += "font-style:italic;color:#94a3b8;font-size:11.5px;";
            }
            const label = frappe.utils.escape_html(data.label || "");
            return `<div style="${s}">${label}</div>`;
        }

        // ── Qiymat ustunlari ────────────────────────────────────────────────────
        if (!data || rt === "divider") return "";
        if (value === null || value === undefined || value === "") return "";
        const num = flt(value);

        // Foiz qatorlari — alohida ajralib turadi (pill)
        if (rt === "percent") {
            const v = Math.round(num);
            const bg  = v >= 0 ? "#eef4ff" : "#fef2f2";
            const clr = v >= 0 ? "#2563eb" : "#dc2626";
            return `<span style="display:inline-block;padding:1px 9px;border-radius:11px;`
                 + `background:${bg};color:${clr};font-weight:700;font-size:11px;">${v}%</span>`;
        }

        // Nisbat (средний цена за кг) — 2 xonali
        if (rt === "ratio") {
            const v = num.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            return `<span style="font-style:italic;color:#64748b;">${v}</span>`;
        }

        // Oddiy summalar — kasrsiz (.00 yo'q), mingliklar probel bilan
        let txt = Math.round(num).toLocaleString("ru-RU");
        if (data.is_qty) txt += " кг";

        let s = "";
        if (rt === "root" || rt === "result") s += "font-weight:700;";
        if (data.is_cost) {
            s += "color:#dc2626;";                          // xarajat/tannarx — qizil
        } else if (rt === "result") {
            s += (num >= 0 ? "color:#0b6b3a;" : "color:#dc2626;"); // foyda — yashil
        } else if (rt === "root") {
            s += "color:#0f2942;";                          // выручка/объём — to'q ko'k
        }
        return `<span style="${s}">${txt}</span>`;
    }
};
