"""Vazifalar Telegram oqimi (TZ D1/H6).

Bot faqat shaxsiy chatda ishlaydi (guruh yo'q).
- Rahbar: /vazifa (bosqichma-bosqich) yoki ERP'da Vazifa yaratadi yoki AI taklifini tasdiqlaydi.
- Mas'ulga tugmali xabar: ✅ Qabul / ❌ Rad (sabab bilan) → ✔️ Bajarildi. Beruvchiga har voqea haqida xabar va
  tekshiruv tugmalari (👍 / ↩️ sabab bilan).
- 09:00: muddat nazorati; har xodimga o'z ro'yxati (shaxsiy chatda); dushanba — rahbarga haftalik natija.
"""
from datetime import timedelta

import frappe
from frappe.utils import add_days, getdate, nowdate

from pokiza.nazorat.tg import config
from pokiza.nazorat.tg.format import esc
from pokiza.nazorat.tg.sender import TgXato, answer_callback, edit_message, send_message

OCHIQ = ("Yangi", "Qabul qilindi", "Muddati o'tdi")
TARIX_BELGI = {"q": "✅ Qabul qildi", "r": "❌ Rad etdi", "b": "✔️ Bajardi", "mo": "⏰ Muddati o'tdi",
               "bk": "⚪ Bekor qilindi", "y": "🔄 Qayta berildi", "ok": "👍 Beruvchi tasdiqladi",
               "qt": "↩️ Qaytarildi"}

BELGI = {"Yangi": "🆕", "Qabul qilindi": "🔵", "Rad etildi": "❌", "Bajarildi": "✅", "Muddati o'tdi": "⏰",
         "Bekor qilindi": "⚪"}
HOLAT_TTL = 1800


# ---------- yordamchilar ----------
def _tid(user):
    return frappe.db.get_value("TG Azo", {"user": user, "faol": 1}, "telegram_id")


def _ism(user):
    return frappe.db.get_value("User", user, "full_name") or user


def muddat_s(muddat, holat=None):
    """'12.11 · 2 kun qoldi' / 'bugun' / '3 kun kechikdi'."""
    m = getdate(muddat)
    if holat in ("Bajarildi", "Bekor qilindi", "Rad etildi"):
        return f"{m:%d.%m}"
    n = (m - getdate(nowdate())).days
    qolgan = ("bugun" if n == 0 else "ertaga" if n == 1 else f"{n} kun qoldi" if n > 0 else f"{-n} kun kechikdi")
    return f"{m:%d.%m} · {qolgan}"


def _matn(v):
    out = [f"{BELGI.get(v.holat, '')} <b>{esc(v.sarlavha)}</b>",
           f"👤 {esc(_ism(v.masul))}   📅 {muddat_s(v.muddat, v.holat)}"]
    if v.tavsif:
        out.append(f"<i>{esc(v.tavsif)}</i>")
    if v.holat == "Rad etildi" and v.rad_sababi:
        out.append(f"❌ Sabab: {esc(v.rad_sababi)}")
    out.append(f"<i>Holat: {esc(v.holat)}</i>")
    return "\n".join(out)


def _tekshiruv():
    return bool(config.sozlama("rahbar_tekshiruvi", 1))


def tekshiruv_tugmalar(v):
    return {"inline_keyboard": [[{"text": "👍 Qabul qilaman", "callback_data": f"vz:ok:{v.name}"},
                                 {"text": "↩️ Qaytarish", "callback_data": f"vz:qt:{v.name}"}]]}


def dm_yangila(v):
    """Mas'ulning shaxsiy chatidagi vazifa xabarini joriy holatga keltirish (ERP'da o'zgarsa ham)."""
    d = frappe.cache.get_value(f"nz_vz_dm:{v.name}", expires=True)
    if d:
        try:
            edit_message(d[0], int(d[1]), _matn(v), reply_markup=_tugmalar(v))
        except TgXato:
            pass


