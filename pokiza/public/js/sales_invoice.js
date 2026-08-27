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
});

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
