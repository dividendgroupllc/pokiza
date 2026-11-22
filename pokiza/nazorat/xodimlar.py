"""Botdan xodimlarni boshqarish — FAQAT administrator (System Manager).

"👥 Xodimlar" menyusi: xodimni tanlash → rol (Nazorat Roli), AI bilan savol-javob, 08:00 hisobotlari, faol/o'chiq.
Xavfsizlik:
- har bir tugma bosilganda administratorlik qayta tekshiriladi (menyu eskirgan bo'lsa ham);
- to'liq ruxsatli rol (barcha ko'rsatkich, foyda, dividend, vazifa berish) alohida tasdiq bilan beriladi;
- administrator o'z rolini o'zgartira olmaydi va o'zini o'chira olmaydi;
- o'zgarish administrator nomidan saqlanadi (TG Azo tarixi) + izoh yoziladi, xodimga botda xabar boradi.
Callback'da ERP email emas, qisqa vaqtinchalik belgi ishlatiladi (Telegram 64 bayt chegarasi).
"""
import secrets

import frappe

from pokiza.nazorat.scope import RAHBAR, azo_bolimi, rol, rollar
from pokiza.nazorat.tg.format import esc
from pokiza.nazorat.tg.sender import TgXato, answer_callback, edit_message, send_message

TOK_TTL = 86400


def admin(user):
    return bool(user) and (user == "Administrator" or "System Manager" in frappe.get_roles(user))


def _tok(user):
    t = secrets.token_urlsafe(6)
    frappe.cache.set_value(f"nz_xa:{t}", user, expires_in_sec=TOK_TTL)
    return t


def _rtok(nom):
    """Rol nomi uchun qisqa belgi (callback 64 bayt; nom indeks emas — ro'yxat o'zgarsa ham to'g'ri rol)."""
    t = secrets.token_urlsafe(4)
    frappe.cache.set_value(f"nz_xr:{t}", nom, expires_in_sec=TOK_TTL)
    return t


def _rol_nomi_tokdan(t):
    """'-' — rolsiz (None); topilmasa/rol o'chirilgan — False."""
    if t == "-":
        return None
    nom = frappe.cache.get_value(f"nz_xr:{t}", expires=True)
    return nom if nom and rol(nom) else False


def _user(tok):
    return frappe.cache.get_value(f"nz_xa:{tok}", expires=True)


def _ism(user):
    return frappe.db.get_value("User", user, "full_name") or user


def _rol_nomi(a):
    return azo_bolimi(frappe._dict(a, faol=1)) or "rolsiz"


# ---------- ko'rinishlar ----------
def royxat():
    rows = frappe.get_all("TG Azo", fields=["user", "rol", "bolim", "faol"], order_by="faol desc, modified desc",
                          limit=80)
    rows.sort(key=lambda a: (not a.faol, _ism(a.user).lower()))
    kb = [[{"text": f"{'' if a.faol else '⛔ '}{_ism(a.user)[:28]} — {_rol_nomi(a)}",
            "callback_data": f"xa:v:{_tok(a.user)}"}] for a in rows]
    matn = (f"👥 <b>Xodimlar</b> · {len(rows)} ta\n\nXodimni tanlang — rol, AI ruxsati va hisobotlarni shu yerda "
            "o'zgartirasiz.\n<i>Ro'yxatda faqat botga ulanganlar. Yangi xodim avval ERP'dan ulanadi.</i>")
    return matn, {"inline_keyboard": kb}


