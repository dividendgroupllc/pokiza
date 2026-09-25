// Sales Order — mijoz kartochkasi bilan ishlash (2026-09-24, egasi talabi).
// Schyot (sales_invoice.js) bilan bir xil qoidalar:
//   - kartochkali mijoz tanlanganda jadvalga kartochkadagi AKTIV SKU'lar
//     soni 0 va KARTOCHKA NARXI bilan avto-tushadi (Disabled tushmaydi);
//   - item tanlash faqat kartochkadagi Aktiv SKU'lar bilan cheklanadi;
//   - kartochkasiz mijozga eski usul: 90 kunlik tarix, umumiy filtr;
//   - Save/Submit oldidan soni 0 qolgan qatorlar avtomatik o'chadi.
// Server tomonda zakaz_yarat/kartochka API'lari baribir qayta tekshiradi.
// IIFE: sales_invoice.js dagi bir xil nomli funksiyalar bilan global
// to'qnashuv bo'lmasligi uchun (ikkalasi bitta bundle'ga tushadi).
(function () {

frappe.ui.form.on("Sales Order", {
    setup(frm) {
        setSalesItemQuery(frm);
    },

    onload(frm) {
        kartaFiltrYuklash(frm);
    },

    refresh(frm) {
        setSalesItemQuery(frm);

        // Zapas (omborga) ishlab chiqarish — mijozsiz STANDART hujjat:
        // Material Request (turi Manufacture). SO bilan adashtirmaslik
        // uchun shu yerdan yo'naltiramiz.
        if (frm.is_new() && !frm.doc.customer) {
            frm.add_custom_button(__("📦 Zapas (omborga) — Material Request"), () => {
                frappe.new_doc("Material Request", {
                    material_request_type: "Manufacture",
                });
            });
        }

        // Tasdiqlangan zakazdan 3 qog'oz — har bo'limga ALOHIDA chiqariladi
        if (frm.doc.docstatus === 1) {
            const chiqar = (qaysi) => qogozniChiqar(frm, qaysi);
            frm.add_custom_button(__("1 · Farsh rejasi"), () => chiqar("farsh"), __("🖨 Qog'ozlar"));
            frm.add_custom_button(__("2 · Shprits rejasi"), () => chiqar("shprits"), __("🖨 Qog'ozlar"));
            frm.add_custom_button(__("3 · Tarozi varaqasi"), () => chiqar("tarozi"), __("🖨 Qog'ozlar"));
        }
    },

    customer(frm) {
        if (!frm.doc.customer) return;
        kartaFiltrYuklash(frm);
        odatiyItemlarniYuklash(frm);
    },

    validate(frm) {
        nolQatorlarniTozalash(frm);
    },
});

function kartaFiltrYuklash(frm) {
    const mijoz = frm.doc.customer;
    frm.__karta_skular = null;
    if (!mijoz) return;
    frappe
        .call({ method: "pokiza.api.kartochka.aktiv_itemlar", args: { mijoz } })
        .then((r) => {
            if (frm.doc.customer !== mijoz) return;
            const itemlar = r.message || [];
            frm.__karta_skular = itemlar.length ? itemlar.map((it) => it.sku) : null;
        });
}

function odatiyItemlarniYuklash(frm) {
    if (!frm.is_new() || frm.doc.amended_from) return;
    const bosh = (frm.doc.items || []).every((r) => !r.item_code);
    // Qo'lda kiritilgan jadvalga tegmaymiz (avto to'ldirilgan bo'lsa almashtiramiz)
    if (!bosh && !frm.__odatiy_mijoz) return;
    if (frm.__odatiy_mijoz === frm.doc.customer) return;

    const mijoz = frm.doc.customer;
    frappe
        .call({ method: "pokiza.api.mijoz.odatiy_itemlar", args: { customer: mijoz } })
        .then((r) => {
            const itemlar = r.message || [];
            if (frm.doc.customer !== mijoz || !itemlar.length) return;
            frm.clear_table("items");
            frm.__odatiy_mijoz = mijoz;
            const kartochkadan = itemlar.some((it) => it.kartochkadan);

            const ishlar = itemlar.map((it) => {
                const row = frm.add_child("items");
                return frappe.model
                    .set_value(row.doctype, row.name, "item_code", it.item_code)
                    .then(() => frappe.model.set_value(row.doctype, row.name, "qty", 0))
                    .then(() => {
                        if (it.kartochkadan && flt(it.rate)) {
                            return frappe.model.set_value(
                                row.doctype, row.name, "rate", it.rate
                            );
                        }
                    });
            });
            Promise.all(ishlar).then(() => {
                frm.refresh_field("items");
                frappe.show_alert({
                    message: kartochkadan
                        ? __("Mijoz kartochkasidan {0} ta Aktiv SKU yuklandi — sonini (kg) kiriting (0 = qator o'chadi)", [itemlar.length])
                        : __("{0} ta odatiy item yuklandi — sonini kiriting (0 = qator o'chadi)", [itemlar.length]),
                    indicator: "green",
                });
            });
        });
}

function nolQatorlarniTozalash(frm) {
    const items = frm.doc.items || [];
    const qoladigan = items.filter((r) => !r.item_code || flt(r.qty) !== 0);
    if (qoladigan.length === items.length) return;
    if (!qoladigan.some((r) => r.item_code)) {
        frappe.throw(
            __("Hamma itemning soni 0 — hech bo'lmaganda bittasining sonini kiriting.")
        );
    }
    const olib_tashlandi = items.length - qoladigan.length;
    frm.doc.items = qoladigan;
    frm.doc.items.forEach((r, i) => (r.idx = i + 1));
    frm.refresh_field("items");
    frappe.show_alert({
        message: __("Soni 0 bo'lgan {0} ta qator olib tashlandi", [olib_tashlandi]),
        indicator: "orange",
    });
}

// ---------------------------------------------------------- 3 QOG'OZ (SO)
// Zakaz tasdiqlangach har bo'lim o'z qog'ozini ALOHIDA chop etadi:
// texnolog — farsh, shpritschi — taqsimot, tarozichi — fakt varaqasi.
function qogozniChiqar(frm, qaysi) {
    frappe
        .call({
            method: "pokiza.api.navbat.so_qogozlari",
            args: { sales_order: frm.doc.name },
        })
        .then((r) => {
            const d = r.message;
            if (!d || !(d.farsh || []).length) {
                frappe.show_alert({
                    message: __("Bu zakazda ishlab chiqariladigan qism yo'q"),
                    indicator: "orange",
                });
                return;
            }
            const w = window.open("", "_blank");
            if (!w) {
                frappe.msgprint(__("Brauzer yangi oynani blokladi — ruxsat bering"));
                return;
            }
            w.document.write(soQogozHtml(d, qaysi));
            w.document.close();
            w.focus();
            setTimeout(() => w.print(), 400);
        });
}

function soEsc(t) {
    return String(t == null ? "" : t)
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function soQogozHtml(d, qaysi) {
    const fmt = (v) => format_number(flt(v), null, flt(v) % 1 ? 1 : 0);
    const bosh = `${soEsc(d.mijoz)} · ${soEsc(d.so)} · ${soEsc(d.sana)}` +
        (d.ombordan_kg ? ` · ${__("ombordan")}: ${fmt(d.ombordan_kg)} kg` : "");

    let sarlavha, jadval;
    if (qaysi === "farsh") {
        sarlavha = "1-QOG'OZ · FARSH ISHLAB CHIQARISH REJASI (texnolog)";
        jadval = `<table><tr><th>Norma / retsept</th><th class="num">Kg</th><th class="num">Zames</th></tr>
            ${d.farsh.map((f) => `<tr><td>${soEsc(f.norma)}</td>
                <td class="num">${fmt(f.kg)}</td><td class="num">${f.zames}</td></tr>`).join("")}
            </table>
            <div class="imzo">Texnolog: ________________ &nbsp; Imzo: ________ &nbsp; Vaqt: ________</div>`;
    } else if (qaysi === "shprits") {
        sarlavha = "2-QOG'OZ · SHPRITS REJASI";
        jadval = `<table><tr><th colspan="2">Norma → SKU</th><th class="num">Kg</th></tr>
            ${d.shprits.map((n) => `
                <tr class="norma-row"><td colspan="2"><b>${soEsc(n.norma)}</b></td>
                    <td class="num"><b>${fmt(n.jami)} kg</b></td></tr>
                ${n.skular.map((s) => `<tr><td class="indent"></td><td>${soEsc(s.nom)}</td>
                    <td class="num">${fmt(s.kg)}</td></tr>`).join("")}`).join("")}
            </table>
            <div class="imzo">Shpritschi: ________________ &nbsp; Imzo: ________ &nbsp; Vaqt: ________</div>`;
    } else {
        sarlavha = "3-QOG'OZ · TAROZI VARAQASI";
        jadval = `<table><tr><th>Mahsulot (SKU)</th><th>Norma</th><th class="num">Reja kg</th><th>Fakt kg</th><th>Izoh</th></tr>
            ${d.tarozi.map((t) => t.normalar.map((n, i) => `
                <tr>${i === 0 ? `<td rowspan="${t.normalar.length}">${soEsc(t.nom)}</td>` : ""}
                    <td>${soEsc(n.norma)}</td><td class="num">${fmt(n.kg)}</td>
                    <td class="fakt"></td><td class="fakt"></td></tr>`).join("")).join("")}
            </table>
            <div class="imzo">Tarozichi: ________________ &nbsp; Imzo: ________ &nbsp; Vaqt: ________</div>`;
    }

    return `<!doctype html><html><head><meta charset="utf-8">
        <title>${soEsc(d.so)} — qog'oz</title>
        <style>
            body { font-family: Arial, sans-serif; font-size: 13px; margin: 24px; color: #000; }
            h2 { margin: 0 0 2px; font-size: 17px; }
            .sub { color: #444; margin-bottom: 10px; font-size: 12px; }
            table { width: 100%; border-collapse: collapse; margin-bottom: 8px; }
            th, td { border: 1px solid #999; padding: 5px 8px; text-align: left; }
            th { background: #eee; }
            .num { text-align: right; white-space: nowrap; }
            .fakt { width: 90px; }
            .indent { width: 20px; border-right: none; }
            .norma-row td { background: #f5f5f5; }
            .imzo { margin: 14px 0 0; font-size: 12px; }
        </style></head><body>
        <h2>${sarlavha}</h2>
        <div class="sub">${bosh} · jami ${fmt(d.jami_kg)} kg</div>
        ${jadval}
        </body></html>`;
}

function setSalesItemQuery(frm) {
    frm.set_query("item_code", "items", () => {
        // Kartochkali mijoz: faqat kartochkadagi Aktiv SKU'lar
        if (frm.__karta_skular && frm.__karta_skular.length) {
            return { filters: { name: ["in", frm.__karta_skular] } };
        }
        return {
            filters: {
                disabled: 0,
                is_sales_item: 1,
                item_group: "Сотув махсулотлари",
            },
        };
    });
}

})();
