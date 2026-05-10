"""
bot.py — Telegram bot for the Inventory Management System.

Usage (polling mode):  python bot.py
For webhook mode, the Flask app handles incoming updates via /webhook/<token>.

Set env vars:
  TELEGRAM_TOKEN     — your bot token from @BotFather
  INCHARGE_IDS       — comma-separated Telegram user IDs allowed to update status
  ALLOWED_CHAT_IDS   — comma-separated group/chat IDs to monitor (leave blank = all)
"""

import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv

import database as db
from parser import parse_message, parse_command_update, parse_add_item

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [BOT] %(levelname)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────

# --- Environment variable checks ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
INCHARGE_IDS = os.getenv("INCHARGE_IDS")
ALLOWED_CHATS = os.getenv("ALLOWED_CHAT_IDS", "")

missing_env = []
if not TOKEN:
    missing_env.append("TELEGRAM_TOKEN")
if not INCHARGE_IDS:
    missing_env.append("INCHARGE_IDS")
if missing_env:
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing_env)}")

INCHARGE_IDS = set(int(x) for x in INCHARGE_IDS.split(",") if x.strip().isdigit())
ALLOWED_CHATS = set(int(x) for x in ALLOWED_CHATS.split(",") if x.strip().lstrip("-").isdigit())

# Status emoji map
STATUS_EMOJI = {
    "available":    "✅",
    "low":          "⚠️",
    "not_available":"❌",
    "ordered":      "📦",
    "pending":      "🕐",
    "received":     "✅",
    "done":         "✅",
    "cancelled":    "🚫",
}


def is_incharge(user_id: int) -> bool:
    """Check if a user is authorized to update inventory."""
    if not INCHARGE_IDS:
        return True   # Open mode: everyone can update (useful for testing)
    return user_id in INCHARGE_IDS


def is_allowed_chat(chat_id: int) -> bool:
    if not ALLOWED_CHATS:
        return True
    return chat_id in ALLOWED_CHATS


# ─── Telegram API helpers ─────────────────────────────────────────────────────

def tg_post(method: str, data: dict):
    """Make a Telegram Bot API call."""
    import urllib.request
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    payload = json.dumps(data).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        log.error("Telegram API error [%s]: %s", method, e)
        return None


def send_message(chat_id: int, text: str, reply_to: int = None, parse_mode: str = "HTML"):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    return tg_post("sendMessage", payload)


# ─── Command handlers ─────────────────────────────────────────────────────────

def handle_start(update: dict):
    chat_id = update["message"]["chat"]["id"]
    user    = update["message"]["from"]
    db.ensure_user(user["id"], user.get("username"), user.get("first_name"))
    text = (
        "👋 <b>Inventory Bot Online</b>\n\n"
        "I track inventory from group chat messages.\n\n"
        "<b>Commands:</b>\n"
        "  /add [item] [qty] — Add an item\n"
        "  /update [item] [status] — Update status\n"
        "  /stock — Show all inventory\n"
        "  /low — Show low/out-of-stock items\n"
        "  /status — Bot status\n\n"
        "<b>Chat commands (reply to any message):</b>\n"
        "  available · not available · ordered\n"
        "  received · done · cancel · low\n\n"
        "Just chat naturally — I understand!"
    )
    send_message(chat_id, text)


def handle_stock(update: dict):
    chat_id = update["message"]["chat"]["id"]
    items   = db.get_all_inventory()
    if not items:
        send_message(chat_id, "📦 No inventory items yet. Use /add to start.")
        return

    lines = ["<b>📦 Current Inventory</b>\n"]
    for item in items:
        emoji = STATUS_EMOJI.get(item["status"], "•")
        lines.append(
            f"{emoji} <b>{item['item_name']}</b>  "
            f"{item['quantity']} {item['unit']}  "
            f"<i>({item['status']})</i>"
        )
    send_message(chat_id, "\n".join(lines))


def handle_low(update: dict):
    chat_id = update["message"]["chat"]["id"]
    items   = db.get_low_stock()
    if not items:
        send_message(chat_id, "✅ All items are sufficiently stocked!")
        return

    lines = ["<b>⚠️ Low / Out-of-Stock Items</b>\n"]
    for item in items:
        emoji = STATUS_EMOJI.get(item["status"], "•")
        lines.append(
            f"{emoji} <b>{item['item_name']}</b> — "
            f"{item['quantity']} {item['unit']}"
        )
    send_message(chat_id, "\n".join(lines))


