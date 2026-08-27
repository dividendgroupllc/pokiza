# Oylik tabel uchun HRMS tayyorgarligi:
# - Attendance.custom_koef maydoni
# - "Bonus" Salary Component
# - "Pokiza Oylik" Salary Structure
import frappe

from pokiza.setup import sync_custom_fields


def execute():
    sync_custom_fields()
    from pokiza.api.oylik import _bonus_komponent_ta_minla, _struktura_ta_minla

    _bonus_komponent_ta_minla()
    _struktura_ta_minla()
    frappe.db.commit()
