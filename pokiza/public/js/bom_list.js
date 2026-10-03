// BOM ro'yxati: sotuv mahsuloti BOM'lari RANG bilan ajratiladi
// (egasi 2026-10-03). 🛒 binafsha = sotuv SKU (upakovkali) BOMi,
// qolganlari standart holat ranglarida (norma/farsh BOMlari).
frappe.listview_settings["BOM"] = frappe.listview_settings["BOM"] || {};

(function (s) {
	const eski_fields = s.add_fields || [];
	s.add_fields = [...new Set([...eski_fields, "custom_sotuv_sku", "is_active", "is_default"])];

	s.get_indicator = function (doc) {
		if (doc.custom_sotuv_sku) {
			return [__("🛒 Sotuv SKU"), "purple", "custom_sotuv_sku,=,1"];
		}
		if (doc.is_default) {
			return [__("Default"), "green", "is_default,=,1"];
		}
		if (doc.is_active) {
			return [__("Active"), "blue", "is_active,=,1"];
		}
		return [__("Not active"), "gray", "is_active,=,0"];
	};
})(frappe.listview_settings["BOM"]);
