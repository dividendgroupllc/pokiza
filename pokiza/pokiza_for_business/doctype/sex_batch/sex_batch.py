# Copyright (c) 2026, abdulloh and contributors
# For license information, please see license.txt
"""
Sex Batch — sex planshetidagi ish PARTIYASI (lot).

Nega kerak: bitta Job Card (operatsiya) bir necha partiyada bajarilishi mumkin.
Oldingi etap 3 ta berdi -> operator 3 talik partiyani BOSHLADI (qty muzlaydi).
Keyin oldingi etap yana 2 ta bersa -> yangi partiya (davomi) ochiladi.
Agar operator hali boshlamagan bo'lsa -> yangi kelgan miqdor bitta "kutilayotgan"
kartochkaga qo'shilib boraveradi (3 -> 5).

Barcha mantiq pokiza/api/sex_ekran.py da; bu shunchaki ma'lumot saqlagich.
"""

from frappe.model.document import Document


class SexBatch(Document):
    pass
