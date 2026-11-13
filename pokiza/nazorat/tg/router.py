"""Ichki bot update'larini qayta ishlash (webhook ham, lokal polling ham shu yerga keladi).

Bot faqat xodimlar uchun, faqat SHAXSIY chatda ishlaydi. Guruhga qo'shilsa — darhol chiqib ketadi, guruh
xabarlariga javob bermaydi. Xizmat faqat ulangan (TG Azo) foydalanuvchilarga; ko'rsatkichlar rol doirasida
(pokiza.nazorat.scope). Javob faqat so'rov kelgan chatga ketadi.
"""
import re

import frappe

from pokiza.nazorat.metrics import DavrXato, REGISTRY, compute
from pokiza.nazorat.reports import HISOBOT, TURI, davr_kalitdan, hisobot, ruxsat_turlar
from pokiza.nazorat.scope import azo_bolimi, ruxsat_kodlar
from pokiza.nazorat.tg import config, linking
from pokiza.nazorat.tg.format import esc, kpi_batafsil, qisqa
from pokiza.nazorat.tg.sender import TgXato, answer_callback, call, edit_message, send_message, send_photo, typing

# Pastki menyu tugmalari (reply keyboard) -> buyruq
MENYU = {"📅 Kunlik": "kunlik", "🗓 Haftalik": "haftalik", "📊 Oylik": "oylik",
         "📈 Ko'rsatkichlar": "kpi", "📌 Vazifalarim": "vazifalar", "➕ Vazifa berish": "vazifa",
         "👥 Xodimlar": "xodimlar"}
TUR_TUGMA = {"kunlik": "📅 Kunlik", "haftalik": "🗓 Haftalik", "oylik": "📊 Oylik"}
ULANMAGAN = ("🔒 Siz Nazorat botiga hali ulanmagansiz.\n\n"
             "ERP → o'z profilingiz → <b>Telegram'ga ulash</b> tugmasi → havolani bosing.\n"
             "Yoki administrator sizga havola yuboradi.")


def _rahbarmi(azo):
    """Vazifa bera oladimi (scope.vazifa_bera_oladimi — yagona joy)."""
    from pokiza.nazorat.scope import vazifa_bera_oladimi

    return vazifa_bera_oladimi(azo)


def menyu(azo):
    """Rolga mos pastki menyu: faqat ko'ra oladigan hisobotlar; vazifa berish faqat rahbarda."""
    bolim = azo_bolimi(azo)
    rows = []
    turlar = [TUR_TUGMA[t] for t in ruxsat_turlar(bolim)]
    if turlar:
        rows.append([{"text": t} for t in turlar])
    row = [{"text": "📈 Ko'rsatkichlar"}] if ruxsat_kodlar(bolim) else []
    row.append({"text": "📌 Vazifalarim"})
    rows.append(row)
    pastki = []
    if _rahbarmi(azo):
        pastki.append({"text": "➕ Vazifa berish"})
    from pokiza.nazorat.xodimlar import admin

    if admin(azo.user):
        pastki.append({"text": "👥 Xodimlar"})  # rol berish — faqat administrator
    if pastki:
        rows.append(pastki)
    return {"keyboard": rows, "resize_keyboard": True, "is_persistent": True}


def salom(azo, yangi=False):
    ism = frappe.db.get_value("User", azo.user, "first_name") or frappe.db.get_value("User", azo.user, "full_name") or ""
    bolim = azo_bolimi(azo)
    out = [("✅ <b>Ulandingiz!</b> " if yangi else "👋 ") + f"Salom, <b>{esc(ism)}</b>"]
    from pokiza.nazorat.scope import toliqmi

    if toliqmi(bolim):
        out.append("Siz barcha ko'rsatkichlarni ko'rasiz.")
    elif bolim:
        out.append(f"Rol: <b>{esc(bolim)}</b>")
    else:
        out.append("Rol hali biriktirilmagan — administrator biriktirgach ko'rsatkichlar ochiladi.")
    out.append("")
    out.append("Pastdagi menyudan tanlang 👇")
    if bolim and (azo.rol == "Rahbar" or azo.ai_ruxsat):
        out.append("💬 Savolni oddiy matn yoki ovozli xabar bilan ham yozishingiz mumkin.")
    return "\n".join(out)