def _tugmalar(v):
    if v.holat == "Yangi":
        return {"inline_keyboard": [[{"text": "✅ Qabul qilaman", "callback_data": f"vz:q:{v.name}"},
                                     {"text": "❌ Rad etaman", "callback_data": f"vz:r:{v.name}"}]]}
    if v.holat in ("Qabul qilindi", "Muddati o'tdi"):
        return {"inline_keyboard": [[{"text": "✔️ Bajarildi", "callback_data": f"vz:b:{v.name}"}]]}
    return {"inline_keyboard": []}


def holat_olish(tid):
    return frappe.cache.get_value(f"nz_holat:{tid}", expires=True)


def holat_qoy(tid, val):
    if val is None:
        frappe.cache.delete_value(f"nz_holat:{tid}")
    else:
        frappe.cache.set_value(f"nz_holat:{tid}", val, expires_in_sec=HOLAT_TTL)


def _yubor(user, matn, kb=None):
    tid = _tid(user)
    if not tid:
        return None
    try:
        return send_message(tid, matn, reply_markup=kb)
    except TgXato as e:
        frappe.log_error(title="Nazorat vazifa xabari", message=str(e))


# ---------- yaratish ----------
def yarat(berdi, masul, sarlavha, muddat, tavsif=None, manba="Telegram", bolim=None):
    doc = frappe.get_doc({"doctype": "Vazifa", "sarlavha": sarlavha[:140], "masul": masul, "muddat": muddat,
                          "tavsif": tavsif, "berdi": berdi, "manba": manba,
                          "bolim": bolim or frappe.db.get_value("TG Azo", masul, "bolim")})
    frappe.set_user(berdi)
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


# ---------- xabarlar (enqueue) ----------
def yangi_xabar(vazifa):
    if not config.faol():
        return
    v = frappe.get_doc("Vazifa", vazifa)
    mid = _yubor(v.masul, f"📌 <b>Sizga yangi vazifa</b> ({esc(_ism(v.berdi))} dan)\n\n" + _matn(v), _tugmalar(v))
    if mid:
        frappe.cache.set_value(f"nz_vz_dm:{v.name}", [_tid(v.masul), mid], expires_in_sec=60 * 86400)
    else:
        _yubor(v.berdi, f"⚠️ {esc(_ism(v.masul))} Telegram'ga ulanmagan — vazifa faqat ERP'da ko'rinadi.\n\n" + _matn(v))


def holat_xabar(vazifa, eski=None):
    """Holat o'zgarishi: mas'ulning vazifa xabari yangilanadi, beruvchi va mas'ulga tegishli voqea xabari."""
    if not config.faol():
        return
    v = frappe.get_doc("Vazifa", vazifa)
    if v.holat == "Yangi" and eski in ("Rad etildi", "Bekor qilindi", "Muddati o'tdi"):
        return yangi_xabar(vazifa)  # qayta berildi — mas'ulga yangi tugmali xabar
    dm_yangila(v)
    kim = esc(_ism(v.masul))
    if v.holat == "Qabul qilindi" and eski == "Yangi":
        _yubor(v.berdi, f"✅ {kim} vazifani qabul qildi: <b>{esc(v.sarlavha)}</b>")
    elif v.holat == "Rad etildi" and eski != "Rad etildi":
        _yubor(v.berdi, f"❌ {kim} vazifani rad etdi: <b>{esc(v.sarlavha)}</b>"
                        + (f"\nSabab: {esc(v.rad_sababi)}" if v.rad_sababi else ""))
    elif v.holat == "Bajarildi" and eski != "Bajarildi" and not v.tasdiqlandi:
        if _tekshiruv():
            _yubor(v.berdi, f"✔️ <b>{kim} bajardi</b> — tekshirib qabul qiling\n\n" + _matn(v), tekshiruv_tugmalar(v))
        else:
            _yubor(v.berdi, f"✔️ {kim} bajardi: <b>{esc(v.sarlavha)}</b>")
    elif v.holat == "Qabul qilindi" and eski == "Bajarildi":
        qt = [q.split("|", 2)[2] for q in (v.tarix or "").splitlines() if q.count("|") >= 2 and q.split("|")[1] == "qt"]
        sabab = f"\nSabab: <i>{esc(qt[-1])}</i>" if qt and qt[-1] else ""
        _yubor(v.masul, f"↩️ <b>Vazifa qaytarildi</b> — qayta bajaring{sabab}\n\n" + _matn(v), _tugmalar(v))
    elif v.holat == "Muddati o'tdi" and eski != "Muddati o'tdi":
        _yubor(v.masul, "⏰ <b>Vazifa muddati o'tdi</b>\n\n" + _matn(v), _tugmalar(v))
        _yubor(v.berdi, f"⏰ Muddati o'tdi: <b>{esc(v.sarlavha)}</b> — {kim}")


