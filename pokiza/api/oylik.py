# Copyright (c) 2026, Pokiza
"""Oylik tabel — xodimlar stavka-kunlik davomat jadvali va oylik hisobi.

Old tomoni: Page "oylik-tabel" (jadval-ekran, katak bosib tahrirlash).
Orqa tomonda HRMS'ning haqiqiy hujjatlari ma'lumot yig'adi:
  - kunlik koeffitsient -> Attendance (custom_koef maydoni bilan)
  - oylik (baza) summa  -> Salary Structure Assignment ("Pokiza Oylik" strukturasi)
  - bonus               -> Additional Salary ("Bonus" komponenti)

Hisob: kunlik narx = oylik / oydagi ish kunlari (yakshanbasiz),
jami = kunlik narx * koeffitsientlar yig'indisi + bonus. Yaxlitlanmaydi.

Oy yopilganda: yozilmagan kunlar Attendance bilan to'ldiriladi (default 1,
yakshanba 0 - yozilmaydi), barcha qoralamalar submit qilinadi, tabel qulflanadi.
"""

import calendar
from datetime import date, timedelta

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now_datetime, nowdate

SAHIFA = "oylik-tabel"
STRUKTURA = "Pokiza Oylik"
BONUS_KOMPONENT = "Bonus"
MAKS_KOEF = 5

OY_NOMLARI = {
    1: "Yanvar", 2: "Fevral", 3: "Mart", 4: "Aprel", 5: "May", 6: "Iyun",
    7: "Iyul", 8: "Avgust", 9: "Sentabr", 10: "Oktabr", 11: "Noyabr", 12: "Dekabr",
}

STATUS_KOEF = {"Present": 1.0, "Work From Home": 1.0, "Half Day": 0.5, "Absent": 0.0, "On Leave": 0.0}


# ---------------------------------------------------------------- ruxsat

def _ruxsat_rollari():
    """Tahrirlash huquqi sahifaning (Page) role ro'yxatidan olinadi —
    egasi Page hujjatida rol qo'shsa/olib tashlasa, shu yerda ham amal qiladi."""
    rollar = frappe.get_all(
        "Has Role",
        filters={"parent": SAHIFA, "parenttype": "Page"},
        pluck="role",
    )
    return rollar or ["System Manager"]


def _rol_tekshir():
    if not set(_ruxsat_rollari()) & set(frappe.get_roles()):
        frappe.throw(_("Oylik tabelga ruxsatingiz yo'q"), frappe.PermissionError)


# ---------------------------------------------------------------- yordamchi

def _oy_chegara(yil, oy):
    yil, oy = cint(yil), cint(oy)
    if not (1 <= oy <= 12) or yil < 2020 or yil > 2100:
        frappe.throw(_("Oy/yil noto'g'ri"))
    kun_soni = calendar.monthrange(yil, oy)[1]
    return date(yil, oy, 1), date(yil, oy, kun_soni), kun_soni


def _tabel_doc(yil, oy):
    """Oy uchun Oylik Tabel hujjatini olish (bo'lmasa yaratish)."""
    nom = frappe.db.get_value("Tabel Oyi", {"yil": cint(yil), "oy": cint(oy)})
    if nom:
        return frappe.get_doc("Tabel Oyi", nom)
    doc = frappe.get_doc({"doctype": "Tabel Oyi", "yil": cint(yil), "oy": cint(oy), "holat": "Ochiq"})
    doc.insert(ignore_permissions=True)
    return doc


def _ochiq_tekshir(yil, oy):
    holat = frappe.db.get_value("Tabel Oyi", {"yil": cint(yil), "oy": cint(oy)}, "holat") or "Ochiq"
    if holat != "Ochiq":
        frappe.throw(_("{0} {1} tabeli yopiq — tahrirlab bo'lmaydi").format(OY_NOMLARI[cint(oy)], yil))


def _jurnal(xodim, xodim_ismi, oy_str, maydon, eski, yangi, sana=None):
    frappe.get_doc({
        "doctype": "Tabel Ozgarish Jurnali",
        "xodim": xodim,
        "xodim_ismi": xodim_ismi,
        "oy": oy_str,
        "sana": sana,
        "maydon": maydon,
        "eski": eski if eski is not None else "",
        "yangi": yangi if yangi is not None else "",
        "kim": frappe.session.user,
    }).insert(ignore_permissions=True)


