"""
app.py — Flask REST API for the Inventory Bot dashboard.
Run:  python app.py
"""


import os
import json
import threading
from datetime import datetime
from functools import wraps

from flask import Flask, jsonify, request, render_template, abort, g
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv

import database as db

# --- Load environment variables from .env if present ---
load_dotenv()


app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)

# --- Rate limiting: 100 requests/hour per IP (customize as needed) ---
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["100 per hour"]
)

# ─── Simple API-key auth for write endpoints ──────────────────────────────────
API_SECRET = os.getenv("API_SECRET")

# --- API key security improvement ---
if not API_SECRET:
    raise RuntimeError("Missing required environment variable: API_SECRET")



def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key") or request.args.get("api_key")
        if key != API_SECRET:
            app.logger.warning(f"Unauthorized access attempt from {get_remote_address()}")
            return jsonify({"error": "Unauthorized: Invalid or missing API key."}), 401
        return f(*args, **kwargs)
    return decorated


# ─── Frontend ─────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


# ─── Stats ───────────────────────────────────────────────────────────────────
@app.route("/api/stats")
@require_api_key
def api_stats():
    return jsonify(db.get_stats())


# ─── Inventory ────────────────────────────────────────────────────────────────
@app.route("/api/inventory")
@require_api_key
def api_inventory():
    items = db.get_all_inventory()
    return jsonify({"items": items, "count": len(items)})


@app.route("/api/inventory/low")
@require_api_key
def api_low_stock():
    return jsonify({"items": db.get_low_stock()})


@app.route("/api/inventory/<int:item_id>", methods=["GET"])
@require_api_key
def api_item(item_id):
    with db.get_db() as conn:
        row = conn.execute("SELECT * FROM inventory WHERE id = ?", (item_id,)).fetchone()
    if not row:
        abort(404)
    return jsonify(dict(row))


@app.route("/api/inventory", methods=["POST"])
@require_api_key
@limiter.limit("20/minute")
def api_add_item():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid JSON payload."}), 400
    if not data or "item_name" not in data:
        return jsonify({"error": "'item_name' is required."}), 400
    try:
        item = db.upsert_item(
            item_name=data["item_name"],
            quantity=data.get("quantity", 0),
            status=data.get("status", "available"),
            unit=data.get("unit", "units"),
            category=data.get("category", "general"),
            actor_id=data.get("actor_id"),
            notes=data.get("notes"),
        )
        db.log_event("item_added", item["item_name"], detail=f"qty={item['quantity']}")
        return jsonify(item), 201
    except Exception as e:
        app.logger.error(f"Error adding item: {e}")
        return jsonify({"error": "Failed to add item. Please try again later."}), 500


@app.route("/api/update", methods=["POST"])
@require_api_key
@limiter.limit("20/minute")
def api_update():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid JSON payload."}), 400
    if not data or "item_name" not in data or "status" not in data:
        return jsonify({"error": "'item_name' and 'status' are required."}), 400

    valid_statuses = {"available", "low", "not_available", "ordered"}
    if data["status"] not in valid_statuses:
        return jsonify({"error": f"'status' must be one of {valid_statuses}"}), 400

    try:
        item = db.update_item_status(data["item_name"], data["status"], data.get("actor_id"))
        if not item:
            return jsonify({"error": "Item not found."}), 404
        db.log_event(
            "status_update",
            item["item_name"],
            actor_id=data.get("actor_id"),
            detail=f"status → {data['status']}",
        )
        return jsonify(item)
    except Exception as e:
        app.logger.error(f"Error updating item: {e}")
        return jsonify({"error": "Failed to update item. Please try again later."}), 500


# ─── Requests ─────────────────────────────────────────────────────────────────
@app.route("/api/requests")
@require_api_key
def api_requests():
    status = request.args.get("status")
    reqs = db.get_requests(status)
    return jsonify({"requests": reqs, "count": len(reqs)})