# ---------- callback ----------
def _sabab_sora(tid, holat, savol):
    """Sababni shaxsiy chatda so'raydi. False — shaxsiy chatga yozib bo'lmadi."""
    holat_qoy(tid, holat)
    try:
        send_message(tid, savol, reply_markup={"force_reply": True, "input_field_placeholder": "Sabab…"})
        return True
    except TgXato:
        holat_qoy(tid, None)
        return False


def _rahbarmi(user):
    from pokiza.nazorat.scope import rahbarmi

    return rahbarmi(user)


def callback(cq):
    _, amal, name = (cq.get("data") or "").split(":", 2)
    tid = str(cq["from"]["id"])
    user = frappe.db.get_value("TG Azo", {"telegram_id": tid, "faol": 1}, "user")
    if not frappe.db.exists("Vazifa", name):
        return answer_callback(cq["id"], "Vazifa topilmadi", alert=True)
    v = frappe.get_doc("Vazifa", name)
    msg = cq.get("message") or {}
    if amal in ("ok", "qt"):
        if not user or not (user == v.berdi or _rahbarmi(user)):
            return answer_callback(cq["id"], "Faqat vazifa beruvchi tasdiqlaydi", alert=True)
        if v.holat != "Bajarildi" or v.tasdiqlandi:
            return answer_callback(cq["id"], f"Holat: {v.holat}", alert=True)
        frappe.set_user(user)
        if amal == "qt":
            if not _sabab_sora(tid, {"tur": "qaytar", "vazifa": name},
                               f"↩️ <b>{esc(v.sarlavha)}</b> — nima uchun qaytarilyapti? (bitta xabar)"):
                return answer_callback(cq["id"], "Avval botga /start bosing", alert=True)
            return answer_callback(cq["id"])
        v.tasdiqlandi = 1
        v.save(ignore_permissions=True)
        frappe.db.commit()
        answer_callback(cq["id"], "Tasdiqlandi")
        return edit_message(tid, msg["message_id"], _matn(v), reply_markup={"inline_keyboard": []})
    if not user or user != v.masul:
        return answer_callback(cq["id"], "Bu vazifa sizga berilmagan", alert=True)
    frappe.set_user(user)
    if amal == "r":
        if v.holat != "Yangi":
            return answer_callback(cq["id"], f"Holat: {v.holat}", alert=True)
        if not _sabab_sora(tid, {"tur": "rad", "vazifa": name},
                           f"❌ <b>{esc(v.sarlavha)}</b> — rad etish sababini yozing (bitta xabar):"):
            return answer_callback(cq["id"], "Avval botga /start bosing", alert=True)
        return answer_callback(cq["id"])
    yangi = {"q": "Qabul qilindi", "b": "Bajarildi"}.get(amal)
    if not yangi:
        return answer_callback(cq["id"])
    try:
        v.holat = yangi
        v.save(ignore_permissions=True)
        frappe.db.commit()
    except frappe.ValidationError as e:
        frappe.db.rollback()
        return answer_callback(cq["id"], str(e)[:180], alert=True)
    answer_callback(cq["id"], yangi)
    if msg.get("message_id"):
        edit_message(tid, msg["message_id"], _matn(v), reply_markup=_tugmalar(v))