def _kompaniya():
    return frappe.defaults.get_global_default("company")


def _valyuta(company):
    return frappe.db.get_value("Company", company, "default_currency") or "UZS"


def _bonus_komponent_ta_minla():
    if not frappe.db.exists("Salary Component", BONUS_KOMPONENT):
        frappe.get_doc({
            "doctype": "Salary Component",
            "salary_component": BONUS_KOMPONENT,
            "salary_component_abbr": "BON",
            "type": "Earning",
        }).insert(ignore_permissions=True)


def _struktura_ta_minla():
    """"Pokiza Oylik" Salary Structure (Basic = base formulasi bilan)."""
    company = _kompaniya()
    if not frappe.db.exists("Salary Structure", STRUKTURA):
        doc = frappe.get_doc({
            "doctype": "Salary Structure",
            "name": STRUKTURA,
            "company": company,
            "payroll_frequency": "Monthly",
            "currency": _valyuta(company),
            "earnings": [{
                "salary_component": "Basic",
                "amount_based_on_formula": 1,
                "formula": "base",
            }],
        })
        doc.flags.ignore_permissions = True
        doc.insert(ignore_permissions=True)
        doc.submit()
    else:
        doc = frappe.get_doc("Salary Structure", STRUKTURA)
        if doc.docstatus == 0:
            doc.flags.ignore_permissions = True
            doc.submit()
    return STRUKTURA


def _kassa_taklif(emp_ids, oy_boshi):
    """Har xodim uchun default oylik taklifi — Kassa'da xodimga qilingan
    to'lovlarning eng oxirgi to'liq oyi yig'indisi (joriy tabel oyidan oldingi)."""
    if not emp_ids:
        return {}
    chegara = oy_boshi.strftime("%Y-%m")
    rows = frappe.db.sql(
        """select party, date_format(`date`, '%%Y-%%m') as oy, sum(amount) as summa
           from `tabKassa`
           where docstatus = 1 and party_type = 'Employee'
             and transaction_type = 'Расход' and party in %(emps)s
             and date_format(`date`, '%%Y-%%m') < %(chegara)s
           group by party, oy""",
        {"emps": emp_ids, "chegara": chegara},
        as_dict=True,
    )
    eng_oxirgi = {}
    for r in rows:
        if r.party not in eng_oxirgi or r.oy > eng_oxirgi[r.party][0]:
            eng_oxirgi[r.party] = (r.oy, flt(r.summa))
    return {p: v[1] for p, v in eng_oxirgi.items()}


# ---------------------------------------------------------------- asosiy hisob