def _azo(tid):
    name = frappe.db.get_value("TG Azo", {"telegram_id": str(tid), "faol": 1}, "name")
    return frappe.get_doc("TG Azo", name) if name else None


def _sm(user):
    return "System Manager" in frappe.get_roles(user)


def _komanda(text):
    """'/kpi@pokiza_nazorat_bot A2 kecha' -> ('kpi', ['A2', 'kecha']) yoki boshqa botga bo'lsa None."""
    m = re.match(r"^/([A-Za-z_'ʻʼ‘’`]+)(?:@(\w+))?\s*(.*)$", (text or "").strip(), re.S)
    if not m:
        return None, []
    if m[2] and m[2].lower() != config.username().lower():
        return None, []
    return re.sub(r"['ʻʼ‘’`]", "", m[1]).lower(), m[3].split()  # /so'ra -> sora


def process_update(update):
    if not config.faol():
        return
    try:
        if "callback_query" in update:
            return _callback(update["callback_query"])
        if "my_chat_member" in update:
            return _chat_member(update["my_chat_member"])
        msg = update.get("message")
        if msg and msg.get("from") and not msg["from"].get("is_bot"):
            return _message(msg)
    except frappe.ValidationError as e:
        frappe.db.rollback()
        if isinstance(e, frappe.TimestampMismatchError):
            matn = "Bu vazifa hozirgina o'zgardi — qayta bosing."
        else:
            matn = frappe.utils.strip_html(str(e))[:500] or "Amal bajarilmadi."
        cq = update.get("callback_query")
        if cq:  # tugma aylanib qolmasin
            try:
                return answer_callback(cq["id"], matn[:190], alert=True)
            except TgXato:
                pass
        chat = (update.get("message") or {}).get("chat") or {}
        if chat.get("id"):
            send_message(chat["id"], esc(matn))
    except TgXato as e:
        frappe.log_error(title="Nazorat bot: Telegram xatosi", message=str(e))
    except frappe.QueryDeadlockError:
        raise  # polling / navbat qayta urinadi
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="Nazorat bot: xato")
        cq = update.get("callback_query")
        if cq:  # tugma "aylanib" qolmasin — foydalanuvchi xatoni ko'rsin
            answer_callback(cq["id"], "Xatolik yuz berdi, qayta bosib ko'ring", alert=True)


def _message(msg):
    chat = msg["chat"]
    cmd, args = _komanda(msg.get("text"))
    if chat["type"] == "private":
        return _private(msg, cmd, args)
    return _guruhdan_chiq(chat["id"])  # bot guruhda ishlamaydi


def _private(msg, cmd, args):
    chat_id, frm = msg["chat"]["id"], msg["from"]
    if cmd == "start" and args:
        ok, res = linking.ulash(args[0], frm)
        frappe.db.commit()
        if not ok:
            return send_message(chat_id, res)
        return send_message(chat_id, salom(res, yangi=True), reply_markup=menyu(res))
    azo = _azo(frm["id"])
    if not azo:
        return send_message(chat_id, ULANMAGAN)
    frappe.set_user(azo.user)
    tid = str(frm["id"])
    if cmd is None and (msg.get("text") or "").strip() in MENYU:
        from pokiza.nazorat import vazifa

        vazifa.holat_qoy(tid, None)  # yarim qolgan suhbat (rad sababi / vazifa ustasi) bekor
        cmd, args = MENYU[msg["text"].strip()], []
    if cmd in ("start", "menu", "menyu", "yordam", "help"):
        return send_message(chat_id, salom(azo), reply_markup=menyu(azo))
    if cmd is None:
        from pokiza.nazorat import vazifa

        h = vazifa.holat_olish(tid)
        if h and msg.get("text"):
            if h.get("tur") == "rad":
                return vazifa.rad_sababi(tid, msg["text"], h)
            if h.get("tur") == "qaytar":
                return vazifa.qaytar_sababi(tid, msg["text"], h)
            if h.get("tur") == "usta":
                r = vazifa.usta_matn(tid, msg["text"], h)
                if r != vazifa.AI_GA:
                    return r
        if not (msg.get("text") or msg.get("voice") or msg.get("audio")):
            return
        if azo.rol != "Rahbar" and not azo.ai_ruxsat:
            return send_message(chat_id, "Pastdagi menyudan tanlang 👇", reply_markup=menyu(azo))
        bolim = azo_bolimi(azo)
        if not bolim:
            return send_message(chat_id, "Sizga bo'lim biriktirilmagan — AI ma'lumot bera olmaydi.")
        from pokiza.nazorat.ai_channel import savol

        return savol(msg, azo, bolim)
    if cmd == "vazifalar":
        from pokiza.nazorat import vazifa

        matn, kb = vazifa.royxat(azo)
        return send_message(chat_id, matn, reply_markup=kb)
    if cmd == "xodimlar":
        from pokiza.nazorat import xodimlar

        if not xodimlar.admin(azo.user):
            return send_message(chat_id, "Bu bo'lim faqat administrator uchun.", reply_markup=menyu(azo))
        matn, kb = xodimlar.royxat()
        return send_message(chat_id, matn, reply_markup=kb)
    if cmd == "vazifa":
        if not _rahbarmi(azo):
            return send_message(chat_id, "Vazifani rahbar beradi.", reply_markup=menyu(azo))
        from pokiza.nazorat import vazifa

        return vazifa.usta_boshla(tid, azo)
    return _buyruq(chat_id, cmd, args, azo_bolimi(azo), azo=azo)