def rad_sababi(tid, matn, holat):
    v = frappe.get_doc("Vazifa", holat["vazifa"])
    user = frappe.db.get_value("TG Azo", {"telegram_id": str(tid), "faol": 1}, "user")
    holat_qoy(tid, None)
    if user != v.masul or v.holat != "Yangi":
        return send_message(tid, "Bu vazifani endi rad etib bo'lmaydi.")
    frappe.set_user(user)
    v.holat, v.rad_sababi = "Rad etildi", matn[:1000]
    v.save(ignore_permissions=True)
    frappe.db.commit()
    return send_message(tid, "Rad etildi, vazifa beruvchiga xabar qilindi.\n\n" + _matn(v))


def qaytar_sababi(tid, matn, holat):
    v = frappe.get_doc("Vazifa", holat["vazifa"])
    user = frappe.db.get_value("TG Azo", {"telegram_id": str(tid), "faol": 1}, "user")
    holat_qoy(tid, None)
    if not user or not (user == v.berdi or _rahbarmi(user)) or v.holat != "Bajarildi" or v.tasdiqlandi:
        return send_message(tid, "Bu vazifani endi qaytarib bo'lmaydi.")
    frappe.set_user(user)
    v.holat = "Qabul qilindi"
    v.flags.qaytarish_sababi = matn[:300]
    v.izoh = ((v.izoh or "") + f"\nQaytarildi: {matn[:500]}").strip()
    v.save(ignore_permissions=True)
    frappe.db.commit()
    return send_message(tid, "↩️ Qaytarildi, mas'ulga xabar qilindi.")


# ---------- /vazifalar ----------
def royxat(azo):
    lines = []
    mening = frappe.get_all("Vazifa", filters={"masul": azo.user, "holat": ["in", ["Yangi", "Qabul qilindi", "Muddati o'tdi"]]},
                            fields=["name", "sarlavha", "muddat", "holat"], order_by="muddat asc", limit=20)
    if mening:
        lines.append(f"📌 <b>Menga berilgan</b> · {len(mening)} ta")
        for v in mening:
            lines += [f"{BELGI.get(v.holat, '')} {esc(v.sarlavha)}", f"      <i>📅 {muddat_s(v.muddat, v.holat)}</i>"]
    bergan = frappe.get_all("Vazifa", filters={"berdi": azo.user, "holat": ["not in", ["Bajarildi", "Bekor qilindi"]]},
                            fields=["name", "sarlavha", "muddat", "holat", "masul"], order_by="muddat asc", limit=30)
    if bergan:
        lines += ["", f"📤 <b>Men bergan</b> · {len(bergan)} ta ochiq"]
        for v in bergan:
            lines += [f"{BELGI.get(v.holat, '')} {esc(v.sarlavha)}",
                      f"      <i>👤 {esc(_ism(v.masul))} · 📅 {muddat_s(v.muddat, v.holat)}</i>"]
    kb = None
    if mening:
        kb = {"inline_keyboard": [[{"text": f"{BELGI.get(v.holat, '')} {v.sarlavha[:30]}", "callback_data": f"vz:v:{v.name}"}]
                                  for v in mening[:8]]}
    return "\n".join(lines).strip() or "✨ Ochiq vazifa yo'q.", kb


