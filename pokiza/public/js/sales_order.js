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