def kpi_menyu(bolim):
    """Ko'rsatkichlar ro'yxati — tugma bilan (kod yozish shart emas). Oylik / haftalik / kunlik guruhlab."""
    ruxsat = ruxsat_kodlar(bolim)
    rows = []
    for turi, (_, kodlar) in HISOBOT.items():
        row = []
        for c in kodlar:
            if c not in ruxsat:
                continue
            row.append({"text": f"{qisqa(c)} · {TURI[turi]}",
                        "callback_data": f"k:{c}:"})
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
    return {"inline_keyboard": rows}


def _buyruq(chat_id, cmd, args, bolim, azo=None, reply_to=None):
    if cmd == "men" and azo:
        return send_message(chat_id, f"👤 {esc(azo.user)}\nRol: {esc(azo.rol)}\nBo'lim: {esc(azo.bolim or '—')}")
    if cmd in HISOBOT:
        if cmd not in ruxsat_turlar(bolim):
            return send_message(chat_id, "Bu hisobotda sizning bo'limingizga tegishli ko'rsatkich yo'q.", reply_to=reply_to)
        typing(chat_id)
        matn, kb = hisobot(cmd, bolim)
        return send_message(chat_id, matn, reply_markup=kb, reply_to=reply_to)
    if cmd == "kpi":
        ruxsat = ruxsat_kodlar(bolim)
        if not ruxsat:
            return send_message(chat_id, "Sizga bo'lim biriktirilmagan — ko'rsatkichlar yopiq.", reply_to=reply_to)
        if not args:
            return send_message(chat_id, "📈 <b>Ko'rsatkichlar</b> — qaysi birini ko'ramiz?",
                                reply_markup=kpi_menyu(bolim), reply_to=reply_to)
        code = args[0].upper()
        if code not in ruxsat:
            return send_message(chat_id, "Bu ko'rsatkich sizning bo'limingiz uchun yopiq yoki mavjud emas. Menyudan tanlang: 📈 Ko'rsatkichlar",
                                reply_to=reply_to)
        typing(chat_id)
        try:
            m = compute(code, args[1] if len(args) > 1 else None, full=True)
        except (DavrXato, ValueError) as e:
            return send_message(chat_id, esc(str(e)), reply_to=reply_to)
        return send_message(chat_id, kpi_batafsil(m), reply_markup=grafik_tugmalari(code), reply_to=reply_to)
    if cmd:
        return send_message(chat_id, "Noma'lum buyruq. Menyudan tanlang: /menu", reply_to=reply_to)


def grafik_tugmalari(code):
    spec = REGISTRY.get(code)
    tur = [t for t in ("kun", "hafta", "oy") if spec and t in spec.davrlar]
    nom = {"kun": "📈 30 kunlik grafik", "hafta": "📈 12 haftalik", "oy": "📈 12 oylik"}
    return {"inline_keyboard": [[{"text": nom[t], "callback_data": f"g:{code}:{t}"} for t in tur]]} if tur else None


