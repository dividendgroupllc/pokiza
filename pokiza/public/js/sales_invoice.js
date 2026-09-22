frappe.ui.form.on("Sales Invoice", {
    setup(frm) {
        setSalesItemQuery(frm);
    },

    onload(frm) {
        // Yangi hujjatda vaqt default 15:00 (qo'lda o'zgartirish mumkin)
        if (frm.is_new() && !frm.doc.amended_from) {
            frm.set_value("set_posting_time", 1);
            frm.set_value("posting_time", "15:00:00");
        }
        kartaFiltrYuklash(frm);
    },

    refresh(frm) {
        setSalesItemQuery(frm);
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

// Mijoz kartochkasi bo'lsa item tanlash FAQAT undagi Aktiv SKU'lar bilan
// cheklanadi (Disabled qatorlar chiqmaydi); kartochkasiz mijozda eski
// umumiy filtr (butun sotuv guruhi) ishlayveradi.
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

// Mijoz tanlanganda jadvalga default itemlar SONI 0 bilan tushadi:
// kartochkali mijozga — kartochkadagi Aktiv qatorlar KARTOCHKA NARXI bilan,
// kartochkasizga — so'nggi 90 kun tarixi (narxni ERPNext o'zi oladi).
// Sotuvchi sonini kiritadi; Save/Submit oldidan soni 0 qolgan qatorlar
// avtomatik olib tashlanadi. Faqat YANGI (saqlanmagan) schyotda ishlaydi;
// mijoz almashtirilsa jadval yangi mijoz ro'yxati bilan qayta to'ldiriladi.
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
                        // Kartochkali mijozda narx — kartochkadan (shartnoma
                        // narxi); kartochkasizda ERPNext o'zi olib keladi.
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
                        ? __("Mijoz kartochkasidan {0} ta Aktiv SKU yuklandi — sonini kiriting (0 = qator o'chadi)", [itemlar.length])
                        : __("{0} ta odatiy item yuklandi — sotiladigan sonini kiriting (0 = qator o'chadi)", [itemlar.length]),
                    indicator: "green",
                });
            });
        });
}

// Save/Submit oldidan soni 0 qolgan qatorlar olib tashlanadi — jadvalda
// faqat operator sonini kiritgan itemlar qoladi.
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