def korsat(cq):
    """vz:v:<name> — vazifani tugmalari bilan qayta ko'rsatish."""
    _, _, name = cq["data"].split(":", 2)
    tid = str(cq["from"]["id"])
    v = frappe.get_doc("Vazifa", name) if frappe.db.exists("Vazifa", name) else None
    user = frappe.db.get_value("TG Azo", {"telegram_id": tid, "faol": 1}, "user")
    if not v or user not in (v.masul, v.berdi):
        return answer_callback(cq["id"], "Topilmadi", alert=True)
    answer_callback(cq["id"])
    return send_message(tid, _matn(v), reply_markup=_tugmalar(v) if user == v.masul else None)


# ---------- /vazifa ustasi (rahbar) ----------
def _xodimlar(berdi):
    """Vazifa berish mumkin bo'lgan xodimlar (beruvchining o'zi ro'yxatda yo'q)."""
    return frappe.get_all("TG Azo", filters={"faol": 1, "user": ["!=", berdi]}, fields=["user", "bolim"],
                          order_by="ism asc", limit=40)


def usta_boshla(tid, azo):
    rows = _xodimlar(azo.user)
    if not rows:
        return send_message(tid, "Telegram'ga ulangan xodim yo'q.")
    holat_qoy(tid, {"tur": "usta", "qadam": "masul", "xodimlar": [r.user for r in rows]})
    kb = {"inline_keyboard": [[{"text": f"{_ism(r.user)}" + (f" · {r.bolim}" if r.bolim else ""),
                                "callback_data": f"vw:m:{i}"}] for i, r in enumerate(rows)]
          + [[{"text": "Bekor", "callback_data": "vw:x:0"}]]}
    return send_message(tid, "📌 <b>Yangi vazifa</b> — kimga?", reply_markup=kb)


def usta_callback(cq, azo):
    tid = str(cq["from"]["id"])
    h = holat_olish(tid)
    _, amal, arg = cq["data"].split(":", 2)
    if not h or h.get("tur") != "usta":
        return answer_callback(cq["id"], "Bu tugma eskirgan. Yangi vazifa: ➕ Vazifa berish", alert=True)
    answer_callback(cq["id"])
    if amal == "x":
        holat_qoy(tid, None)
        return send_message(tid, "Bekor qilindi.")
    if amal == "m" and h["qadam"] == "masul":
        i = int(arg)
        if not 0 <= i < len(h["xodimlar"]):
            return
        h.update(qadam="sarlavha", masul=h["xodimlar"][i])
        holat_qoy(tid, h)
        return send_message(tid, f"Mas'ul: <b>{esc(_ism(h['masul']))}</b>\nVazifa matnini yozing:",
                            reply_markup={"force_reply": True, "input_field_placeholder": "Nima qilish kerak…"})
    if amal == "d" and h["qadam"] == "muddat":
        h.update(qadam="tasdiq", muddat=str(add_days(nowdate(), int(arg))))
        holat_qoy(tid, h)
        return _usta_tasdiq(tid, h)
    if amal == "ok" and h["qadam"] == "tasdiq":
        holat_qoy(tid, None)
        v = yarat(azo.user, h["masul"], h["sarlavha"], h["muddat"], manba="Telegram")
        return send_message(tid, "✅ Vazifa berildi.\n\n" + _matn(v))


AI_GA = "ai"  # usta matn kutmayotgan bo'lsa — matn oddiy savol sifatida AI'ga o'tadi


