// ERPNext'ning o'z listview_settings'ini (add_fields, get_indicator, onload)
// o'chirib yubormaslik uchun uni almashtirmasdan kengaytiramiz.
(() => {
    const settings = (frappe.listview_settings["Sales Order"] =
        frappe.listview_settings["Sales Order"] || {});
    const original_onload = settings.onload;

    settings.onload = function (listview) {
        if (original_onload) {
            original_onload.call(this, listview);
        }
        listview.page.add_inner_button(__("Davr bo'yicha chop etish"), () => {
            openPeriodPrintDialog();
        });
    };
})();

function openPeriodPrintDialog() {
    const dialog = new frappe.ui.Dialog({
        title: __("Davr bo'yicha chop etish"),
        fields: [
            {
                fieldname: "from_date",
                label: __("Boshlanish sanasi"),
                fieldtype: "Date",
                reqd: 1,
                default: frappe.datetime.month_start(),
            },
            {
                fieldname: "to_date",
                label: __("Tugash sanasi"),
                fieldtype: "Date",
                reqd: 1,
                default: frappe.datetime.month_end(),
            },
            { fieldtype: "Section Break" },
            {
                fieldname: "include_draft",
                label: __("Qoralamalarni ham qo'shish"),
                fieldtype: "Check",
                default: 0,
            },
            {
                fieldname: "include_cancelled",
                label: __("Bekor qilinganlarni ham qo'shish"),
                fieldtype: "Check",
                default: 0,
            },
        ],
        primary_action_label: __("Chop etish"),
        primary_action(values) {
            // Popup blokerga tushmasligi uchun oyna klik paytida ochiladi
            const win = window.open("", "_blank");
            if (!win) {
                frappe.msgprint(__("Brauzer yangi oynani bloklab qo'ydi. Popup'ga ruxsat bering."));
                return;
            }
            win.document.write(loadingHtml());

            frappe
                .call({
                    method: "pokiza.api.sales_order_print.get_period_report_html",
                    args: values,
                })
                .then((r) => {
                    const data = r.message || {};
                    if (!data.count) {
                        win.close();
                        frappe.msgprint(__("Tanlangan davrda Sales Order topilmadi."));
                        return;
                    }
                    dialog.hide();
                    renderAndPrint(win, data.html);
                })
                .catch(() => win.close());
        },
    });

    dialog.show();
}

function loadingHtml() {
    return `<!doctype html><html><head><meta charset="utf-8"><title>${__("Yuklanmoqda")}…</title></head>
        <body style="font-family:system-ui,sans-serif;padding:40px;color:#555">${__("Yuklanmoqda")}…</body></html>`;
}

function renderAndPrint(win, html) {
    win.document.open();
    win.document.write(`<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>${__("Sotuv buyurtmalari hisoboti")}</title>
<style>${reportCss()}</style>
</head>
<body>${html}</body>
</html>`);
    win.document.close();
    win.focus();
    // Sahifa to'liq chizilishi uchun bir kadr kutamiz
    setTimeout(() => win.print(), 300);
}

function reportCss() {
    return `
    @page { size: A4; margin: 12mm 10mm; }
    * { box-sizing: border-box; }
    body { font-family: 'DejaVu Sans', system-ui, Arial, sans-serif; font-size: 11px; color: #1a1a1a; margin: 0; padding: 16px; background: #fff; }

    .report-head { display: flex; justify-content: space-between; align-items: flex-end;
        background: #0f2942; color: #fff; padding: 14px 18px; border-radius: 6px; margin-bottom: 16px; }
    .report-head h1 { font-size: 17px; margin: 3px 0 0; font-weight: 700; }
    .kicker { font-size: 9px; letter-spacing: 2px; text-transform: uppercase; opacity: .65; }
    .head-right { text-align: right; }
    .head-right .period { font-size: 12px; font-weight: 700; }
    .head-right .muted { font-size: 9px; opacity: .75; margin-top: 2px; }

    .order { border: 1px solid #d8dee5; border-radius: 5px; margin-bottom: 12px; padding: 10px 12px;
        page-break-inside: avoid; break-inside: avoid; }
    .order-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
    .order-id .doc { font-weight: 700; font-size: 12px; }
    .order-meta { font-size: 10px; color: #555; }
    .meta-item + .meta-item { margin-left: 12px; }
    .customer { font-size: 12px; margin-bottom: 7px; padding-bottom: 6px; border-bottom: 1px dashed #dde3e9; }

    .badge { display: inline-block; margin-left: 8px; padding: 1px 7px; border-radius: 9px;
        font-size: 9px; font-weight: 700; text-transform: uppercase; }
    .st-submitted { background: #e6f4ea; color: #17683a; }
    .st-draft { background: #f1f3f5; color: #666; }
    .st-cancelled { background: #fdecea; color: #a3120f; }

    table { width: 100%; border-collapse: collapse; }
    .items th { background: #eef1f4; font-size: 9px; text-transform: uppercase; letter-spacing: .4px;
        color: #4a5560; padding: 5px 7px; border-bottom: 1px solid #cfd6dd; }
    .items td { padding: 5px 7px; border-bottom: 1px solid #f0f2f4; }
    .items tbody tr:last-child td { border-bottom: none; }
    th.num, td.num { width: 26px; text-align: center; color: #8a949e; }
    th.item, td.item { text-align: left; }
    th.qty, td.qty { text-align: right; width: 80px; }
    th.uom, td.uom { text-align: left; width: 55px; color: #666; }
    th.money, td.money { text-align: right; width: 105px; white-space: nowrap; }
    td.item .code { color: #8a949e; font-size: 9px; }
    td.empty { text-align: center; color: #999; font-style: italic; padding: 10px; }

    .items tfoot td { border-top: 1.5px solid #cfd6dd; padding: 6px 7px; font-weight: 700; }
    .total-label { text-align: right; text-transform: uppercase; font-size: 9px; letter-spacing: .5px; color: #4a5560; }
    .total-value { font-size: 12px; }
    .extra { text-align: right; font-size: 10px; color: #555; margin-top: 4px; }

    .summary { margin-top: 18px; page-break-inside: avoid; break-inside: avoid; }
    .summary h2 { font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: #0f2942;
        margin: 0 0 6px; }
    .summary table { border: 1px solid #d8dee5; border-radius: 5px; overflow: hidden; }
    .summary th { background: #0f2942; color: #fff; padding: 6px 9px; font-size: 9px;
        text-transform: uppercase; letter-spacing: .5px; text-align: left; }
    .summary th, .summary td { white-space: nowrap; }
    .summary th.qty, .summary th.money { text-align: right; }
    .summary th.qty, .summary td.qty { width: 150px; }
    .summary th.money, .summary td.money { width: 180px; }
    .summary td { padding: 7px 9px; border-bottom: 1px solid #f0f2f4; font-weight: 700; }
    .summary tr:last-child td { border-bottom: none; }

    .empty-report { text-align: center; color: #888; padding: 40px; font-style: italic; }

    @media print {
        body { padding: 0; }
        .order { border-color: #ccc; }
    }
    `;
}
