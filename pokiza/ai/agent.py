"""Agent loop: Claude bilan suhbat, tool chaqiruvlari, realtime streaming.

Background job'da ishlaydi (pokiza.ai.api.send_message enqueue qiladi).
Tarix append-only: Claude qaytargan content bloklar (thinking bilan) o'zgarishsiz saqlanadi
va keyingi so'rovlarda shundayligicha qaytariladi.
"""
import json
import time

import frappe
from frappe.utils import now_datetime

from pokiza.ai.attachments import expand_content
from pokiza.ai.client import get_client, get_settings, usage_cost
from pokiza.ai.prompt import SYSTEM_PROMPT, user_preamble
from pokiza.ai.voice import VoiceError, prepare_voice
from pokiza.ai.tools import run_tool, tool_specs

EVENT = "pokiza_ai"
FLUSH_SEC = 0.15
MAX_TOKENS = 32000


def stop_key(xabar):
    return f"pokiza_ai_stop:{xabar}"


class Publisher:
    def __init__(self, user, suhbat, xabar):
        self.user, self.suhbat, self.xabar = user, suhbat, xabar
        self.buf, self.last = [], 0.0

    def send(self, type_, **data):
        frappe.publish_realtime(EVENT, {"suhbat": self.suhbat, "xabar": self.xabar, "type": type_, **data}, user=self.user)

    def text(self, chunk, kind="text"):
        self.buf.append((kind, chunk))
        if time.monotonic() - self.last >= FLUSH_SEC:
            self.flush()

    def flush(self):
        if not self.buf:
            return
        merged = {}
        for kind, chunk in self.buf:
            merged[kind] = merged.get(kind, "") + chunk
        for kind, chunk in merged.items():
            self.send("delta", kind=kind, text=chunk)
        self.buf, self.last = [], time.monotonic()


def _dump(content):
    return [b.model_dump(mode="json", exclude_none=True) for b in content]


def build_history(suhbat, upto_xabar):
    """Joriy javobgacha bo'lgan barcha API xabarlari."""
    rows = frappe.get_all(
        "AI Xabar",
        filters={"suhbat": suhbat, "name": ["!=", upto_xabar]},
        fields=["role", "content_json", "api_messages_json"],
        order_by="creation asc",
    )
    messages = []
    for r in rows:
        if r.role == "user":
            messages.append({"role": "user", "content": expand_content(json.loads(r.content_json))})
        else:
            msgs = json.loads(r.api_messages_json or "[]")
            messages.extend(msgs or [{"role": "assistant", "content": [{"type": "text", "text": "(javob berilmadi)"}]}])
    return messages


def _close_turn(turn, note):
    """To'xtatilgan/xato bo'lgan navbatni API uchun yaroqli holatda yakunlash (faqat oxiriga qo'shiladi)."""
    if turn and turn[-1]["role"] == "assistant":
        pending = [b for b in turn[-1]["content"] if b.get("type") == "tool_use"]
        if pending:
            turn.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": b["id"], "content": note, "is_error": True}
                        for b in pending
                    ],
                }
            )
    if not turn or turn[-1]["role"] == "user":
        turn.append({"role": "assistant", "content": [{"type": "text", "text": f"({note})"}]})


def _text_of(turn):
    parts = []
    for m in turn:
        if m["role"] == "assistant":
            parts += [b["text"] for b in m["content"] if b.get("type") == "text" and b.get("text")]
    return "\n\n".join(parts).strip()


