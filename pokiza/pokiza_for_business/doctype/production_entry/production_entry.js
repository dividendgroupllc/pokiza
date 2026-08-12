// Copyright (c) 2025, Sardorbek and contributors
// For license information, please see license.txt

const DEFAULT_PRODUCTION_WAREHOUSE = "Склад сырьё - P";
const FINISHED_GOODS_ITEM_GROUP = "Готовый продукт";

frappe.ui.form.on('Production Entry', {
    setup: function(frm) {
        frm.ignore_doctypes_on_cancel_all = ["Stock Entry"];

        frm.set_query("item_to_manufacture", function() {
            return {
                filters: {
                    item_group: FINISHED_GOODS_ITEM_GROUP
                }
            };
        });

        // Set default target warehouse for new documents
        if (frm.is_new() && !frm.doc.target_warehouse) {
            frm.set_value("target_warehouse", DEFAULT_PRODUCTION_WAREHOUSE);
        }

        // Set default company for new documents
        if (frm.is_new() && !frm.doc.company) {
            frappe.call({
                method: "frappe.client.get_default",
                args: { key: "Company" },
                callback: function(r) {
                    if (r.message) {
                        frm.set_value("company", r.message);
                    }
                }
            });
        }
    },

    refresh: function(frm) {
        // Set query for BOM - only show BOMs for selected item
        frm.set_query("bom_no", function() {
            return {
                filters: {
                    "item": frm.doc.item_to_manufacture,
                    "is_active": 1,
                    "docstatus": 1
                }
            };
        });

        // Set query for target warehouse
        frm.set_query("target_warehouse", function() {
            return {
                filters: {
                    "is_group": 0,
                    "company": frm.doc.company
                }
            };
        });

        // Add button to refresh available qty
        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__('Refresh Available Qty'), function() {
                update_all_available_qty(frm);
            });
        }
    },

    item_to_manufacture: function(frm) {
        if (frm.doc.item_to_manufacture) {
            // Get default BOM for item
            frappe.call({
                method: "pokiza.pokiza_for_business.doctype.production_entry.production_entry.get_bom_for_item",
                args: {
                    item_code: frm.doc.item_to_manufacture
                },
                callback: function(r) {
                    if (r.message) {
                        frm.set_value("bom_no", r.message);
                    } else {
                        frm.set_value("bom_no", "");
                        frappe.msgprint(__("No active BOM found for {0}", [frm.doc.item_to_manufacture]));
                    }
                }
            });
        } else {
            frm.set_value("bom_no", "");
            frm.clear_table("items");
            frm.refresh_field("items");
        }
    },

    bom_no: function(frm) {
        // Miqdor hali kiritilmagan bo'lsa ham jadval darhol ko'rinsin (1 birlik
        // uchun retsept sifatida). Yakuniy to'g'ri qiymatni baribir server
        // saqlash paytida qayta hisoblaydi — bu faqat ko'rish uchun.
        if (frm.doc.bom_no) {
            fetch_bom_items(frm);
        }
    },

    qty_to_manufacture: function(frm) {
        if (frm.doc.bom_no && frm.doc.qty_to_manufacture > 0) {
            fetch_bom_items(frm);
        }
    },

    posting_date: function(frm) {
        update_all_available_qty(frm);
    },

    posting_time: function(frm) {
        update_all_available_qty(frm);
    },

    target_warehouse: function(frm) {
        // Update all source_warehouse in items when target_warehouse changes
        if (frm.doc.target_warehouse && frm.doc.items && frm.doc.items.length > 0) {
            frm.doc.items.forEach(function(row) {
                frappe.model.set_value(row.doctype, row.name, "source_warehouse", frm.doc.target_warehouse);
            });
            frm.refresh_field("items");
            update_all_available_qty(frm);
        }
    },

    items_add: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        let warehouse = frm.doc.target_warehouse || DEFAULT_PRODUCTION_WAREHOUSE;

        if (row && warehouse && !row.source_warehouse) {
            frappe.model.set_value(cdt, cdn, "source_warehouse", warehouse);
        }
    }
});

frappe.ui.form.on('Production Entry Item', {
    item_code: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.item_code && row.source_warehouse) {
            update_available_qty(frm, row);
        }
    },

    source_warehouse: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.item_code && row.source_warehouse) {
            update_available_qty(frm, row);
        }
    },

    required_qty: function(frm, cdt, cdn) {
        // Allow manual editing, just refresh
        frm.refresh_field("items");
    }
});

function update_all_available_qty(frm) {
    if (!frm.doc.items || frm.doc.items.length === 0) return;

    frm.doc.items.forEach(function(item) {
        if (item.item_code && item.source_warehouse) {
            update_available_qty(frm, item);
        }
    });
}

function fetch_bom_items(frm) {
    // Har bir so'rovga raqam beriladi: faqat ENG OXIRGI so'rov javobi qabul qilinadi.
    // Aks holda sekin kelgan eski javob (masalan qty=1 bilan) yangi jadvalni yozib qo'yadi.
    const req_id = frm._bom_fetch_id = (frm._bom_fetch_id || 0) + 1;
    frappe.call({
        method: "pokiza.pokiza_for_business.doctype.production_entry.production_entry.get_bom_items",
        args: {
            bom_no: frm.doc.bom_no,
            qty_to_manufacture: frm.doc.qty_to_manufacture || 1,
            posting_date: frm.doc.posting_date,
            posting_time: frm.doc.posting_time,
            source_warehouse: frm.doc.target_warehouse || ""
        },
        callback: function(r) {
            if (req_id !== frm._bom_fetch_id) return;
            if (r.message) {
                frm.clear_table("items");
                r.message.forEach(function(item) {
                    let row = frm.add_child("items");
                    row.item_code = item.item_code;
                    row.item_name = item.item_name;
                    row.source_warehouse = item.source_warehouse;
                    row.required_qty = item.required_qty;
                    row.available_qty = item.available_qty;
                    row.uom = item.uom;
                });
                frm.refresh_field("items");
            }
        }
    });
}

function update_available_qty(frm, row) {
    frappe.call({
        method: "pokiza.pokiza_for_business.doctype.production_entry.production_entry.get_available_qty_for_item",
        args: {
            item_code: row.item_code,
            warehouse: row.source_warehouse,
            posting_date: frm.doc.posting_date,
            posting_time: frm.doc.posting_time
        },
        callback: function(r) {
            if (r.message !== undefined) {
                frappe.model.set_value(row.doctype, row.name, "available_qty", r.message);
            }
        }
    });
}
