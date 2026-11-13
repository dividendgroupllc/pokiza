frappe.ui.form.on("Nazorat Bot Sozlamalari", {
	refresh(frm) {
		if (frm.is_dirty()) return;
		frm.add_custom_button(__("Tekshirish va webhook o'rnatish"), () =>
			frappe.call({ method: "pokiza.nazorat.tg.setup.ornatish", freeze: true }).then((r) => {
				frappe.msgprint(r.message || "OK");
				frm.reload_doc();
			})
		);
		frm.add_custom_button(__("Webhook'ni o'chirish"), () =>
			frappe.call({ method: "pokiza.nazorat.tg.setup.ochirish", freeze: true }).then((r) => {
				frappe.msgprint(r.message || "OK");
				frm.reload_doc();
			})
		);
	},
});