def run(suhbat, xabar):
    user = frappe.session.user
    pub = Publisher(user, suhbat, xabar)
    s = get_settings()
    turn, audit = [], []
    totals = {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0, "cost_usd": 0.0}
    status, error, stop_reason, model = "Tayyor", None, None, s.model
    # create_file tool'i uchun kontekst
    frappe.local.pokiza_ai = {
        "suhbat": suhbat,
        "files": [],
        "dashboards": [],
        "on_file": lambda f: pub.send("file", file=f),
        "on_dashboard": lambda d: pub.send("dashboard", dashboard=d),
    }
    files, dashboards = frappe.local.pokiza_ai["files"], frappe.local.pokiza_ai["dashboards"]

    try:
        client = get_client()
        prepare_voice(suhbat, xabar, pub.send)
        history = build_history(suhbat, xabar)
        tools = tool_specs(sql_enabled=s.sql_enabled)
        retried_bad_json = False

        for _step in range(int(s.max_steps)):
            if frappe.cache.get_value(stop_key(xabar)):
                status = "To'xtatildi"
                break

            pub.send("status", text="O'ylayapti…")
            stopped, last_stop_check = False, time.monotonic()
            try:
                with client.beta.messages.stream(
                    model=s.model,
                    max_tokens=MAX_TOKENS,
                    system=SYSTEM_PROMPT,
                    tools=tools,
                    messages=history + turn,
                    thinking={"type": "adaptive", "display": "summarized"},
                    output_config={"effort": s.effort},
                    cache_control={"type": "ephemeral"},
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                ) as stream:
                    for event in stream:
                        if event.type == "content_block_start":
                            if event.content_block.type == "tool_use":
                                pub.flush()
                                pub.send("tool_start", name=event.content_block.name)
                        elif event.type == "content_block_delta":
                            if event.delta.type == "text_delta":
                                pub.text(event.delta.text)
                            elif event.delta.type == "thinking_delta":
                                pub.text(event.delta.thinking, kind="thinking")
                        if time.monotonic() - last_stop_check > 0.5:
                            last_stop_check = time.monotonic()
                            if frappe.cache.get_value(stop_key(xabar)):
                                stopped = True
                                break
                    pub.flush()
                    if stopped:
                        status = "To'xtatildi"
                        break
                    msg = stream.get_final_message()
            except ValueError:
                # eager_input_streaming: tool input JSON buzilgan — so'rovni bir marta qayta yuboramiz
                if retried_bad_json:
                    raise
                retried_bad_json = True
                continue

            model = msg.model
            for k, attr in (
                ("input_tokens", "input_tokens"),
                ("output_tokens", "output_tokens"),
                ("cache_read_tokens", "cache_read_input_tokens"),
                ("cache_write_tokens", "cache_creation_input_tokens"),
            ):
                totals[k] += getattr(msg.usage, attr, 0) or 0
            totals["cost_usd"] += usage_cost(msg.model, msg.usage)
            stop_reason = msg.stop_reason

            content = _dump(msg.content)
            turn.append({"role": "assistant", "content": content})

            if stop_reason == "pause_turn":
                continue
            if stop_reason == "refusal":
                status, error = "Xato", "Model so'rovni rad etdi"
                break
            if stop_reason != "tool_use":
                # end_turn / max_tokens / stop_sequence
                break

            results = []
            for block in content:
                if block.get("type") != "tool_use":
                    continue
                pub.send("tool_run", name=block["name"], input=block.get("input"))
                result, is_error, a = run_tool(block["name"], block.get("input") or {})
                audit.append(a)
                pub.send("tool_end", name=block["name"], is_error=is_error)
                results.append(
                    {"type": "tool_result", "tool_use_id": block["id"], "content": result, "is_error": is_error}
                )
            turn.append({"role": "user", "content": results})
        else:
            status, error = "Xato", f"Qadamlar limiti ({s.max_steps}) tugadi"

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(title="Pokiza AI agent xatosi")
        status, error = "Xato", _friendly_error(e)

    display_text = _text_of(turn)
    # oxirgi xabar javobsiz tool_use yoki user bo'lsa — yaroqli holatga keltiramiz (normal javobda hech narsa qo'shmaydi)
    _close_turn(turn, error or "to'xtatildi")
    if stop_reason == "max_tokens" and not error:
        error = "Javob uzunlik limitiga yetdi"

    frappe.local.pokiza_ai = None
    _save(suhbat, xabar, display_text, turn, audit, totals, status, error, stop_reason, model, files, dashboards)
    frappe.cache.delete_value(stop_key(xabar))
    pub.send("done", status=status, error=error, text=display_text, cost_usd=totals["cost_usd"])


def _friendly_error(e):
    import anthropic

    if isinstance(e, anthropic.RateLimitError):
        return "Claude API limiti: biroz kutib qayta urinib ko'ring"
    if isinstance(e, anthropic.APIConnectionError):
        return "Claude API'ga ulanib bo'lmadi (internet/proxy)"
    if isinstance(e, anthropic.AuthenticationError):
        return "API key noto'g'ri"
    if isinstance(e, anthropic.APIStatusError):
        return f"Claude API xatosi {e.status_code}: {str(e.message)[:300]}"
    if isinstance(e, VoiceError):
        return str(e)
    if isinstance(e, frappe.ValidationError):
        return str(e)
    return f"Ichki xato: {type(e).__name__}"


def _save(suhbat, xabar, text, turn, audit, totals, status, error, stop_reason, model, files=None, dashboards=None):
    frappe.db.set_value(
        "AI Xabar",
        xabar,
        {
            "text": text,
            "api_messages_json": json.dumps(turn, ensure_ascii=False),
            "tool_calls_json": json.dumps(audit, ensure_ascii=False, default=str),
            "files_json": json.dumps(files or [], ensure_ascii=False),
            "dashboards_json": json.dumps(dashboards or [], ensure_ascii=False, default=str),
            "status": status,
            "error": error,
            "stop_reason": stop_reason,
            "model": model,
            **totals,
        },
        update_modified=False,
    )
    total = frappe.db.get_value("AI Suhbat", suhbat, "total_cost_usd") or 0
    frappe.db.set_value(
        "AI Suhbat",
        suhbat,
        {
            "status": "Xato" if status == "Xato" else "Tayyor",
            "last_message_at": now_datetime(),
            "total_cost_usd": total + totals["cost_usd"],
        },
    )
    frappe.db.commit()


def run_sync(text, suhbat=None):
    """Konsoldan sinash: bench --site X execute pokiza.ai.agent.run_sync --kwargs "{'text': '...'}" """
    from pokiza.ai.api import _create_messages

    suhbat, _user_xabar, xabar = _create_messages(text, suhbat)
    frappe.db.commit()
    run(suhbat, xabar)
    row = frappe.db.get_value("AI Xabar", xabar, ["status", "error", "text", "tool_calls_json", "cost_usd"], as_dict=True)
    print("STATUS:", row.status, row.error or "")
    for a in json.loads(row.tool_calls_json or "[]"):
        print("TOOL:", a["name"], json.dumps(a["input"], ensure_ascii=False)[:300], "ERR" if a["is_error"] else "", f"{a['ms']}ms")
    for f in json.loads(frappe.db.get_value("AI Xabar", xabar, "files_json") or "[]"):
        print("FILE:", f["file_name"], f["file_url"])
    print("COST: $%.4f" % (row.cost_usd or 0))
    print(row.text)
    return suhbat
