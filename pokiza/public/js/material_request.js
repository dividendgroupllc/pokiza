// Material Request (turi Manufacture) = ZAPAS ishlab chiqarish (2026-09-25).
// Mijoz YO'Q — bu ERPNext'ning make-to-stock standarti. Sotuv itemlari
// filtri, kg semantikasi va 3 qog'oz (har bo'limga alohida) shu yerda.
(function () {

// Manufacture (zapas) turida item tanlash FAQAT sotuv mahsulotlari bilan
// cheklanadi. ERPNext'ning o'z skripti ham shu maydonga query o'rnatadi —
// shuning uchun har refresh/tur o'zgarishida QAYTA o'rnatiladi (oxirgi
// o'rnatilgani g'olib). Server tomonda zapas_before_submit baribir
// qattiq tekshiradi.
function zapasItemFiltr(frm) {
    frm.set_query("item_code", "items", () => {
        if (frm.doc.material_request_type !== "Manufacture") {
            return { query: "erpnext.controllers.queries.item_query" };
        }
        return {
            query: "erpnext.controllers.queries.item_query",
            filters: {
                disabled: 0,
                item_group: "Сотув махсулотлари",
            },
        };
    });
}

frappe.ui.form.on("Material Request", {
    setup(frm) {
        zapasItemFiltr(frm);
    },

    onload(frm) {
        // Zakaz sahifasidan «Zapas» tugmasi bilan kelinganda turi tayyor
        if (frm.is_new() && !frm.doc.material_request_type) {
            frm.set_value("material_request_type", "Manufacture");
        }
        zapasItemFiltr(frm);
    },

    material_request_type(frm) {
        zapasItemFiltr(frm);
    },

    refresh(frm) {
        zapasItemFiltr(frm);
        if (
            frm.doc.docstatus === 1 &&
            frm.doc.material_request_type === "Manufacture"
        ) {
            const chiqar = (qaysi) => zapasQogoz(frm, qaysi);
            frm.add_custom_button(__("1 · Farsh rejasi"), () => chiqar("farsh"), __("🖨 Qog'ozlar"));
            frm.add_custom_button(__("2 · Shprits rejasi"), () => chiqar("shprits"), __("🖨 Qog'ozlar"));
            frm.add_custom_button(__("3 · Tarozi varaqasi"), () => chiqar("tarozi"), __("🖨 Qog'ozlar"));
        }
    },
});

function zapasQogoz(frm, qaysi) {
    frappe
        .call({
            method: "pokiza.api.navbat.zapas_qogozlari",
            args: { material_request: frm.doc.name },
        })
        .then((r) => {
            const d = r.message;
            if (!d || !(d.farsh || []).length) {
                frappe.show_alert({
                    message: __("Ishlab chiqariladigan qism yo'q"),
                    indicator: "orange",
                });
                return;
            }
            const w = window.open("", "_blank");
            if (!w) {
                frappe.msgprint(__("Brauzer yangi oynani blokladi — ruxsat bering"));
                return;
            }
            w.document.write(zapasQogozHtml(d, qaysi));
            w.document.close();
            w.focus();
            setTimeout(() => w.print(), 400);
        });
}

function zEsc(t) {
    return String(t == null ? "" : t)
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function zapasQogozHtml(d, qaysi) {
    const fmt = (v) => format_number(flt(v), null, flt(v) % 1 ? 1 : 0);
    const bosh = `${zEsc(d.mijoz)} · ${zEsc(d.so)} · ${zEsc(d.sana)}`;

    let sarlavha, jadval;
    if (qaysi === "farsh") {
        sarlavha = "1-QOG'OZ · FARSH ISHLAB CHIQARISH REJASI (texnolog)";
        jadval = `<table><tr><th>Norma / retsept</th><th class="num">Kg</th><th class="num">Zames</th></tr>
            ${d.farsh.map((f) => `<tr><td>${zEsc(f.norma)}</td>
                <td class="num">${fmt(f.kg)}</td><td class="num">${f.zames}</td></tr>`).join("")}
            </table>
            <div class="imzo">Texnolog: ________________ &nbsp; Imzo: ________ &nbsp; Vaqt: ________</div>`;
    } else if (qaysi === "shprits") {
        sarlavha = "2-QOG'OZ · SHPRITS REJASI";
        jadval = `<table><tr><th colspan="2">Norma → SKU</th><th class="num">Kg</th></tr>
            ${d.shprits.map((n) => `
                <tr class="norma-row"><td colspan="2"><b>${zEsc(n.norma)}</b></td>
                    <td class="num"><b>${fmt(n.jami)} kg</b></td></tr>
                ${n.skular.map((s) => `<tr><td class="indent"></td><td>${zEsc(s.nom)}</td>
                    <td class="num">${fmt(s.kg)}</td></tr>`).join("")}`).join("")}
            </table>
            <div class="imzo">Shpritschi: ________________ &nbsp; Imzo: ________ &nbsp; Vaqt: ________</div>`;
    } else {
        sarlavha = "3-QOG'OZ · TAROZI VARAQASI";
        jadval = `<table><tr><th>Mahsulot (SKU)</th><th>Norma</th><th class="num">Reja kg</th><th>Fakt kg</th><th>Izoh</th></tr>
            ${d.tarozi.map((t) => t.normalar.map((n, i) => `
                <tr>${i === 0 ? `<td rowspan="${t.normalar.length}">${zEsc(t.nom)}</td>` : ""}
                    <td>${zEsc(n.norma)}</td><td class="num">${fmt(n.kg)}</td>
                    <td class="fakt"></td><td class="fakt"></td></tr>`).join("")).join("")}
            </table>
            <div class="imzo">Tarozichi: ________________ &nbsp; Imzo: ________ &nbsp; Vaqt: ________</div>`;
    }

    return `<!doctype html><html><head><meta charset="utf-8">
        <title>${zEsc(d.so)} — zapas qog'oz</title>
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

})();