def _tabel_hisobla(yil, oy, hamma_kunlar=False):
    """Tabelning to'liq holatini hisoblaydi (get_tabel ham, oy yopish ham ishlatadi).

    hamma_kunlar=True — oyning barcha kunlari (yopishda backfill uchun),
    aks holda faqat bugungacha bo'lgan kunlar ko'rsatiladi.
    """
    yil, oy = cint(yil), cint(oy)
    bugun = getdate(nowdate())
    oy_boshi, oy_oxiri, kun_soni = _oy_chegara(yil, oy)

    if oy_boshi > bugun:
        frappe.throw(_("Kelajak oy uchun tabel ochilmaydi"))

    if hamma_kunlar or oy_oxiri <= bugun:
        korinadigan = kun_soni
    else:
        korinadigan = bugun.day

    kunlar = []
    yakshanbalar = set()
    for k in range(1, kun_soni + 1):
        if date(yil, oy, k).weekday() == 6:
            yakshanbalar.add(k)
    for k in range(1, korinadigan + 1):
        kunlar.append({"kun": k, "sana": str(date(yil, oy, k)), "yakshanba": k in yakshanbalar})

    ish_kunlari = kun_soni - len(yakshanbalar)

    xodimlar = frappe.get_all(
        "Employee",
        filters={"status": "Active", "date_of_joining": ["<=", oy_oxiri]},
        fields=["name", "employee_name", "date_of_joining"],
        order_by="employee_name asc",
    )
    emp_ids = [x.name for x in xodimlar]

    # Oylik (baza): SSA'dan; bo'lmasa Kassa taklifi
    base_map = {}
    if emp_ids:
        for r in frappe.get_all(
            "Salary Structure Assignment",
            filters={"employee": ["in", emp_ids], "docstatus": 1, "from_date": ["<=", oy_oxiri]},
            fields=["employee", "base", "from_date"],
            order_by="from_date asc",
        ):
            base_map[r.employee] = flt(r.base)  # keyingi from_date ustun keladi
    kassa_map = _kassa_taklif(emp_ids, oy_boshi)

    # Kunlik koeffitsientlar: Attendance
    davomat = {}
    if emp_ids:
        for r in frappe.get_all(
            "Attendance",
            filters={
                "employee": ["in", emp_ids],
                "docstatus": ["<", 2],
                "attendance_date": ["between", [oy_boshi, oy_oxiri]],
            },
            fields=["employee", "attendance_date", "custom_koef", "status", "docstatus"],
        ):
            koef = flt(r.custom_koef) if r.custom_koef is not None else STATUS_KOEF.get(r.status, 1.0)
            davomat[(r.employee, getdate(r.attendance_date).day)] = koef

    # Bonuslar: Additional Salary
    bonus_map = {}
    if emp_ids:
        for r in frappe.get_all(
            "Additional Salary",
            filters={
                "employee": ["in", emp_ids],
                "docstatus": ["<", 2],
                "salary_component": BONUS_KOMPONENT,
                "payroll_date": ["between", [oy_boshi, oy_oxiri]],
            },
            fields=["employee", "amount"],
        ):
            bonus_map[r.employee] = bonus_map.get(r.employee, 0) + flt(r.amount)

    qatorlar = []
    for x in xodimlar:
        kirgan = getdate(x.date_of_joining) if x.date_of_joining else None
        if x.name in base_map:
            oylik = {"summa": base_map[x.name], "manba": "ssa"}
        elif x.name in kassa_map:
            oylik = {"summa": kassa_map[x.name], "manba": "kassa"}
        else:
            oylik = {"summa": 0.0, "manba": "yoq"}

        kun_qatori = []
        koef_yigindi = 0.0
        for kd in kunlar:
            k = kd["kun"]
            sana_k = date(yil, oy, k)
            if kirgan and sana_k < kirgan:
                kun_qatori.append({"koef": None, "holat": "kirmagan"})
                continue
            if (x.name, k) in davomat:
                koef = davomat[(x.name, k)]
                holat = "saqlangan"
            else:
                koef = 0.0 if kd["yakshanba"] else 1.0
                holat = "default"
            koef_yigindi += koef
            kun_qatori.append({"koef": koef, "holat": holat})

        bonus = bonus_map.get(x.name, 0.0)
        kunlik_narx = (oylik["summa"] / ish_kunlari) if ish_kunlari else 0.0
        jami = kunlik_narx * koef_yigindi + bonus

        qatorlar.append({
            "xodim": x.name,
            "ismi": x.employee_name,
            "kirgan_sana": str(kirgan) if kirgan else None,
            "oylik": oylik,
            "kunlar": kun_qatori,
            "koef_yigindi": koef_yigindi,
            "kunlik_narx": kunlik_narx,
            "bonus": bonus,
            "jami": jami,
        })

    return {
        "yil": yil,
        "oy": oy,
        "oy_nomi": OY_NOMLARI[oy],
        "bugun": str(bugun),
        "kun_soni": kun_soni,
        "ish_kunlari": ish_kunlari,
        "kunlar": kunlar,
        "qatorlar": qatorlar,
        "jami_oylik": sum(q["jami"] for q in qatorlar),
        "jami_bonus": sum(q["bonus"] for q in qatorlar),
    }


# ---------------------------------------------------------------- whitelisted

@frappe.whitelist()
def get_tabel(yil=None, oy=None):
    _rol_tekshir()
    bugun = getdate(nowdate())
    yil = cint(yil) or bugun.year
    oy = cint(oy) or bugun.month

    natija = _tabel_hisobla(yil, oy)
    tabel = _tabel_doc(yil, oy)
    oy_oxiri = _oy_chegara(yil, oy)[1]

    natija["holat"] = tabel.holat
    natija["tahrir_mumkin"] = tabel.holat == "Ochiq"
    natija["yopish_mumkin"] = tabel.holat == "Ochiq" and bugun >= oy_oxiri
    natija["ochish_mumkin"] = tabel.holat == "Yopiq" and "System Manager" in frappe.get_roles()
    return natija


