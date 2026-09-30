from pathlib import Path

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


NAKLADNAYA_PRINT_FORMAT = "Накладная Pokiza"
BOM_DOCTYPE = "BOM"
BOM_UNIQUE_CODE_FIELDNAME = "custom_unique_code"

PRODUCTION_ENTRY_DOCTYPE = "Production Entry"
# Frappe list view kolonkalarni cheklaydi (odatiy ekranada 6 ta). Shu sabab
# `qty_to_manufacture` (ishlab chiqarilayotgan miqdor) — `bom_no` dan keyingi
# oxirgi in_list_view maydoni — ro'yxatda ko'rinmay qoladi. Chegarani ko'tarib,
# uni "ВМ №" (BOM No) ustunidan keyin ko'rsatamiz.
PRODUCTION_ENTRY_LIST_TOTAL_FIELDS = "8"


def get_custom_fields():
    return {
        "Stock Entry": [
            {
                "fieldname": "custom_production_entry",
                "label": "Production Entry",
                "fieldtype": "Link",
                "options": "Production Entry",
                "insert_after": "work_order",
                "read_only": 1,
            }
        ],
        "Customer": [
            {
                "fieldname": "contact_number",
                "label": "Telefon raqam",
                "fieldtype": "Data",
                "options": "Phone",
                "insert_after": "customer_name",
                "in_list_view": 0,
                "in_standard_filter": 1,
            },
            {
                "fieldname": "telegram_chat_id",
                "label": "Telegram Chat ID",
                "fieldtype": "Data",
                "insert_after": "contact_number",
                "read_only": 1,
                "in_list_view": 0,
            },
        ],
        "Supplier": [
            {
                "fieldname": "contact_number",
                "label": "Telefon raqam",
                "fieldtype": "Data",
                "options": "Phone",
                "insert_after": "supplier_name",
                "in_list_view": 0,
                "in_standard_filter": 1,
            },
            {
                "fieldname": "telegram_chat_id",
                "label": "Telegram Chat ID",
                "fieldtype": "Data",
                "insert_after": "contact_number",
                "read_only": 1,
                "in_list_view": 0,
            },
        ],
        "Employee": [
            {
                "fieldname": "telegram_chat_id",
                "label": "Telegram Chat ID",
                "fieldtype": "Data",
                "insert_after": "employee_name",
                "read_only": 1,
                "in_list_view": 0,
            },
        ],
        # Oylik tabel: har kunlik stavka koeffitsienti (1 = to'liq kun, 0.5, 1.5, 2 ...)
        "Attendance": [
            {
                "fieldname": "custom_koef",
                "label": "Stavka koeffitsienti (tabel)",
                "fieldtype": "Float",
                "precision": "9",
                "insert_after": "status",
                "in_list_view": 1,
            },
        ],
        "Sales Order": [
            {
                "fieldname": "custom_izoh",
                "label": "Izoh (sex ekrani uchun)",
                "fieldtype": "Small Text",
                "insert_after": "order_type",
                "in_list_view": 0,
            },
        ],
        # Brak (2026-09-30): tarozida yaroqsiz deb ajratilgan kg — sotuvga
        # kirmaydi, farshi BOM bo'yicha xom ashyoga qaytadi (PE hisoblaydi)
        "Sales Order Item": [
            {
                "fieldname": "custom_brak_kg",
                "label": "Brak (kg)",
                "fieldtype": "Float",
                "insert_after": "custom_fakt_kg",
                "read_only": 1,
                "no_copy": 1,
            },
        ],
        "Material Request Item": [
            {
                "fieldname": "custom_brak_kg",
                "label": "Brak (kg)",
                "fieldtype": "Float",
                "insert_after": "custom_fakt_kg",
                "read_only": 1,
                "no_copy": 1,
            },
        ],
        # Schyotda zakaz soni ko'rinadi; qator soni (qty) esa tarozi fakti
        # bilan sinxronlanadi — mijozga fakt bo'yicha sotiladi (2026-09-30)
        "Sales Invoice Item": [
            {
                "fieldname": "custom_zakaz_kg",
                "label": "Zakaz kg (SO)",
                "fieldtype": "Float",
                "insert_after": "qty",
                "read_only": 1,
                "in_list_view": 1,
                "columns": 1,
                "no_copy": 1,
            },
        ],
    }


def get_bom_unique_code_field():
    return {
        "fieldname": BOM_UNIQUE_CODE_FIELDNAME,
        "label": "Custom Unique Code",
        "fieldtype": "Data",
        "insert_after": "item",
        "in_list_view": 1,
        "in_standard_filter": 1,
        "reqd": 0,
    }