def kartochka(user, admin_user):
    a = frappe.get_doc("TG Azo", user)
    t = _tok(user)
    oziniki = user == admin_user
    tg = f"@{esc(a.username)}" if a.username else esc(a.ism or "—")
    matn = "\n".join([
        f"👤 <b>{esc(_ism(user))}</b>",
        f"ERP: {esc(user)}",
        f"Telegram: {tg}",
        "",
        f"🎭 Rol: <b>{esc(_rol_nomi(a.as_dict()))}</b>",
        f"🤖 AI bilan savol-javob: {'✅ yoqilgan' if a.ai_ruxsat or a.rol == 'Rahbar' else '❌ yopiq'}",
        f"📅 08:00 hisobotlari: {'✅ keladi' if a.hisobot_olsin or a.rol == 'Rahbar' else '❌ kelmaydi'}",
        "Holat: " + ("🟢 faol" if a.faol else "⛔ o'chirilgan"),
    ] + (["", "<i>O'z rolingizni va holatingizni bu yerdan o'zgartira olmaysiz.</i>"] if oziniki else []))
    kb = []
    if not oziniki:
        kb.append([{"text": "🎭 Rolni o'zgartirish", "callback_data": f"xa:r:{t}"}])
    if a.rol != "Rahbar":
        kb.append([{"text": "🤖 AI: " + ("o'chirish" if a.ai_ruxsat else "yoqish"), "callback_data": f"xa:ai:{t}"},
                   {"text": "📅 Hisobot: " + ("o'chirish" if a.hisobot_olsin else "yoqish"), "callback_data": f"xa:hs:{t}"}])
    if not oziniki:
        kb.append([{"text": "⛔ Botdan uzish" if a.faol else "✅ Qayta yoqish", "callback_data": f"xa:f:{t}"}])
    kb.append([{"text": "◀ Ro'yxat", "callback_data": "xa:l:0"}])
    return matn, {"inline_keyboard": kb}


def rol_tanlash(user):
    a = frappe.get_doc("TG Azo", user)
    joriy = azo_bolimi(frappe._dict(a.as_dict(), faol=1))
    t = _tok(user)
    kb = []
    for nom in rollar():
        r = rol(nom)
        belgi = "✓ " if nom == joriy else ""
        kalit = " 🔑" if r and r.toliq_ruxsat else ""
        kb.append([{"text": f"{belgi}{nom}{kalit}", "callback_data": f"xa:rs:{t}:{_rtok(nom)}"}])
    kb.append([{"text": ("✓ " if not joriy else "") + "Rolsiz (hech narsa ko'rmaydi)", "callback_data": f"xa:rs:{t}:-"}])
    kb.append([{"text": "◀ Orqaga", "callback_data": f"xa:v:{t}"}])
    return (f"🎭 <b>{esc(_ism(user))}</b> uchun rol tanlang\n\n🔑 — to'liq ruxsat: barcha ko'rsatkichlar, foyda, "
            "dividend, vazifa berish."), {"inline_keyboard": kb}


# ---------- o'zgartirish ----------
def _qollash(user, admin_user, tavsif, **qiymat):
    doc = frappe.get_doc("TG Azo", user)
    doc.update(qiymat)
    doc.save(ignore_permissions=True)  # sessiya — administrator: TG Azo tarixida kim o'zgartirgani ko'rinadi
    doc.add_comment("Info", f"Telegram bot orqali {_ism(admin_user)}: {tavsif}")
    frappe.db.commit()
    return doc


def _xabar(doc, matn, menyu_yangila=True):
    """Xodimga o'zgarish haqida xabar; menyusi yangi roliga moslanadi."""
    if not doc.telegram_id:
        return
    from pokiza.nazorat.tg.router import menyu

    try:
        kb = menyu(doc) if (menyu_yangila and doc.faol) else {"remove_keyboard": True}
        send_message(doc.telegram_id, matn, reply_markup=kb)
    except TgXato:
        pass


def _rol_ber(user, admin_user, nom):
    if nom is False:
        raise frappe.ValidationError("Rol topilmadi — ro'yxatni qayta oching")
    qiymat = {"rol": "Rahbar", "bolim": RAHBAR} if nom == RAHBAR else {"rol": "Xodim", "bolim": nom}
    doc = _qollash(user, admin_user, f"rol → {nom or 'rolsiz'}", **qiymat)
    frappe.cache.delete_value(f"nz_holat:{doc.telegram_id}")  # yarim qolgan suhbat (vazifa ustasi va h.k.) bekor
    if nom:
        _xabar(doc, f"🎭 Rolingiz o'zgardi: <b>{esc(nom)}</b>\n\nMenyu yangilandi 👇")
    else:
        _xabar(doc, "🎭 Rolingiz olib tashlandi — ko'rsatkichlar yopiq. Vazifalar avvalgidek ishlaydi.")