@frappe.whitelist()
def set_koef(xodim, sana, koef):
    """Bitta kun katakchasini o'zgartirish -> Attendance yoziladi."""
    _rol_tekshir()
    sana = getdate(sana)
    koef = flt(koef)
    if koef < 0 or koef > MAKS_KOEF:
        frappe.throw(_("Koeffitsient 0 dan {0} gacha bo'lishi kerak").format(MAKS_KOEF))
    if sana > getdate(nowdate()):
        frappe.throw(_("Kelajak kunga yozib bo'lmaydi"))
    _ochiq_tekshir(sana.year, sana.month)

    emp = frappe.db.get_value(
        "Employee", xodim, ["name", "employee_name", "company", "date_of_joining"], as_dict=True
    )
    if not emp:
        frappe.throw(_("Xodim topilmadi"))
    if emp.date_of_joining and sana < getdate(emp.date_of_joining):
        frappe.throw(_("Xodim {0} da ishga kirgan — undan oldingi kunga yozib bo'lmaydi").format(emp.date_of_joining))

    status = "Absent" if koef == 0 else ("Half Day" if koef < 1 else "Present")

    mavjud = frappe.get_all(
        "Attendance",
        filters={"employee": xodim, "attendance_date": sana, "docstatus": ["<", 2]},
        fields=["name", "docstatus", "custom_koef", "status"],
        limit=1,
    )
    eski = None
    if mavjud:
        eski_r = mavjud[0]
        eski = flt(eski_r.custom_koef) if eski_r.custom_koef is not None else STATUS_KOEF.get(eski_r.status)
        doc = frappe.get_doc("Attendance", eski_r.name)
        doc.flags.ignore_permissions = True
        if doc.docstatus == 1:
            # yopilib qayta ochilgan oy — eskisi bekor qilinib yangisi yoziladi
            doc.cancel()
            mavjud = None
        else:
            doc.status = status
            doc.custom_koef = koef
            doc.save(ignore_permissions=True)

    if not mavjud:
        doc = frappe.get_doc({
            "doctype": "Attendance",
            "naming_series": "HR-ATT-.YYYY.-",
            "employee": xodim,
            "attendance_date": sana,
            "status": status,
            "custom_koef": koef,
            "company": emp.company or _kompaniya(),
        })
        doc.flags.ignore_permissions = True
        doc.insert(ignore_permissions=True)

    _jurnal(xodim, emp.employee_name, f"{sana.year}-{sana.month:02d}", "Kun koeffitsienti",
            "default" if eski is None else str(eski), str(koef), sana=sana)
    return {"ok": True, "koef": koef}


@frappe.whitelist()
def set_oylik(xodim, yil, oy, summa):
    """Oylik (baza) summani o'rnatish -> Salary Structure Assignment.

    from_date = oy boshi, shuning uchun qachon o'zgartirilmasin — o'sha oyga
    TO'LIQ amal qiladi (oldingi oylar eski qiymatida qoladi)."""
    _rol_tekshir()
    yil, oy = cint(yil), cint(oy)
    summa = flt(summa)
    if summa < 0:
        frappe.throw(_("Oylik manfiy bo'lmaydi"))
    _ochiq_tekshir(yil, oy)
    oy_boshi = _oy_chegara(yil, oy)[0]

    emp = frappe.db.get_value(
        "Employee", xodim, ["name", "employee_name", "company", "date_of_joining"], as_dict=True
    )
    if not emp:
        frappe.throw(_("Xodim topilmadi"))

    _bonus_komponent_ta_minla()
    _struktura_ta_minla()

    # SSA from_date xodim kirgan kunidan oldin bo'lolmaydi
    from_date = oy_boshi
    if emp.date_of_joining and getdate(emp.date_of_joining) > oy_boshi:
        from_date = getdate(emp.date_of_joining)

    eski = None
    for r in frappe.get_all(
        "Salary Structure Assignment",
        filters={"employee": xodim, "from_date": from_date, "docstatus": 1},
        pluck="name",
    ):
        doc = frappe.get_doc("Salary Structure Assignment", r)
        eski = flt(doc.base)
        doc.flags.ignore_permissions = True
        doc.cancel()

    company = emp.company or _kompaniya()
    doc = frappe.get_doc({
        "doctype": "Salary Structure Assignment",
        "employee": xodim,
        "salary_structure": STRUKTURA,
        "from_date": from_date,
        "company": company,
        "currency": _valyuta(company),
        "base": summa,
    })
    doc.flags.ignore_permissions = True
    doc.insert(ignore_permissions=True)
    doc.submit()

    _jurnal(xodim, emp.employee_name, f"{yil}-{oy:02d}", "Oylik summa",
            str(eski) if eski is not None else "", str(summa))
    return {"ok": True, "summa": summa}