def _cb_bolim(cq, chat):
    """Callback ko'rish doirasi: faqat shaxsiy chatda (bosgan a'zoning roli). Guruhda raqamli tugma yo'q."""
    if chat.get("type") == "private":
        return azo_bolimi(_azo(cq["from"]["id"]))
    return None


def _callback(cq):
    data, frm = cq.get("data") or "", cq["from"]
    msg = cq.get("message") or {}
    chat = msg.get("chat") or {}
    chat_id = str(chat.get("id", ""))
    if data.startswith("h:"):
        parts = data.split(":", 2)
        turi, kalit = parts[1], parts[2] if len(parts) > 2 else ""
        bolim = _cb_bolim(cq, chat)
        if turi not in HISOBOT or turi not in ruxsat_turlar(bolim):
            return answer_callback(cq["id"], "Bu hisobot sizga yopiq", alert=True)
        answer_callback(cq["id"], "Tayyorlanmoqda…")
        typing(chat_id)
        try:
            matn, kb = hisobot(turi, bolim, d=davr_kalitdan(turi, kalit or None))
        except (DavrXato, ValueError) as e:
            return send_message(chat_id, esc(str(e)))
        if kalit and msg.get("message_id"):
            return edit_message(chat_id, msg["message_id"], matn, reply_markup=kb)  # ◀ ▶ — shu xabarni almashtiradi
        return send_message(chat_id, matn, reply_markup=kb)
    if data.startswith(("k:", "g:")):
        parts = data.split(":")
        if len(parts) != 3:
            return answer_callback(cq["id"])
        tur, code, arg = parts
        bolim = _cb_bolim(cq, chat)
        if code not in ruxsat_kodlar(bolim):
            return answer_callback(cq["id"], "Bu ko'rsatkich sizga yopiq", alert=True)
        answer_callback(cq["id"], "Tayyorlanmoqda…")
        typing(chat_id)
        try:
            if tur == "k":
                m = compute(code, arg or None, full=True)
                return send_message(chat_id, kpi_batafsil(m), reply_markup=grafik_tugmalari(code))
            from pokiza.nazorat.charts import trend_png
            png, m = trend_png(code, arg)
            return send_photo(chat_id, png, caption=f"<b>{esc(m['nom'])}</b>")
        except (DavrXato, ValueError) as e:
            return send_message(chat_id, esc(str(e)))
    if data.startswith("xa:"):
        if chat.get("type") != "private":
            return answer_callback(cq["id"])
        from pokiza.nazorat import xodimlar

        return xodimlar.callback(cq, _azo(frm["id"]))
    if data.startswith(("vz:", "vw:", "vzt:", "xbt:")):
        from pokiza.nazorat import vazifa

        if data.startswith("vz:v:"):
            return vazifa.korsat(cq)
        if data.startswith("vz:"):
            return vazifa.callback(cq)
        azo = _azo(frm["id"])
        if not azo or not _rahbarmi(azo):
            return answer_callback(cq["id"], "Faqat vazifa bera oladiganlar", alert=True)
        frappe.set_user(azo.user)
        if data.startswith("vw:"):
            return vazifa.usta_callback(cq, azo)
        if data.startswith("xbt:"):
            return vazifa.xabar_taklif_callback(cq, azo)
        return vazifa.ai_taklif_callback(cq, azo)
    return answer_callback(cq["id"])


def _guruhdan_chiq(chat_id):
    """Bot faqat shaxsiy chatda ishlaydi: guruh/kanalga qo'shilsa jim chiqib ketadi."""
    chat_id = str(chat_id)
    try:
        call("leaveChat", {"chat_id": chat_id})
    except TgXato:
        pass
    if frappe.db.exists("TG Chat", chat_id):
        frappe.db.set_value("TG Chat", chat_id, "faol", 0)
        frappe.db.commit()


def _chat_member(upd):
    chat = upd.get("chat") or {}
    if chat.get("type") == "private":
        return
    status = (upd.get("new_chat_member") or {}).get("status")
    if status in ("member", "administrator", "restricted"):
        return _guruhdan_chiq(chat["id"])
    if status in ("left", "kicked") and frappe.db.exists("TG Chat", str(chat["id"])):
        frappe.db.set_value("TG Chat", str(chat["id"]), "faol", 0)
        frappe.db.commit()