def usta_matn(tid, matn, h):
    if h["qadam"] not in ("sarlavha", "muddat"):
        holat_qoy(tid, None)
        return AI_GA
    if h["qadam"] == "sarlavha":
        h.update(qadam="muddat", sarlavha=matn.strip()[:140])
        holat_qoy(tid, h)
        kb = {"inline_keyboard": [[{"text": "Bugun", "callback_data": "vw:d:0"}, {"text": "Ertaga", "callback_data": "vw:d:1"}],
                                  [{"text": "3 kun", "callback_data": "vw:d:3"}, {"text": "1 hafta", "callback_data": "vw:d:7"}],
                                  [{"text": "Bekor", "callback_data": "vw:x:0"}]]}
        return send_message(tid, "Muddat? (tugma yoki sana: 2026-11-20)", reply_markup=kb)
    if h["qadam"] == "muddat":
        try:
            d = getdate(matn.strip())
        except Exception:
            if len(matn.strip()) > 15:  # sana emas, boshqa gap — usta bekor, matn AI'ga
                holat_qoy(tid, None)
                send_message(tid, "Vazifa berish bekor qilindi.")
                return AI_GA
            return send_message(tid, "Sana formati: 2026-11-20")
        if d < getdate(nowdate()):
            return send_message(tid, "Muddat o'tgan sana bo'lmasin.")
        h.update(qadam="tasdiq", muddat=str(d))
        holat_qoy(tid, h)
        return _usta_tasdiq(tid, h)
    return AI_GA


def _usta_tasdiq(tid, h):
    kb = {"inline_keyboard": [[{"text": "✅ Yaratish", "callback_data": "vw:ok:0"}, {"text": "Bekor", "callback_data": "vw:x:0"}]]}
    return send_message(tid, f"<b>{esc(h['sarlavha'])}</b>\nMas'ul: {esc(_ism(h['masul']))}\n"
                             f"Muddat: {getdate(h['muddat']):%d.%m.%Y}\n\nYaratilsinmi?", reply_markup=kb)


# ---------- AI taklifi (5-bosqich) ----------
def ai_taklif_callback(cq, azo):
    """vzt:<id> — AI taklif qilgan vazifani rahbar tasdiqlaydi."""
    tid = str(cq["from"]["id"])
    key = f"nz_vz_taklif:{cq['data'].split(':', 1)[1]}"
    t = frappe.cache.get_value(key, expires=True)
    if not t or t.get("berdi") != azo.user:
        return answer_callback(cq["id"], "Taklif topilmadi yoki muddati o'tgan", alert=True)
    frappe.cache.delete_value(key)
    answer_callback(cq["id"], "Yaratilmoqda")
    try:
        v = yarat(azo.user, t["masul"], t["sarlavha"], t["muddat"], t.get("tavsif"), manba="AI")
    except frappe.ValidationError as e:
        frappe.db.rollback()
        return send_message(tid, f"Yaratib bo'lmadi: {esc(str(e))}")
    return send_message(tid, "✅ Vazifa berildi.\n\n" + _matn(v))


def xabar_taklif_callback(cq, azo):
    """xbt:<id> — AI tayyorlagan shaxsiy xabarni rahbar tasdiqlaydi va u xodimga ketadi."""
    key = f"nz_xb_taklif:{cq['data'].split(':', 1)[1]}"
    t = frappe.cache.get_value(key, expires=True)
    if not t or t.get("berdi") != azo.user:
        return answer_callback(cq["id"], "Xabar topilmadi yoki muddati o'tgan", alert=True)
    tg = frappe.db.get_value("TG Azo", {"user": t["kimga"], "faol": 1}, "telegram_id")
    if not tg:
        return answer_callback(cq["id"], "Xodim botdan uzilgan", alert=True)
    frappe.cache.delete_value(key)
    kimdan = frappe.db.get_value("User", azo.user, "full_name") or azo.user
    html = f"📨 <b>{esc(kimdan)}dan xabar</b>\n\n{esc(t['matn'])}"
    royxat_m, kb = royxat(frappe._dict(user=t["kimga"]))
    if kb:
        html += "\n\n" + royxat_m
    try:
        send_message(tg, html, reply_markup=kb)
    except TgXato as e:
        return answer_callback(cq["id"], f"Yuborilmadi: {str(e)[:150]}", alert=True)
    answer_callback(cq["id"], "Yuborildi")
    msg = cq.get("message") or {}
    if msg.get("message_id"):
        from pokiza.nazorat.tg.sender import call

        qolgan = [r for r in ((msg.get("reply_markup") or {}).get("inline_keyboard") or [])
                  if r and r[0].get("callback_data") != cq["data"]]
        try:
            call("editMessageReplyMarkup", {"chat_id": msg["chat"]["id"], "message_id": msg["message_id"],
                                            "reply_markup": {"inline_keyboard": qolgan}})
        except TgXato:
            pass
    nomi = frappe.db.get_value("User", t["kimga"], "full_name") or t["kimga"]
    return send_message(str(cq["from"]["id"]), f"✅ {esc(nomi)}ga yuborildi.")