@frappe.whitelist()
def set_bonus(xodim, yil, oy, summa):
    """Oy oxiridagi bonus -> Additional Salary (Bonus komponenti, qoralama)."""
    _rol_tekshir()
    yil, oy = cint(yil), cint(oy)
    summa = flt(summa)
    if summa < 0:
        frappe.throw(_("Bonus manfiy bo'lmaydi"))
    _ochiq_tekshir(yil, oy)
    oy_boshi, oy_oxiri, _kun = _oy_chegara(yil, oy)

    emp = frappe.db.get_value("Employee", xodim, ["name", "employee_name", "company"], as_dict=True)
    if not emp:
        frappe.throw(_("Xodim topilmadi"))

    _bonus_komponent_ta_minla()

    mavjud = frappe.get_all(
        "Additional Salary",
        filters={
            "employee": xodim,
            "salary_component": BONUS_KOMPONENT,
            "payroll_date": ["between", [oy_boshi, oy_oxiri]],
            "docstatus": ["<", 2],
        },
        fields=["name", "docstatus", "amount"],
    )
    eski = sum(flt(r.amount) for r in mavjud) if mavjud else None

    for r in mavjud:
        doc = frappe.get_doc("Additional Salary", r.name)
        doc.flags.ignore_permissions = True
        if doc.docstatus == 1:
            doc.cancel()
        else:
            frappe.delete_doc("Additional Salary", r.name, ignore_permissions=True, force=True)

    if summa > 0:
        company = emp.company or _kompaniya()
        doc = frappe.get_doc({
            "doctype": "Additional Salary",
            "employee": xodim,
            "company": company,
            "salary_component": BONUS_KOMPONENT,
            "currency": _valyuta(company),
            "amount": summa,
            "payroll_date": oy_oxiri,
        })
        doc.flags.ignore_permissions = True
        doc.insert(ignore_permissions=True)

    _jurnal(xodim, emp.employee_name, f"{yil}-{oy:02d}", "Bonus",
            str(eski) if eski is not None else "", str(summa))
    return {"ok": True, "summa": summa}


@frappe.whitelist()
def oy_yop(yil, oy):
    """Oyni yopish: bo'sh kunlar Attendance bilan to'ldiriladi (default),
    hammasi submit bo'ladi, oylik summalar SSA sifatida saqlanadi, tabel qulflanadi.
    Og'ir ish — fonda (background job) bajariladi."""
    _rol_tekshir()
    yil, oy = cint(yil), cint(oy)
    _ochiq_tekshir(yil, oy)
    oy_oxiri = _oy_chegara(yil, oy)[1]
    if getdate(nowdate()) < oy_oxiri:
        frappe.throw(_("Oy hali tugamagan — {0} dan keyin yopish mumkin").format(oy_oxiri))

    tabel = _tabel_doc(yil, oy)
    tabel.db_set("holat", "Yopilmoqda")
    frappe.enqueue(
        "pokiza.api.oylik._oy_yop_job",
        queue="long",
        timeout=7200,
        yil=yil,
        oy=oy,
        foydalanuvchi=frappe.session.user,
    )
    return {"ok": True, "holat": "Yopilmoqda"}


