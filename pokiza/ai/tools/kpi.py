"""Rahbar KPI'lari (TZ A1..K4) — Nazorat tizimining yagona KPI dvigatelidan (pokiza/nazorat/metrics).

Telegram hisobotlari va rahbar paneli ham shu funksiyani chaqiradi — AI javobi hisobot bilan bir xil bo'ladi.
"""
from pokiza.ai.tools import RuxsatXato, ToolError, tool
from pokiza.nazorat.metrics import DavrXato, compute, royxat


def _bolim():
    import frappe

    return (getattr(frappe.local, "pokiza_ai", None) or {}).get("bolim")


def get_kpi(code=None, davr=None, trend=None, tafsilot=None):
    import frappe

    bolim = _bolim()
    ruxsat = None
    if not bolim and (getattr(frappe.local, "pokiza_ai", None) or {}).get("tools") is not None:
        raise RuxsatXato("Foydalanuvchiga rol biriktirilmagan")
    if bolim:  # rol doirasi (web va Telegram; to'liq ruxsatli rol — hammasi)
        from pokiza.nazorat.scope import ruxsat_kodlar

        ruxsat = ruxsat_kodlar(bolim)
    if not code:
        rows = royxat()
        return {"korsatkichlar": [r for r in rows if ruxsat is None or r["code"] in ruxsat]}
    if ruxsat is not None and code.upper().strip() not in ruxsat:
        raise RuxsatXato("Bu ko'rsatkich foydalanuvchining roliga kirmaydi")
    trend = int(trend or 0)
    if not 0 <= trend <= 24:
        raise ToolError("trend 0..24 oralig'ida bo'lishi kerak")
    try:
        r = compute(code, davr, full=tafsilot is not False, trend=trend)
    except KeyError as e:
        raise ToolError(f"{e}. Ro'yxat uchun code'siz chaqir.")
    except (DavrXato, ValueError) as e:
        raise ToolError(str(e))
    if isinstance(r.get("tafsilot"), list) and len(r["tafsilot"]) > 40:
        r["tafsilot_note"] = f"{len(r['tafsilot'])} qatordan 40 tasi"
        r["tafsilot"] = r["tafsilot"][:40]
    return r


TOOLS = [
    (
        tool(
            "get_kpi",
            "Rahbarning rasmiy KPI'lari (TZ): reja vs fakt, bajarilish %, rang (yashil/sariq/qizil), oldingi davr, "
            "tafsilot va izohlar. Telegram hisobotlari bilan AYNAN bir xil raqam — rahbar 'savdo/quvvat/rentabellik/"
            "o'rtacha chek/sof daromad/dividend/jim mijozlar' haqida so'rasa AVVAL shuni ishlat. Kodlar: "
            "A1 quvvat, A2 savdo, A3 sof rentabellik, A4 o'rtacha chek, A5 sof daromad $, B1 mijoz rentabelligi, "
            "B2 mijoz dinamikasi, B3 top mahsulotlar (50%), B4 kategoriya mix, C1 postavshiklarga to'lov (oy), "
            "C2 mijozlar to'lov kelishuvi/debitorlik (oy), C3 xarajatlar, C4 brak/vozvrat, C5 dividend, "
            "C6 sof foyda taqsimoti (yechilgan vs oborotda), D1 vazifalar bajarilishi, H6 haftalik vazifalar, "
            "H1 haftalik savdo, H2 haftalik chek, H3 haftalik quvvat, H4 7 kun jim mijozlar, "
            "H5 'oldingi tovarni yopish' shartli mijozlar, K1 kunlik savdo, "
            "K2 kunlik ishlab chiqarish, K3 kassa kirimi, K4 kunlik dividend. code'siz — to'liq ro'yxat "
            "(qurilmaganlari sababi bilan). Kodlar faqat ichki tartib uchun: foydalanuvchiga javobda A2, C1 kabi "
            "kodlarni YOZMA — doim ko'rsatkich nomini yoz (masalan 'Savdo', 'Postavshiklarga to'lov').",
            {
                "code": {"type": "string", "description": "Masalan 'A2'. Bo'sh — ro'yxat"},
                "davr": {"type": "string", "description": "2026-10 | 2026-W44 | 2026-10-15 | 2026-10-01:2026-10-15 | "
                         "joriy_oy | otgan_oy | joriy_hafta | otgan_hafta | bugun | kecha. Bo'sh — oxirgi to'liq davr"},
                "trend": {"type": "integer", "description": "Shuncha davr tarixi (0..24), grafik/trend uchun"},
                "tafsilot": {"type": "boolean", "description": "false — faqat asosiy raqamlar (tezroq)"},
            },
            strict=False,
        ),
        get_kpi,
    ),
]