# ---------- scheduler 09:00 ----------
def kunlik_tekshir():
    """Muddati o'tganlarni belgilaydi (mas'ul va beruvchiga xabar); ertangi muddatga eslatma; har kimga kunlik ro'yxat."""
    bugun = getdate(nowdate())
    otganlar = []
    for v in frappe.get_all("Vazifa", filters={"holat": ["in", ["Yangi", "Qabul qilindi"]], "muddat": ["<", bugun]},
                            pluck="name"):
        doc = frappe.get_doc("Vazifa", v)
        eski = doc.holat
        doc.holat = "Muddati o'tdi"
        doc.flags.ignore_permissions = True
        doc.flags.nz_jim = True  # xabar pastda, ketma-ket (navbatga yuz xabar tashlanmasin)
        doc.save()
        frappe.db.commit()
        otganlar.append((doc.name, eski))
    if not config.faol():
        return
    for name, eski in otganlar:
        holat_xabar(name, eski)
    for v in frappe.get_all("Vazifa", filters={"holat": ["in", ["Yangi", "Qabul qilindi"]],
                                               "muddat": bugun + timedelta(days=1), "eslatma_yuborildi": 0}, pluck="name"):
        doc = frappe.get_doc("Vazifa", v)
        ok = _yubor(doc.masul, "🔔 <b>Eslatma: ertaga muddat</b>\n\n" + _matn(doc), _tugmalar(doc))
        if ok:
            frappe.db.set_value("Vazifa", v, "eslatma_yuborildi", 1)
            frappe.db.commit()
    kunlik_royxat()


def _qator(v, kim=None):
    return (f"{BELGI.get(v.holat, '')} {esc(v.sarlavha)}" + (f" — {esc(_ism(kim))}" if kim else "")
            + f" · <i>{muddat_s(v.muddat, v.holat)}</i>")


def kunlik_royxat():
    """09:00 — har xodimga SHAXSIY chatda o'z ro'yxati: o'zidagi vazifalar (bugun muddati, kechikkan, qabul
    qilinmagan) va o'zi bergan vazifalardan kechikkanlar va tekshiruv kutayotganlar. Bo'sh bo'lsa — xabar yo'q."""
    if not config.faol():
        return
    bugun = getdate(nowdate())
    f = ["name", "sarlavha", "masul", "berdi", "muddat", "holat", "tasdiqlandi"]
    kimga = {}

    def qosh(user, bolim, v):
        kimga.setdefault(user, {}).setdefault(bolim, []).append(v)

    for v in frappe.get_all("Vazifa", filters={"holat": ["in", list(OCHIQ)]}, fields=f, order_by="muddat asc"):
        if v.holat == "Muddati o'tdi":
            qosh(v.masul, "otgan", v)
            if v.berdi != v.masul:
                qosh(v.berdi, "bergan_otgan", v)
        elif getdate(v.muddat) == bugun:
            qosh(v.masul, "bugun", v)
        elif v.holat == "Yangi":
            qosh(v.masul, "yangi", v)
    if _tekshiruv():
        for v in frappe.get_all("Vazifa", filters={"holat": "Bajarildi", "tasdiqlandi": 0}, fields=f):
            qosh(v.berdi, "tekshir", v)

    for user, b in kimga.items():
        tid = _tid(user)
        if not tid or not config.bir_marta(f"kunlik_royxat:{bugun}:{tid}"):
            continue
        out = [f"📋 <b>Vazifalar — {bugun:%d.%m.%Y}</b>"]
        for k, sarlavha in (("bugun", "⏳ Bugun muddati"), ("otgan", "⏰ Muddati o'tgan"),
                            ("yangi", "🆕 Hali qabul qilmagansiz")):
            if b.get(k):
                out += ["", f"<b>{sarlavha}</b> · {len(b[k])}"] + [_qator(v) for v in b[k][:15]]
        if b.get("tekshir"):
            out += ["", f"<b>👀 Tekshiruvingizni kutmoqda</b> · {len(b['tekshir'])}"]
            out += [f"✔️ {esc(v.sarlavha)} — {esc(_ism(v.masul))}" for v in b["tekshir"][:15]]
        if b.get("bergan_otgan"):
            out += ["", f"<b>⏰ Siz bergan, muddati o'tgan</b> · {len(b['bergan_otgan'])}"]
            out += [_qator(v, v.masul) for v in b["bergan_otgan"][:15]]
        try:
            send_message(tid, "\n".join(out), reply_markup=royxat(frappe._dict(user=user))[1]
                         if (b.get("bugun") or b.get("otgan") or b.get("yangi")) else None)
        except TgXato as e:
            config.bosh_qoy(f"kunlik_royxat:{bugun}:{tid}")
            frappe.log_error(title="Nazorat: kunlik vazifalar", message=str(e))