def handle_status_cmd(update: dict):
    chat_id = update["message"]["chat"]["id"]
    stats   = db.get_stats()
    text = (
        f"<b>📊 System Status</b>\n\n"
        f"Total items:     {stats['total_items']}\n"
        f"✅ Available:    {stats['available']}\n"
        f"⚠️  Low stock:   {stats['low_stock']}\n"
        f"❌ Out of stock: {stats['out_of_stock']}\n"
        f"📦 Ordered:      {stats['ordered']}\n\n"
        f"🕐 Pending requests: {stats['pending_requests']}\n"
        f"📦 Ordered requests: {stats['ordered_requests']}"
    )
    send_message(chat_id, text)


def handle_add_cmd(update: dict):
    """Handle /add <item> [qty] [unit]"""
    msg     = update["message"]
    user    = msg["from"]
    chat_id = msg["chat"]["id"]
    text    = msg.get("text", "")
    db.ensure_user(user["id"], user.get("username"), user.get("first_name"))

    parsed = parse_add_item(text)
    if not parsed:
        send_message(chat_id, "Usage: /add <item name> [quantity] [unit]\nExample: /add Rice 50 kg")
        return

    item = db.upsert_item(
        item_name=parsed["item_name"],
        quantity=parsed["quantity"],
        unit=parsed["unit"],
        actor_id=user["id"],
    )
    db.log_event(
        "item_added",
        parsed["item_name"],
        actor_id=user["id"],
        actor_name=user.get("first_name"),
        detail=f"qty={parsed['quantity']} {parsed['unit']}",
        raw_message=text,
    )
    send_message(
        chat_id,
        f"✅ Added <b>{item['item_name']}</b> — {item['quantity']} {item['unit']}",
        reply_to=msg["message_id"],
    )


def handle_update_cmd(update: dict):
    """Handle /update <item> <status> [qty]"""
    msg     = update["message"]
    user    = msg["from"]
    chat_id = msg["chat"]["id"]
    text    = msg.get("text", "")
    db.ensure_user(user["id"], user.get("username"), user.get("first_name"))

    if not is_incharge(user["id"]):
        send_message(chat_id, "⛔ You are not authorized to update inventory.", reply_to=msg["message_id"])
        return

    parsed = parse_command_update(text)
    if not parsed:
        send_message(
            chat_id,
            "Usage: /update <item name> <status>\n"
            "Status options: available · not_available · low · ordered\n"
            "Example: /update Rice available",
            reply_to=msg["message_id"],
        )
        return

    item = db.update_item_status(parsed["item_name"], parsed["status"], user["id"])
    if not item:
        # Item doesn't exist — create it
        item = db.upsert_item(parsed["item_name"], 0, parsed["status"], actor_id=user["id"])

    db.log_event(
        "status_update",
        parsed["item_name"],
        actor_id=user["id"],
        actor_name=user.get("first_name"),
        detail=f"status → {parsed['status']}",
        raw_message=text,
    )
    emoji = STATUS_EMOJI.get(parsed["status"], "•")
    send_message(
        chat_id,
        f"{emoji} <b>{item['item_name']}</b> marked as <b>{parsed['status']}</b>",
        reply_to=msg["message_id"],
    )


# ─── Free-form message parser ─────────────────────────────────────────────────

