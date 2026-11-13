"""Lokal test: webhook o'rniga long polling (public HTTPS yo'q joyda).

    bench --site pokiza.local execute pokiza.nazorat.tg.polling.run

Prod'da KERAK EMAS — u yerda webhook. Polling boshlanishi webhook'ni o'chiradi.
"""
import time

import frappe

from pokiza.nazorat.tg import config
from pokiza.nazorat.tg.router import process_update
from pokiza.nazorat.tg.sender import TgXato, call


def run():
    if not config.token():
        print("❌ Token kiritilmagan (Nazorat Bot Sozlamalari)")
        return
    call("deleteWebhook")
    me = call("getMe")
    print(f"🤖 @{me['username']} polling rejimida. Ctrl+C — to'xtatish.")
    offset = 0
    while True:
        try:
            ups = call("getUpdates", {"offset": offset, "timeout": 30,
                                      "allowed_updates": ["message", "callback_query", "my_chat_member"]},
                       timeout=40, urinish=0) or []
        except TgXato as e:
            print(f"⚠️ {e} — 5 s dan keyin qayta")
            time.sleep(5)
            continue
        except KeyboardInterrupt:
            print("\n👋 To'xtatildi")
            return
        for u in ups:
            offset = u["update_id"] + 1
            for urinish in (1, 2):
                # getUpdates 30 s kutadi — shu vaqtdagi eski tranzaksiya "surati"ni tashlab, yangisidan boshlaymiz,
                # aks holda worker o'zgartirgan yozuvni saqlashda "Record has changed since last read" chiqadi
                frappe.db.rollback()
                try:
                    frappe.set_user("Guest")
                    frappe.clear_document_cache(config.DOCTYPE, config.DOCTYPE)
                    process_update(u)
                    frappe.db.commit()
                    break
                except frappe.QueryDeadlockError:
                    frappe.db.rollback()
                    if urinish == 2:
                        frappe.log_error(title="Nazorat bot polling xatosi")
                except Exception:
                    frappe.db.rollback()
                    frappe.log_error(title="Nazorat bot polling xatosi")
                    print(f"⚠️ update {u['update_id']} xato — Error Log")
                    break