def _oy_yop_job(yil, oy, foydalanuvchi):
    try:
        _bonus_komponent_ta_minla()
        _struktura_ta_minla()
        natija = _tabel_hisobla(yil, oy, hamma_kunlar=True)
        oy_boshi, oy_oxiri, _kun = _oy_chegara(yil, oy)

        for q in natija["qatorlar"]:
            emp = q["xodim"]
            company = frappe.db.get_value("Employee", emp, "company") or _kompaniya()

            # 1) Oylik summa SSA'da yo'q bo'lsa — ko'rsatilgan qiymat bilan saqlab qo'yamiz
            if q["oylik"]["manba"] != "ssa":
                from_date = oy_boshi
                kirgan = getdate(q["kirgan_sana"]) if q["kirgan_sana"] else None
                if kirgan and kirgan > oy_boshi:
                    from_date = kirgan
                if not frappe.db.exists(
                    "Salary Structure Assignment",
                    {"employee": emp, "from_date": from_date, "docstatus": 1},
                ):
                    ssa = frappe.get_doc({
                        "doctype": "Salary Structure Assignment",
                        "employee": emp,
                        "salary_structure": STRUKTURA,
                        "from_date": from_date,
                        "company": company,
                        "currency": _valyuta(company),
                        "base": q["oylik"]["summa"],
                    })
                    ssa.flags.ignore_permissions = True
                    ssa.insert(ignore_permissions=True)
                    ssa.submit()

            # 2) Yozilmagan kunlarni default bilan to'ldirish
            for i, kd in enumerate(natija["kunlar"]):
                kq = q["kunlar"][i]
                if kq["holat"] != "default":
                    continue  # kirmagan yoki allaqachon saqlangan
                if kd["yakshanba"] and not kq["koef"]:
                    continue  # yakshanba 0 — yozuv shart emas
                koef = kq["koef"]
                status = "Absent" if koef == 0 else ("Half Day" if koef < 1 else "Present")
                att = frappe.get_doc({
                    "doctype": "Attendance",
                    "naming_series": "HR-ATT-.YYYY.-",
                    "employee": emp,
                    "attendance_date": kd["sana"],
                    "status": status,
                    "custom_koef": koef,
                    "company": company,
                })
                att.flags.ignore_permissions = True
                att.insert(ignore_permissions=True)

        # 3) Oydagi barcha qoralama Attendance'larni submit qilish
        for nom in frappe.get_all(
            "Attendance",
            filters={"docstatus": 0, "attendance_date": ["between", [oy_boshi, oy_oxiri]]},
            pluck="name",
        ):
            doc = frappe.get_doc("Attendance", nom)
            doc.flags.ignore_permissions = True
            doc.submit()

        # 4) Bonus qoralamalarini submit qilish
        for nom in frappe.get_all(
            "Additional Salary",
            filters={
                "docstatus": 0,
                "salary_component": BONUS_KOMPONENT,
                "payroll_date": ["between", [oy_boshi, oy_oxiri]],
            },
            pluck="name",
        ):
            doc = frappe.get_doc("Additional Salary", nom)
            doc.flags.ignore_permissions = True
            doc.submit()

        tabel = _tabel_doc(yil, oy)
        tabel.db_set("holat", "Yopiq")
        tabel.db_set("yopgan_kim", foydalanuvchi)
        tabel.db_set("yopilgan_vaqt", now_datetime())
        _jurnal(None, "", f"{yil}-{oy:02d}", "Oy holati", "Ochiq", "Yopiq")
        frappe.db.commit()
        frappe.publish_realtime(
            "tabel_update",
            {"yil": yil, "oy": oy, "holat": "Yopiq", "xabar": f"{OY_NOMLARI[oy]} {yil} tabeli yopildi ✅"},
        )
    except Exception:
        frappe.db.rollback()
        tabel = _tabel_doc(yil, oy)
        tabel.db_set("holat", "Ochiq")
        frappe.db.commit()
        frappe.log_error(title="Oylik tabel yopishda xato", message=frappe.get_traceback())
        frappe.publish_realtime(
            "tabel_update",
            {"yil": yil, "oy": oy, "holat": "Ochiq", "xabar": "Oy yopishda xato — tizim jurnalini ko'ring ❌"},
        )


@frappe.whitelist()
def oy_och(yil, oy):
    """Yopiq oyni qayta ochish (faqat System Manager)."""
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Faqat System Manager oyni qayta ocha oladi"), frappe.PermissionError)
    yil, oy = cint(yil), cint(oy)
    tabel = _tabel_doc(yil, oy)
    if tabel.holat != "Yopiq":
        frappe.throw(_("Bu oy yopiq emas"))
    tabel.db_set("holat", "Ochiq")
    _jurnal(None, "", f"{yil}-{oy:02d}", "Oy holati", "Yopiq", "Ochiq")
    return {"ok": True}
