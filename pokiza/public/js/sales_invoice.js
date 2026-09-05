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
    },

    refresh(frm) {
        setSalesItemQuery(frm);
    },

    customer(frm) {
        if (!frm.doc.customer) return;
        odatiyItemlarniYuklash(frm);
    },
});

frappe.ui.form.on("Sales Invoice Item", {
    qty(frm, cdt, cdn) {
        // Soni 0 qilinsa qator jadvaldan o'zi yo'qoladi
        const row = locals[cdt][cdn];
        if (!row || !row.item_code || flt(row.qty) !== 0) return;
        setTimeout(() => {
            const grid_row = frm.get_field("items").grid.grid_rows_by_docname[cdn];
            if (grid_row) grid_row.remove();
            frm.refresh_field("items");
        }, 100);
    },
});

// Mijoz tanlanganda uning doim sotib oladigan itemlari (so'nggi 90 kun
// tarixidan, oxirgi soni/narxi bilan) jadvalga default tushadi. Sotuvchi
// sonini/narxini o'zgartiradi, yangi qator qo'shadi; soni 0 = qator o'chadi.
// Faqat YANGI (saqlanmagan) schyotda ishlaydi; mijoz almashtirilsa jadval
// yangi mijoz ro'yxati bilan qayta to'ldiriladi.
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

            const ishlar = itemlar.map((it) => {
                const row = frm.add_child("items");
                return frappe.model
                    .set_value(row.doctype, row.name, "item_code", it.item_code)
                    .then(() => {
                        frappe.model.set_value(row.doctype, row.name, "qty", it.qty);
                        return frappe.model.set_value(row.doctype, row.name, "rate", it.rate);
                    });
            });
            Promise.all(ishlar).then(() => {
                frm.refresh_field("items");
                frappe.show_alert({
                    message: __("{0} ta odatiy item yuklandi (so'nggi 90 kun)", [itemlar.length]),
                    indicator: "green",
                });
            });
        });
}

function setSalesItemQuery(frm) {
    frm.set_query("item_code", "items", () => {
        return {
            filters: {
                disabled: 0,
                is_sales_item: 1,
                item_group: "Сотув махсулотлари",
            },
        };
    });
}