def handle_free_message(update: dict):
    """
    Handles natural language messages and reply-based status updates.
    """
    msg     = update["message"]
    user    = msg["from"]
    chat_id = msg["chat"]["id"]
    text    = msg.get("text", "") or msg.get("caption", "")

    if not text:
        return

    db.ensure_user(user["id"], user.get("username"), user.get("first_name"))

    # ── Reply context: update request status ──────────────────────────────────
    reply_to_msg = msg.get("reply_to_message")
    parsed = parse_message(text)

    if reply_to_msg and parsed.intent:
        # The message is a reply + has a valid command → status update
        original_text = reply_to_msg.get("text", "") or reply_to_msg.get("caption", "")
        original_parsed = parse_message(original_text)

        if not is_incharge(user["id"]):
            send_message(
                chat_id,
                "⛔ Only incharge staff can update status.",
                reply_to=msg["message_id"],
            )
            return

        # Determine which item to update
        item_name = parsed.item_name or original_parsed.item_name

        if parsed.intent in ("received", "done", "cancelled"):
            # Update pending requests
            reqs = db.get_requests("pending") + db.get_requests("ordered")
            matched_req = next(
                (r for r in reqs if item_name and r["item_name"].lower() == item_name.lower()),
                None,
            )
            if matched_req:
                db.update_request_status(matched_req["id"], parsed.intent)
                db.log_event(
                    "request_update",
                    item_name,
                    actor_id=user["id"],
                    actor_name=user.get("first_name"),
                    detail=f"request#{matched_req['id']} → {parsed.intent}",
                    raw_message=text,
                )

        if item_name:
            # Map intent to inventory status
            inv_status_map = {
                "available":     "available",
                "not_available": "not_available",
                "low":           "low",
                "ordered":       "ordered",
                "received":      "available",
                "done":          "available",
                "cancelled":     "not_available",
            }
            inv_status = inv_status_map.get(parsed.intent)
            if inv_status:
                item = db.update_item_status(item_name, inv_status, user["id"])
                if not item:
                    item = db.upsert_item(item_name, parsed.quantity or 0, inv_status, actor_id=user["id"])

                db.log_event(
                    "status_update",
                    item_name,
                    actor_id=user["id"],
                    actor_name=user.get("first_name"),
                    detail=f"via reply: {text[:80]}",
                    raw_message=text,
                )
                emoji = STATUS_EMOJI.get(inv_status, "•")
                send_message(
                    chat_id,
                    f"{emoji} <b>{item_name}</b> → <b>{inv_status}</b>",
                    reply_to=msg["message_id"],
                )
        return

    # ── Standalone message with item + intent → create request or update ──────
    if parsed.intent and parsed.item_name:
        actor_name = user.get("first_name", "Unknown")
        log.info("[PARSE] %s: intent=%s item=%s qty=%s",
                 actor_name, parsed.intent, parsed.item_name, parsed.quantity)

        if parsed.intent in ("not_available", "low"):
            # Someone is reporting low stock → create a request
            req_id = db.create_request(
                parsed.item_name,
                user["id"],
                quantity=parsed.quantity or 1,
                message_id=msg["message_id"],
                chat_id=chat_id,
                notes=text[:200],
            )
            db.log_event(
                "request_created",
                parsed.item_name,
                actor_id=user["id"],
                actor_name=actor_name,
                detail=f"qty={parsed.quantity}, req#{req_id}",
                raw_message=text,
            )

            # Also update inventory status
            existing = db.get_item(parsed.item_name)
            if existing:
                db.update_item_status(parsed.item_name, parsed.intent, user["id"])
            else:
                db.upsert_item(parsed.item_name, parsed.quantity or 0, parsed.intent,
                               actor_id=user["id"])

            send_message(
                chat_id,
                f"⚠️ <b>{parsed.item_name}</b> reported as {parsed.intent}. "
                f"Request #{req_id} created.",
                reply_to=msg["message_id"],
            )

        elif parsed.intent == "available" and is_incharge(user["id"]):
            db.upsert_item(parsed.item_name, parsed.quantity or 0, "available", actor_id=user["id"])
            db.log_event(
                "status_update",
                parsed.item_name,
                actor_id=user["id"],
                actor_name=actor_name,
                detail=f"available, qty={parsed.quantity}",
                raw_message=text,
            )
            send_message(
                chat_id,
                f"✅ <b>{parsed.item_name}</b> marked available.",
                reply_to=msg["message_id"],
            )

        elif parsed.intent == "ordered" and is_incharge(user["id"]):
            db.update_item_status(parsed.item_name, "ordered", user["id"])
            db.log_event(
                "status_update",
                parsed.item_name,
                actor_id=user["id"],
                actor_name=actor_name,
                detail="ordered",
                raw_message=text,
            )
            send_message(
                chat_id,
                f"📦 <b>{parsed.item_name}</b> marked as ordered.",
                reply_to=msg["message_id"],
            )


# ─── Update dispatcher ────────────────────────────────────────────────────────

COMMAND_HANDLERS = {
    "/start":  handle_start,
    "/help":   handle_start,
    "/stock":  handle_stock,
    "/low":    handle_low,
    "/status": handle_status_cmd,
    "/add":    handle_add_cmd,
    "/update": handle_update_cmd,
}


def process_update(update: dict):
    """Route a single Telegram update to the right handler."""
    try:
        msg = update.get("message") or update.get("edited_message")
        if not msg:
            return

        chat_id = msg["chat"]["id"]
        if not is_allowed_chat(chat_id):
            return

        text = msg.get("text", "") or msg.get("caption", "")
        if not text:
            return

        # Slash command routing
        first_word = text.split()[0].split("@")[0].lower() if text else ""
        if first_word in COMMAND_HANDLERS:
            COMMAND_HANDLERS[first_word](update)
        else:
            handle_free_message(update)

    except Exception as e:
        log.exception("Error processing update: %s", e)


# ─── Polling runner ───────────────────────────────────────────────────────────

def run_polling():
    import time
    offset = 0
    log.info("🤖 Bot starting in polling mode…")
    db.init_db()

    while True:
        try:
            import urllib.request
            url = f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={offset}&timeout=30"
            with urllib.request.urlopen(url, timeout=35) as resp:
                data = json.loads(resp.read())

            if data.get("ok"):
                for update in data.get("result", []):
                    process_update(update)
                    offset = update["update_id"] + 1

        except Exception as e:
            log.error("Polling error: %s", e)
            time.sleep(5)


if __name__ == "__main__":
    run_polling()
