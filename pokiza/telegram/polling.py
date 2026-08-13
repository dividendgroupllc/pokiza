"""Lokal test uchun polling rejimi.

Lokal kompyuterga Telegram webhook yubora olmaydi (public HTTPS yo'q),
shuning uchun bot o'zi Telegram'dan xabarlarni tortib oladi (long polling).

Ishga tushirish (bench start yonida alohida terminalda):

    bench --site pokiza.local execute pokiza.telegram.polling.run

To'xtatish: Ctrl+C. Productionda bu KERAK EMAS — u yerda webhook ishlaydi.
"""

import time

import frappe
import requests

from pokiza.telegram.config import get_bot_token, is_bot_active


def run():
    token = get_bot_token()
    if not token:
        print("❌ Bot Token kiritilmagan (Telegram Bot Settings)")
        return

    # Polling va webhook birga ishlamaydi — avval webhook'ni o'chiramiz
    requests.post(f"https://api.telegram.org/bot{token}/deleteWebhook", timeout=10)

    me = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10).json()
    if not me.get("ok"):
        print(f"❌ Token noto'g'ri: {me.get('description')}")
        return
    print(f"🤖 @{me['result']['username']} polling rejimida ishlamoqda. Ctrl+C — to'xtatish.")

    from pokiza.api.telegram_webhook import process_update

    offset = 0
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=40,
            )
            updates = r.json().get("result", [])
        except requests.RequestException as e:
            print(f"⚠️ Tarmoq xatosi: {e} — 5 soniyadan keyin qayta urinaman")
            time.sleep(5)
            continue
        except KeyboardInterrupt:
            print("\n👋 Polling to'xtatildi")
            return

        for update in updates:
            offset = update["update_id"] + 1
            if not is_bot_active():
                continue
            try:
                process_update(update)
                frappe.db.commit()
            except Exception:
                frappe.db.rollback()
                frappe.log_error(frappe.get_traceback(), "Telegram polling xatosi")
                print(f"⚠️ Update {update['update_id']} da xato — Error Log'ga yozildi")
