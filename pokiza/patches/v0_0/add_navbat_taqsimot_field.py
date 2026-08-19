# Sales Order'ga kun taqsimot child jadvali (zakaz bir necha kunga bo'linadi).
# Qo'shimcha: custom_ishlab_chiqarish_kuni endi "bitish kuni" ma'nosida —
# label yangilanadi; mavjud submit zakazlarga bitta-kunlik taqsimot yoziladi
# (aks holda sig'im hisobida ko'rinmay qoladi).

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import flt


def execute():
	create_custom_fields(
		{
			"Sales Order": [
				{
					"fieldname": "custom_kun_taqsimot",
					"label": "Kunlarga taqsimot",
					"fieldtype": "Table",
					"options": "Kun Taqsimot Qatori",
					"insert_after": "custom_kg_nomalum",
					"read_only": 1,
					"allow_on_submit": 1,
					"no_copy": 1,
					"print_hide": 1,
				},
			]
		},
		update=True,
	)

	# endi bu maydon = reja bo'yicha OXIRGI (bitish) kun
	frappe.db.set_value(
		"Custom Field",
		{"dt": "Sales Order", "fieldname": "custom_ishlab_chiqarish_kuni"},
		"label",
		"Ishlab chiqarish bitish kuni",
	)

	# eski submit zakazlar: kuni bor, taqsimoti yo'q -> bitta qator
	for so in frappe.get_all(
		"Sales Order",
		filters={"docstatus": 1, "custom_ishlab_chiqarish_kuni": ("is", "set")},
		fields=["name", "custom_ishlab_chiqarish_kuni", "custom_jami_kg"],
	):
		if frappe.db.exists(
			"Kun Taqsimot Qatori",
			{"parenttype": "Sales Order", "parent": so.name},
		):
			continue
		frappe.get_doc({
			"doctype": "Kun Taqsimot Qatori",
			"parenttype": "Sales Order",
			"parent": so.name,
			"parentfield": "custom_kun_taqsimot",
			"idx": 1,
			"sana": so.custom_ishlab_chiqarish_kuni,
			"kg": flt(so.custom_jami_kg),
		}).insert(ignore_permissions=True)
