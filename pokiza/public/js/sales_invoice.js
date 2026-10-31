frappe.ui.form.on("Sales Invoice", {
    setup(frm) {
        setSalesItemQuery(frm);
    },

    onload(frm) {
        // Yangi hujjatda vaqt default 15:00 (qo'lda o'zgartirish mumkin).
        // Ikki alohida set_value o'rniga bitta — har set_value formani
        // qayta chizadi va `validate`/`refresh` zanjirini ishga tushiradi.
        if (frm.is_new() && !frm.doc.amended_from) {
            frm.set_value({ set_posting_time: 1, posting_time: "15:00:00" });
            gpSkladDefault(frm);
        }
    },

    refresh(frm) {
        setSalesItemQuery(frm);
    },

    customer(frm) {
        if (!frm.doc.customer) return;
        // Itemlar ham, telefon ham BITTA server chaqiruvidan keladi
        mijozMalumotiniYuklash(frm);
    },

    validate(frm) {
        nolQatorlarniTozalash(frm);
    },
});

// Mijoz telefon raqami (2026-10-13): kartochkadagi raqam schyotga tushadi,
// kassir kerak bo'lsa qo'lda o'zgartiradi. Накладная PDF'dagi "тел:" katagi
// shu maydondan oladi. Qo'lda yozilgan raqam ustiga yozilmaydi.
function telQoy(frm, tel) {
    if (!tel || frm.doc.docstatus !== 0 || frm.doc.custom_mijoz_tel) return;
    frm.set_value("custom_mijoz_tel", tel);
}

// Yangi schyotda ombor defaulti — tayyor mahsulot (ГП) skladi: Stock
// Settings'dagi umumiy default сырьё, sotuvga mos emas. Operator xohlasa
// qo'lda boshqa skladga o'zgartira oladi.
let GP_SKLAD = null; // sahifa ochiq turgancha bir marta so'raladi

function gpSkladDefault(frm) {
    if (frm.doc.set_warehouse) return; // SO'dan kelganida yozilgan bo'ladi
    const qoy = (ombor) => {
        if (ombor && frm.is_new() && !frm.doc.set_warehouse) {
            frm.set_value("set_warehouse", ombor);
        }
    };
    if (GP_SKLAD) return qoy(GP_SKLAD);
    frappe.db
        .get_value(
            "Warehouse",
            { is_group: 0, disabled: 0, name: ["like", "%ГП%"] },
            "name"
        )
        .then((r) => {
            GP_SKLAD = (r && r.message && r.message.name) || null;
            qoy(GP_SKLAD);
        });
}

// Mijoz tanlanganda jadvalga default itemlar SONI 0 bilan tushadi:
// kartochkali mijozga — kartochkadagi Aktiv qatorlar KARTOCHKA NARXI bilan,
// kartochkasizga — so'nggi 90 kun tarixi prays-list narxi bilan.
// Sotuvchi sonini kiritadi; Save/Submit oldidan soni 0 qolgan qatorlar
// avtomatik olib tashlanadi. Faqat YANGI (saqlanmagan) schyotda ishlaydi;
// mijoz almashtirilsa jadval yangi mijoz ro'yxati bilan qayta to'ldiriladi.
//
// TEZLIK (2026-10-29, sotuvchi shikoyati «schyot uzoq yuklanadi»):
// avval har qator `frappe.model.set_value("item_code", ...)` bilan
// to'ldirilardi. Har bunday set_value ERPNext'ning `item_code` handlerini
// chaqiradi, u esa SERVERGA `get_item_details` so'rovi yuboradi — QATOR
// BOSHIGA BITTA, ketma-ket, va har so'rovga butun schyot hujjati
// biriktirilgan holda. «ЧП Хаёт»da 72 Aktiv SKU bor → 72 ketma-ket
// so'rov (faqat server SQL'i 1 498 ta / 1.8 s, ustiga 72 marta tarmoq
// kechikishi va o'sib boruvchi yuk). Endi hammasi BITTA so'rovda
// (`schyot_qatorlari`, 22 SQL / 0.065 s) tayyor qilib olinadi va
// qatorlar `frm.add_child` bilan joylanadi — u qiymatlarni to'g'ridan-
// to'g'ri yozadi, handler ishga tushmaydi, demak server chaqiruvi yo'q.
function mijozMalumotiniYuklash(frm) {
    const mijoz = frm.doc.customer;
    // Jadvalni to'ldirish faqat YANGI, hali qo'lda tegilmagan schyotda;
    // telefon esa har holda kerak — shuning uchun chaqiruv baribir ketadi.
    const bosh = (frm.doc.items || []).every((r) => !r.item_code);
    const jadvalgaRuxsat =
        frm.is_new() &&
        !frm.doc.amended_from &&
        (bosh || frm.__odatiy_mijoz) &&
        frm.__odatiy_mijoz !== mijoz;
    if (!jadvalgaRuxsat && frm.doc.custom_mijoz_tel) return;
    frappe
        .call({
            method: "pokiza.api.mijoz.schyot_qatorlari",
            args: {
                customer: mijoz,
                company: frm.doc.company,
                price_list: frm.doc.selling_price_list,
                set_warehouse: frm.doc.set_warehouse,
                posting_date: frm.doc.posting_date,
            },
        })
        .then((r) => {
            const javob = r.message || {};
            if (frm.doc.customer !== mijoz) return;
            telQoy(frm, javob.tel);

            const qatorlar = javob.qatorlar || [];
            if (!jadvalgaRuxsat || !qatorlar.length) return;

            frm.clear_table("items");
            frm.__odatiy_mijoz = mijoz;
            const kartochkadan = qatorlar.some((q) => q.kartochkadan);

            qatorlar.forEach((q) => {
                // `kartochkadan` — faqat xabar matni uchun belgi, SI Item
                // maydoni emas; hujjatga yozilmasin
                const { kartochkadan: _belgi, ...maydonlar } = q;
                frm.add_child("items", maydonlar);
            });

            frm.refresh_field("items");
            // Jami summalarni BIR MARTA qayta hisoblaymiz (avval har
            // set_value'da 72 qatorli jadval uchun qaytadan hisoblanardi)
            if (frm.cscript && frm.cscript.calculate_taxes_and_totals) {
                frm.cscript.calculate_taxes_and_totals();
            }

            frappe.show_alert({
                message: kartochkadan
                    ? __("Mijoz kartochkasidan {0} ta Aktiv SKU yuklandi — sonini kiriting (0 = qator o'chadi)", [qatorlar.length])
                    : __("{0} ta odatiy item yuklandi — sotiladigan sonini kiriting (0 = qator o'chadi)", [qatorlar.length]),
                indicator: "green",
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
    // Egasi qarori 2026-10-12: kartochkali mijozga ham BUTUN sotuv guruhi
    // ochiq — kartada yo'q mahsulotni ham sotish mumkin (eski "faqat karta
    // Aktiv SKU'lari" filtri olib tashlandi; kartadagilar baribir avto
    // to'ldirishda karta narxi bilan tushadi).
    frm.set_query("item_code", "items", () => ({
        filters: {
            disabled: 0,
            is_sales_item: 1,
            item_group: "Сотув махсулотлари",
        },
    }));
}