@app.route("/api/requests/<int:req_id>", methods=["PATCH"])
@require_api_key
@limiter.limit("20/minute")
def api_update_request(req_id):
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid JSON payload."}), 400
    status = data.get("status")
    valid_statuses = {"pending", "ordered", "received", "cancelled", "done"}
    if not status:
        return jsonify({"error": "'status' is required."}), 400
    if status not in valid_statuses:
        return jsonify({"error": f"'status' must be one of {valid_statuses}"}), 400
    try:
        ok = db.update_request_status(req_id, status)
    except Exception as e:
        app.logger.error(f"Database error: {e}")
        return jsonify({"error": "Database error. Please try again later."}), 500
    if not ok:
        return jsonify({"error": "Request not found."}), 404
    db.log_event("request_update", detail=f"request#{req_id} → {status}")
    return jsonify({"id": req_id, "status": status})


# ─── Events / Logs ────────────────────────────────────────────────────────────
@app.route("/api/events")
@require_api_key
def api_events():
    limit = int(request.args.get("limit", 200))
    events = db.get_events(limit)
    return jsonify({"events": events, "count": len(events)})


# ─── Bot webhook (for production) / polling fallback ─────────────────────────
@app.route("/webhook/<token>", methods=["POST"])
def webhook(token):
    """Receives Telegram updates via webhook."""
    expected = os.getenv("TELEGRAM_TOKEN", "")
    if token != expected:
        abort(403)
    update_data = request.get_json(force=True)
    # Import here to avoid circular issues at startup
    from bot import process_update
    threading.Thread(target=process_update, args=(update_data,), daemon=True).start()
    return "ok"


# ─── Health check ─────────────────────────────────────────────────────────────
@app.route("/health")
def health():
    stats = db.get_stats()
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat(), **stats})


if __name__ == "__main__":
    db.init_db()
    # Seed some demo data so the dashboard isn't empty on first run
    _demo = [
        ("Rice (Basmati)", 150, "available", "kg", "grains"),
        ("Wheat Flour",     45,  "low",       "kg", "grains"),
        ("Sugar",           80,  "available", "kg", "pantry"),
        ("Cooking Oil",      6,  "low",       "litre", "pantry"),
        ("Salt",             2,  "not_available", "kg", "pantry"),
        ("Lentils (Dal)",   60,  "available", "kg", "grains"),
        ("Milk (Packets)",  20,  "ordered",   "pcs", "dairy"),
        ("Butter",          12,  "available", "kg", "dairy"),
        ("Tomatoes",         0,  "not_available", "kg", "vegetables"),
        ("Onions",          35,  "available", "kg", "vegetables"),
        ("Potatoes",        50,  "available", "kg", "vegetables"),
        ("Eggs",            10,  "low",       "dozen", "poultry"),
        ("Chicken",          0,  "not_available", "kg", "meat"),
        ("Paper Plates",    200, "available", "pcs", "supplies"),
        ("Detergent",        8,  "available", "kg", "cleaning"),
    ]
    for name, qty, status, unit, cat in _demo:
        db.upsert_item(name, qty, status, unit, cat)
        db.log_event("seed", name, detail=f"Demo data loaded: {qty}{unit}")

    # Seed some demo requests
    _reqs = [
        ("Chicken", 1, 10, "pending"),
        ("Tomatoes", 1, 5, "ordered"),
        ("Milk (Packets)", 1, 30, "received"),
    ]
    for item, uid, qty, st in _reqs:
        rid = db.create_request(item, uid, qty)
        db.update_request_status(rid, st)

    print("\n🚀  Inventory Bot API running at http://localhost:5050")
    print("📊  Dashboard:  http://localhost:5050/")
    print("🔑  API Secret:", API_SECRET)
    print("📝  Docs: GET /api/inventory, GET /api/events, POST /api/update\n")
    app.run(host="0.0.0.0", port=5050, debug=False)
