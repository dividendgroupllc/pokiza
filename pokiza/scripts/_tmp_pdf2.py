import re
import frappe

SCR = "/tmp/claude-1000/-home-user-frappe-bench/2ed77911-9a38-404d-9712-4e6ee80c801b/scratchpad/"


def dump():
    frappe.conf["host_name"] = "http://localhost:8000"
    si = frappe.db.get_value("Sales Invoice", {"docstatus": 1}, "name",
                             order_by="creation desc")
    html = frappe.get_print(doctype="Sales Invoice", name=si,
                            print_format="Накладная Pokiza", no_letterhead=1)
    open(SCR + "nakl.html", "w").write(html)
    print("zoom bormi:", "zoom:" in html, "| html,body reset:", "html, body {" in html)
    # print-format konteyneri atrofidagi markup
    i = html.find('class="print-format')
    print("...", html[max(0, i - 400):i + 200].replace("\n", " ")[-620:])
    # tashqi css'dagi body/padding qoidalari
    for m in re.finditer(r"(body|\.print-format)[^{]*\{[^}]*\}", html):
        t = m.group(0)
        if "padding" in t or "margin" in t or "width" in t:
            print("CSS>", " ".join(t.split())[:160])
