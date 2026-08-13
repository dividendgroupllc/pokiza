frappe.ui.form.on("Telegram Bot Settings", {
	refresh(frm) {
		frm.add_custom_button(__("ℹ️ Bot holati"), () => {
			frappe.call({
				method: "pokiza.pokiza_for_business.doctype.telegram_bot_settings.telegram_bot_settings.bot_status",
				freeze: true,
				freeze_message: __("Telegram bilan bog'lanmoqda..."),
				callback(r) {
					if (!r.message) return;
					const { bot, webhook, linked_users, total_users, admins } = r.message;
					const wh_url = webhook.url
						? `<code>${webhook.url}</code>`
						: "<b style='color:red'>o'rnatilmagan</b>";
					const wh_err = webhook.last_error_message
						? `<br>⚠️ Oxirgi xato: <code>${webhook.last_error_message}</code>`
						: "";
					frappe.msgprint({
						title: __("Bot holati"),
						indicator: webhook.url ? "green" : "orange",
						message: `
							🤖 Bot: <b>@${bot.username}</b> (ID: ${bot.id})<br>
							🔗 Webhook: ${wh_url}${wh_err}<br>
							⏳ Kutilayotgan xabarlar: ${webhook.pending_update_count || 0}<br><hr>
							👥 Jami foydalanuvchilar: <b>${total_users}</b><br>
							✅ Tizimga bog'langanlar: <b>${linked_users}</b><br>
							👨‍💼 Adminlar: <b>${admins}</b>
						`,
					});
				},
			});
		});

		frm.add_custom_button(__("🔗 Webhook o'rnatish"), () => {
			frappe.call({
				method: "pokiza.pokiza_for_business.doctype.telegram_bot_settings.telegram_bot_settings.set_webhook",
				freeze: true,
				freeze_message: __("Webhook o'rnatilmoqda..."),
				callback: () => frm.reload_doc(),
			});
		});

		frm.add_custom_button(__("❌ Webhook o'chirish"), () => {
			frappe.confirm(__("Webhook o'chirilsinmi? Bot xabarlarga javob bermay qo'yadi."), () => {
				frappe.call({
					method: "pokiza.pokiza_for_business.doctype.telegram_bot_settings.telegram_bot_settings.delete_webhook",
					freeze: true,
				});
			});
		});

		frm.add_custom_button(__("👥 Telegram foydalanuvchilari"), () => {
			frappe.set_route("List", "Telegram User");
		});
	},
});
