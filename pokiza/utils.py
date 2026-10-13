# -*- coding: utf-8 -*-
"""Chop etish (PDF) yordamchilari."""

import subprocess

import frappe

# wkhtmltopdf ning ikki xil qurilishi bor:
#   * «patched Qt» (Frappe hujjatlari tavsiya qiladigani) — CSS dagi mm/px
#     o'lchovlarini QOG'OZDA aynan shuncha qilib chizadi;
#   * «unpatched/reduced functionality» (Ubuntu repo'sidagi odatiy paket) —
#     sahifani kengroq maketda yig'ib, keyin qog'ozga SIQIB joylashtiradi:
#     287mm qutи 221mm bo'lib chiqadi (≈0.77), ya'ni chap yuqori burchakka
#     siqilib, o'ng va past tomonda bo'sh joy qoladi (egasi 2026-10-13 da
#     aynan shuni ko'rsatdi).
# Yechim: ikkinchi holatda butun sahifani `zoom` bilan 1.3 barobar kattalashtirish
# — shunda maket dizayn qilinganidek, A4 ni to'liq egallaydi.
PDF_ZOOM_SIQILGAN = 1.3
_CACHE_KALIT = "pokiza_wkhtmltopdf_zoom"


def _wk_versiya():
    try:
        r = subprocess.run(["wkhtmltopdf", "--version"],
                           capture_output=True, text=True, timeout=20)
        return (r.stdout or "") + (r.stderr or "")
    except Exception:
        return ""


def pdf_zoom():
    """Print format'lar uchun `zoom` qiymati (Jinja'dan chaqiriladi)."""
    qiymat = frappe.cache().get_value(_CACHE_KALIT)
    if qiymat is None:
        versiya = _wk_versiya().lower()
        # «patched qt» yozuvi bo'lsa — siqish yo'q, zoom kerak emas
        qiymat = 1 if ("patched" in versiya) else PDF_ZOOM_SIQILGAN
        frappe.cache().set_value(_CACHE_KALIT, qiymat, expires_in_sec=3600)
    return qiymat
