const PURCHASE_ITEM_GROUPS = ["Сырё", "Упаковка"];

frappe.ui.form.on("Purchase Invoice", {
    setup(frm) {
        setPurchaseItemQuery(frm);
    },

    onload(frm) {
        // Yangi hujjatda vaqt default 09:00 (qo'lda o'zgartirish mumkin)
        if (frm.is_new() && !frm.doc.amended_from) {
            frm.set_value("set_posting_time", 1);
            frm.set_value("posting_time", "09:00:00");
        }
    },

    refresh(frm) {
        setPurchaseItemQuery(frm);
    },
});

function setPurchaseItemQuery(frm) {
    frm.set_query("item_code", "items", () => {
        return {
            filters: {
                disabled: 0,
                is_purchase_item: 1,
                item_group: ["in", PURCHASE_ITEM_GROUPS],
            },
        };
    });
}