def sync_custom_fields():
    create_custom_fields(get_custom_fields(), ignore_validate=True, update=True)
    sync_bom_unique_code_field()


def sync_bom_unique_code_field():
    field = get_bom_unique_code_field()
    custom_field_name = frappe.db.get_value(
        "Custom Field",
        {"dt": BOM_DOCTYPE, "fieldname": BOM_UNIQUE_CODE_FIELDNAME},
        "name",
    )

    if custom_field_name or not frappe.get_meta(BOM_DOCTYPE, cached=False).get_field(
        BOM_UNIQUE_CODE_FIELDNAME
    ):
        create_custom_fields(
            {BOM_DOCTYPE: [field]},
            ignore_validate=True,
            update=True,
        )

    normalize_blank_bom_unique_codes()
    validate_existing_bom_unique_codes()
    set_bom_unique_code_property()

    frappe.clear_cache(doctype=BOM_DOCTYPE)
    frappe.db.updatedb(BOM_DOCTYPE)


def normalize_blank_bom_unique_codes():
    if frappe.db.has_column(BOM_DOCTYPE, BOM_UNIQUE_CODE_FIELDNAME):
        frappe.db.sql(
            f"""
            UPDATE `tab{BOM_DOCTYPE}`
            SET `{BOM_UNIQUE_CODE_FIELDNAME}` = NULL
            WHERE `{BOM_UNIQUE_CODE_FIELDNAME}` = ''
            """
        )


def validate_existing_bom_unique_codes():
    if not frappe.db.has_column(BOM_DOCTYPE, BOM_UNIQUE_CODE_FIELDNAME):
        return

    duplicates = frappe.db.sql(
        f"""
        SELECT `{BOM_UNIQUE_CODE_FIELDNAME}` AS code
        FROM `tab{BOM_DOCTYPE}`
        WHERE `{BOM_UNIQUE_CODE_FIELDNAME}` IS NOT NULL
            AND `{BOM_UNIQUE_CODE_FIELDNAME}` != ''
        GROUP BY `{BOM_UNIQUE_CODE_FIELDNAME}`
        HAVING COUNT(*) > 1
        LIMIT 5
        """,
        as_dict=True,
    )
    if duplicates:
        duplicate_codes = ", ".join(d.code for d in duplicates)
        frappe.throw(
            "BOM custom_unique_code maydonini unique qilib bo'lmadi. "
            f"Takrorlangan qiymatlar bor: {duplicate_codes}"
        )


def set_bom_unique_code_property():
    custom_field_name = frappe.db.get_value(
        "Custom Field",
        {"dt": BOM_DOCTYPE, "fieldname": BOM_UNIQUE_CODE_FIELDNAME},
        "name",
    )
    if custom_field_name:
        frappe.db.set_value("Custom Field", custom_field_name, "unique", 1)
        frappe.db.set_value("Custom Field", custom_field_name, "reqd", 0)

    unique_property_setter_name = frappe.db.exists(
        "Property Setter",
        {
            "doc_type": BOM_DOCTYPE,
            "field_name": BOM_UNIQUE_CODE_FIELDNAME,
            "property": "unique",
        },
    )
    if unique_property_setter_name:
        frappe.db.set_value(
            "Property Setter", unique_property_setter_name, "value", "1"
        )
    else:
        frappe.make_property_setter(
            {
                "doctype": BOM_DOCTYPE,
                "fieldname": BOM_UNIQUE_CODE_FIELDNAME,
                "property": "unique",
                "property_type": "Check",
                "value": "1",
            },
            ignore_validate=True,
            validate_fields_for_doctype=False,
        )

    reqd_property_setter_name = frappe.db.exists(
        "Property Setter",
        {
            "doc_type": BOM_DOCTYPE,
            "field_name": BOM_UNIQUE_CODE_FIELDNAME,
            "property": "reqd",
        },
    )
    if reqd_property_setter_name:
        frappe.db.set_value(
            "Property Setter", reqd_property_setter_name, "value", "0"
        )


def sync_so_item_fakt_visibility():
    """SO items jadvalida tarozi faktini ko'rsatish (egasi talabi 2026-09-30).
    Maydonlar add_navbat_item_fields patchida yaratilgan — bu yerda faqat
    ko'rinish xususiyati yangilanadi."""
    cf = frappe.db.get_value(
        "Custom Field",
        {"dt": "Sales Order Item", "fieldname": "custom_fakt_kg"},
        "name",
    )
    if cf:
        frappe.db.set_value(
            "Custom Field", cf, {"in_list_view": 1, "columns": 1}
        )
        frappe.clear_cache(doctype="Sales Order")