def _rol_tasdiq(user, nom):
    t = _tok(user)
    return (f"⚠️ <b>{esc(nom)}</b> — to'liq ruxsatli rol.\n\n{esc(_ism(user))} barcha ko'rsatkichlarni, foyda va "
            "dividendni ko'radi, AI'ga cheklovsiz savol bera oladi va vazifa beradi.\n\nTasdiqlaysizmi?"), {
        "inline_keyboard": [[{"text": "✅ Ha, beraman", "callback_data": f"xa:rk:{t}:{_rtok(nom)}"},
                             {"text": "Bekor", "callback_data": f"xa:v:{t}"}]]}


def callback(cq, azo):
    """xa:<amal>:<belgi>[:<rol>] — har bosishda administratorlik qayta tekshiriladi."""
    msg = cq.get("message") or {}
    chat_id, mid = (msg.get("chat") or {}).get("id"), msg.get("message_id")
    if not azo or not admin(azo.user):
        return answer_callback(cq["id"], "Bu bo'lim faqat administrator uchun", alert=True)
    frappe.set_user(azo.user)
    parts = (cq.get("data") or "").split(":")
    amal = parts[1] if len(parts) > 1 else ""

    def ko_rsat(matn_kb):
        answer_callback(cq["id"])
        return edit_message(chat_id, mid, matn_kb[0], reply_markup=matn_kb[1])

    if amal == "l":
        return ko_rsat(royxat())
    user = _user(parts[2]) if len(parts) > 2 else None
    if not user or not frappe.db.exists("TG Azo", user):
        answer_callback(cq["id"], "Ro'yxat eskirgan — qayta oching", alert=True)
        return edit_message(chat_id, mid, *royxat()) if mid else None
    oziniki = user == azo.user
    if amal == "v":
        return ko_rsat(kartochka(user, azo.user))
    if amal in ("r", "rs", "rk", "f") and oziniki:
        return answer_callback(cq["id"], "O'z rolingiz va holatingizni o'zgartira olmaysiz", alert=True)
    if amal == "r":
        return ko_rsat(rol_tanlash(user))
    if amal in ("rs", "rk"):
        nom = _rol_nomi_tokdan(parts[3]) if len(parts) > 3 else False
        if nom is False:
            return answer_callback(cq["id"], "Ro'yxat eskirgan — qayta oching", alert=True)
        if amal == "rs" and nom and (rol(nom) or {}).get("toliq_ruxsat"):
            return ko_rsat(_rol_tasdiq(user, nom))
        _rol_ber(user, azo.user, nom)
        answer_callback(cq["id"], "Rol saqlandi")
        return edit_message(chat_id, mid, *kartochka(user, azo.user))
    a = frappe.get_doc("TG Azo", user)
    if amal == "ai" and a.rol != "Rahbar":
        yangi = 0 if a.ai_ruxsat else 1
        doc = _qollash(user, azo.user, "AI savol-javob → " + ("yoqildi" if yangi else "o'chirildi"), ai_ruxsat=yangi)
        _xabar(doc, "🤖 Endi botga savolni matn yoki ovoz bilan yozishingiz mumkin." if yangi
               else "🤖 AI bilan savol-javob o'chirildi. Menyudan foydalaning.")
    elif amal == "hs" and a.rol != "Rahbar":
        yangi = 0 if a.hisobot_olsin else 1
        doc = _qollash(user, azo.user, "08:00 hisobotlari → " + ("yoqildi" if yangi else "o'chirildi"), hisobot_olsin=yangi)
        _xabar(doc, "📅 Ertalabki 08:00 hisobotlari " + ("endi sizga keladi." if yangi else "endi kelmaydi."))
    elif amal == "f":
        yangi = 0 if a.faol else 1
        doc = _qollash(user, azo.user, "botga kirish → " + ("yoqildi" if yangi else "o'chirildi"), faol=yangi)
        _xabar(doc, "✅ Botdan foydalanish qayta yoqildi." if yangi
               else "⛔ Botdan foydalanish to'xtatildi. Savol bo'lsa, administratorga murojaat qiling.", menyu_yangila=bool(yangi))
    else:
        return answer_callback(cq["id"])
    answer_callback(cq["id"], "Saqlandi")
    return edit_message(chat_id, mid, *kartochka(user, azo.user))
