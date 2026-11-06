"""Faqat-o'qish SQL: tekshiruv va alohida read-only MariaDB ulanishi.

Asosiy himoya — MariaDB'dagi `pokiza_ai_ro` user (faqat SELECT, sezgir jadvallarsiz).
Bu modul ikkinchi qatlam: noto'g'ri so'rovni bazaga yetmasdan rad etadi.
"""
import re

import frappe

from pokiza.ai.tools import DENY_DOCTYPES, ToolError

MAX_ROWS = 500
TIMEOUT_SEC = 15

DENY_TABLES = {f"tab{d}".lower() for d in DENY_DOCTYPES} | {
    "__auth", "__usersettings", "tabsessions", "tabdefaultvalue", "tabversion",
    "tabcommunication", "tabemail queue", "tabemail queue recipient", "tabprepared report",
    "tabsingles", "tabdeleted document",  # Single sozlamalar (tokenlar bo'lishi mumkin), o'chirilgan hujjatlar
}
FORBIDDEN = re.compile(
    # REPLACE() funksiyasi va boshqa oddiy so'zlar ataylab yo'q: bitta SELECT bo'lgani uchun
    # DML baribir bajarilmaydi, asosiy cheklov — read-only user.
    r"\b(insert|update|delete|drop|alter|create|truncate|rename|grant|revoke|call|handler|into|"
    r"load_file|outfile|dumpfile|sleep|benchmark|get_lock|release_lock|"
    r"information_schema|performance_schema|mysql|lock\s+in\s+share\s+mode)\b",
    re.IGNORECASE,
)


def _strip(sql):
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    sql = re.sub(r"(--|#)[^\n]*", " ", sql)
    return sql.strip().rstrip(";").strip()


def _without_literals(sql):
    return re.sub(r"'(?:[^'\\]|\\.|'')*'|\"(?:[^\"\\]|\\.)*\"", "''", sql)


def validate(sql):
    sql = _strip(sql or "")
    if not sql:
        raise ToolError("SQL bo'sh")
    bare = _without_literals(sql)
    if ";" in bare:
        raise ToolError("Faqat bitta SELECT so'rov ruxsat etiladi")
    if not re.match(r"^\s*(select|with)\b", bare, re.I):
        raise ToolError("Faqat SELECT (yoki WITH ... SELECT) ruxsat etiladi")
    if FORBIDDEN.search(re.sub(r"`[^`]*`", "``", bare)):
        raise ToolError("So'rovda taqiqlangan kalit so'z bor (faqat o'qish mumkin)")
    names = re.findall(r"`([^`]+)`", bare) + re.findall(r"\b(tab\w+|__\w+)\b", re.sub(r"`[^`]*`", "``", bare))
    for t in names:
        if t.lower() in DENY_TABLES:
            raise ToolError(f"`{t}` jadvali ruxsat etilmagan")
    return sql


def connect():
    import pymysql

    from pokiza.ai.client import get_secret, get_settings

    s = get_settings()
    password = get_secret("db_ro_password")
    if not (s.db_ro_user and password):
        raise ToolError("SQL tool sozlanmagan (read-only DB user/parol yo'q). report va boshqa tool'larni ishlat.")
    conn = pymysql.connect(
        host=frappe.conf.db_host or "127.0.0.1",
        port=int(frappe.conf.db_port or 3306),
        user=s.db_ro_user,
        password=password,
        database=frappe.conf.db_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5,
        read_timeout=TIMEOUT_SEC + 5,
    )
    with conn.cursor() as cur:
        cur.execute(f"SET SESSION max_statement_time = {TIMEOUT_SEC}")
        cur.execute("SET SESSION TRANSACTION READ ONLY")
    return conn


def run_select(sql, max_rows=MAX_ROWS):
    sql = validate(sql)
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchmany(max_rows + 1)
            columns = [d[0] for d in cur.description or []]
    except Exception as e:
        raise ToolError(f"SQL xatosi: {str(e)[:500]}")
    finally:
        conn.close()
    truncated = len(rows) > max_rows
    return columns, rows[:max_rows], truncated