def haftalik_natija():
    """Dushanba 09:05 — rahbar(lar)ga shaxsiy chatda o'tgan hafta muddatli vazifalar natijasi (xodim bo'yicha)."""
    if not config.faol():
        return
    from pokiza.nazorat.scope import rahbarlar

    bugun = getdate(nowdate())
    f, t = bugun - timedelta(days=bugun.weekday() + 7), bugun - timedelta(days=bugun.weekday() + 1)
    rows = frappe.db.sql("""SELECT masul, COUNT(*) jami, SUM(holat = 'Bajarildi') bajarildi,
            SUM(holat = 'Bajarildi' AND bajarilgan_vaqt > TIMESTAMP(muddat, '23:59:59')) kech,
            SUM(holat IN ('Yangi', 'Qabul qilindi', 'Muddati o''tdi')) ochiq, SUM(holat = 'Rad etildi') rad
        FROM `tabVazifa` WHERE muddat BETWEEN %s AND %s AND holat != 'Bekor qilindi'
        GROUP BY masul ORDER BY SUM(holat = 'Bajarildi') / COUNT(*) DESC, COUNT(*) DESC""", (f, t), as_dict=True)
    if not rows:
        return
    jami, baj = sum(r.jami for r in rows), sum(int(r.bajarildi or 0) for r in rows)
    out = [f"🗓 <b>O'tgan hafta vazifalari</b> ({f:%d.%m}–{t:%d.%m})",
           f"Jami {jami} · bajarildi {baj} ({round(baj / jami * 100)}%)", ""]
    for i, r in enumerate(rows, 1):
        b = int(r.bajarildi or 0)
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.") if b else "▫️"
        q = f"{medal} {esc(_ism(r.masul))} — {b}/{r.jami}"
        qo = [f"{int(r.kech)} kech" if r.kech else "", f"{int(r.ochiq)} ochiq" if r.ochiq else "",
              f"{int(r.rad)} rad" if r.rad else ""]
        qo = [x for x in qo if x]
        out.append(q + (f" · <i>{', '.join(qo)}</i>" if qo else ""))
    for user in rahbarlar():
        tid = _tid(user)
        if not tid or not config.bir_marta(f"haftalik_natija:{f}:{tid}"):
            continue
        try:
            send_message(tid, "\n".join(out))
        except TgXato as e:
            config.bosh_qoy(f"haftalik_natija:{f}:{tid}")
            frappe.log_error(title="Nazorat: haftalik vazifalar", message=str(e))
