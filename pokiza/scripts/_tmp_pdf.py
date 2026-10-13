import frappe
from frappe.utils.pdf import get_pdf

SCR = "/tmp/claude-1000/-home-user-frappe-bench/2ed77911-9a38-404d-9712-4e6ee80c801b/scratchpad/"


def yarat(si=None, nom="nakl_hozir"):
    frappe.conf["host_name"] = "http://localhost:8000"
    if not si:
        si = frappe.db.get_value("Sales Invoice", {"docstatus": 1}, "name",
                                 order_by="creation desc")
    html = frappe.get_print(doctype="Sales Invoice", name=si,
                            print_format="Накладная Pokiza", no_letterhead=1)
    with open(SCR + nom + ".pdf", "wb") as f:
        f.write(get_pdf(html))
    print("yozildi:", nom, si)


def kop():
    yarat("ACC-SINV-2026-00732", "nakl_kop")


def kop2():
    import traceback
    try:
        yarat("ACC-SINV-2026-00732", "nakl_kop")
    except Exception:
        traceback.print_exc()


def kop3():
    yarat("ACC-SINV-2026-01300", "nakl_kop")
