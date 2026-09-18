const BOM_FINISHED_GOODS_ITEM_GROUP = "Готовый продукт";

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
    let soni = 0;
    let summa = 0;
    (frm.doc.items || []).forEach((d) => {
        soni += flt(d.qty);
        summa += flt(d.amount);
    });
    frm.set_value("custom_sarf_jami_soni", soni);
    frm.set_value("custom_sarf_jami_summa", summa);
}

function setBomItemQuery(frm) {
    frm.set_query("item", () => {
        return {
            filters: {
                disabled: 0,
                item_group: BOM_FINISHED_GOODS_ITEM_GROUP,
            },
        };
    });
}