def sync_production_entry_list_settings():
    """Production Entry ro'yxatida ishlab chiqarilayotgan miqdor ustunini ko'rsatish.

    Frappe list view ustunlar sonini cheklaydi, natijada `qty_to_manufacture`
    (BOM No / "ВМ №" dan keyingi maydon) kesib tashlanadi. `total_fields` ni
    ko'tarib, uni doimiy ko'rinadigan qilamiz.
    """
    if frappe.db.exists("List View Settings", PRODUCTION_ENTRY_DOCTYPE):
        frappe.db.set_value(
            "List View Settings",
            PRODUCTION_ENTRY_DOCTYPE,
            "total_fields",
            PRODUCTION_ENTRY_LIST_TOTAL_FIELDS,
        )
    else:
        doc = frappe.new_doc("List View Settings")
        doc.name = PRODUCTION_ENTRY_DOCTYPE
        doc.total_fields = PRODUCTION_ENTRY_LIST_TOTAL_FIELDS
        doc.insert(ignore_permissions=True)

    frappe.clear_cache(doctype=PRODUCTION_ENTRY_DOCTYPE)


def after_install():
    sync_custom_fields()
    sync_so_item_fakt_visibility()
    sync_production_entry_list_settings()
    create_nakladnaya_print_format()


def after_migrate():
    sync_custom_fields()
    sync_so_item_fakt_visibility()
    sync_production_entry_list_settings()
    create_nakladnaya_print_format()


def create_nakladnaya_print_format():
    html = Path(__file__).parent.joinpath(
        "print_formats", "sales_invoice_nakladnaya.html"
    ).read_text(encoding="utf-8")

    # Logo data-URI sifatida joylanadi — wkhtmltopdf tarmoqdan rasm olmasin
    # (saytga HTTP so'rov HostNotFoundError berishi mumkin).
    logo_path = Path(__file__).parent.joinpath("public", "images", "burxanov_logo.png")
    if logo_path.exists():
        import base64

        logo_src = "data:image/png;base64," + base64.b64encode(
            logo_path.read_bytes()
        ).decode()
    else:
        logo_src = "/assets/pokiza/images/burxanov_logo.png"
    html = html.replace("__POKIZA_LOGO_SRC__", logo_src)

    values = {
        "doc_type": "Sales Invoice",
        "module": "Pokiza for business",
        "custom_format": 1,
        "standard": "No",
        "print_format_for": "DocType",
        "print_format_type": "Jinja",
        "print_format_builder": 0,
        "print_format_builder_beta": 0,
        "raw_printing": 0,
        "disabled": 0,
        "font": "Calibri",
        "font_size": 12,
        "page_number": "Hide",
        "margin_top": 0,
        "margin_bottom": 0,
        "margin_left": 0,
        "margin_right": 0,
        "html": html,
    }

    if frappe.db.exists("Print Format", NAKLADNAYA_PRINT_FORMAT):
        print_format = frappe.get_doc("Print Format", NAKLADNAYA_PRINT_FORMAT)
        print_format.update(values)
        print_format.save(ignore_permissions=True)
    else:
        print_format = frappe.get_doc(
            {
                "doctype": "Print Format",
                "name": NAKLADNAYA_PRINT_FORMAT,
                **values,
            }
        )
        print_format.insert(ignore_permissions=True)

    property_setter = frappe.db.exists(
        "Property Setter",
        {
            "doctype_or_field": "DocType",
            "doc_type": "Sales Invoice",
            "property": "default_print_format",
        },
    )
    if property_setter:
        frappe.db.set_value(
            "Property Setter", property_setter, "value", NAKLADNAYA_PRINT_FORMAT
        )
    else:
        frappe.make_property_setter(
            {
                "doctype_or_field": "DocType",
                "doctype": "Sales Invoice",
                "property": "default_print_format",
                "property_type": "Data",
                "value": NAKLADNAYA_PRINT_FORMAT,
            }
        )

    # Qoralama (draft) schyotda ham nakladnoy PDF chiqishi uchun
    if not frappe.db.get_single_value("Print Settings", "allow_print_for_draft"):
        frappe.db.set_single_value("Print Settings", "allow_print_for_draft", 1)

    frappe.clear_cache(doctype="Sales Invoice")
