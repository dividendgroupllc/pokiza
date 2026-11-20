const BOM_FINISHED_GOODS_ITEM_GROUP = "Готовый продукт";
// 2026-11: ГП itemlari «Фарш» guruhiga ko'chirildi
const BOM_FARSH_ITEM_GROUP = "Фарш";
// Sotuv guruhi endi daraxt (Сосиски, Полукопченые... bola guruhlar) —
// to'liq ro'yxat serverdan bir marta olinadi, kelguncha statik zaxira
let BOM_ITEM_GURUHLARI = [BOM_FINISHED_GOODS_ITEM_GROUP, BOM_FARSH_ITEM_GROUP, "Сотув махсулотлари"];
frappe.call("pokiza.guruhlar.bom_item_guruhlari").then((r) => {
    if (Array.isArray(r.message) && r.message.length) BOM_ITEM_GURUHLARI = r.message;
});

frappe.ui.form.on("BOM", {
    setup(frm) {
        setBomItemQuery(frm);
    },

    refresh(frm) {
        setBomItemQuery(frm);
        hisoblaSarfJami(frm);
    },
});

frappe.ui.form.on("BOM Item", {
    qty(frm) {
        hisoblaSarfJami(frm);
    },
    rate(frm) {
        hisoblaSarfJami(frm);
    },
    amount(frm) {
        hisoblaSarfJami(frm);
    },
    items_add(frm) {
        hisoblaSarfJami(frm);
    },
    items_remove(frm) {
        hisoblaSarfJami(frm);
    },
});

function hisoblaSarfJami(frm) {
    // FAQAT qoralamada: submit'dan keyin qayta hisoblash JS float dumi
    // tufayli "Cannot Update After Submit" xatosiga olib keladi
    if (frm.doc.docstatus !== 0) return;
    let soni = 0;
    let summa = 0;
    (frm.doc.items || []).forEach((d) => {
        soni += flt(d.qty);
        summa += flt(d.amount);
    });
    // server (events/bom.py) bilan BIR XIL yaxlitlash — aks holda forma
    // har ochilganda "Not Saved" bo'lib, Submit tugmasi chiqmay qoladi
    frm.set_value("custom_sarf_jami_soni", flt(soni, 6));
    frm.set_value("custom_sarf_jami_summa", flt(summa, 2));
}

function setBomItemQuery(frm) {
    frm.set_query("item", () => {
        return {
            filters: {
                disabled: 0,
                // farsh BOM'lari + sotuv SKU BOM'lari (sodda rejim 2026-10)
                item_group: ["in", BOM_ITEM_GURUHLARI],
            },
        };
    });
}
