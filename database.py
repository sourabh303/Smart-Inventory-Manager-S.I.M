# === NEW: Create order and order items ===
def create_order(chat_id, message_id, created_by, items, timestamp=None):
    """
    Create a new order and associated order_items.
    items: list of dicts with keys: name, size, quantity, unit
    Returns order_id.
    """
    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO orders (chat_id, message_id, created_by, created_at, status)
            VALUES (?, ?, ?, ?, 'PENDING')
            """,
            (chat_id, message_id, created_by, timestamp or datetime.utcnow().isoformat())
        )
        order_id = cur.lastrowid
        for item in items:
            conn.execute(
                """
                INSERT INTO order_items (order_id, name, size, quantity, unit, status)
                VALUES (?, ?, ?, ?, ?, 'PENDING')
                """,
                (order_id, item.get('name'), item.get('size'), item.get('quantity'), item.get('unit'))
            )
        return order_id

# === NEW: Add message mapping ===
def add_message_mapping(message_id, mapped_order_id, confidence_score):
    with get_db() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO message_mapping (message_id, mapped_order_id, confidence_score)
            VALUES (?, ?, ?)
            """,
            (message_id, mapped_order_id, confidence_score)
        )

# === NEW: Get order by message_id ===
def get_order_by_message_id(message_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM orders WHERE message_id = ?", (message_id,)
        ).fetchone()
        return dict(row) if row else None

# === NEW: Update order/item status ===
def update_order_status(order_id, status):
    with get_db() as conn:
        conn.execute(
            "UPDATE orders SET status = ? WHERE order_id = ?",
            (status, order_id)
        )

def update_order_item_status(item_id, status):
    with get_db() as conn:
        conn.execute(
            "UPDATE order_items SET status = ? WHERE item_id = ?",
            (status, item_id)
        )

# === NEW: Get order items by order_id ===
def get_order_items(order_id):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM order_items WHERE order_id = ?",
            (order_id,)
        ).fetchall()
        return [dict(r) for r in rows]
"""
database.py — SQLite schema and helper functions for the Inventory Bot
"""

import sqlite3
import json
from datetime import datetime
from contextlib import contextmanager

DB_PATH = "inventory.db"


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
            -- NEW: Orders table for structured order tracking
            CREATE TABLE IF NOT EXISTS orders (
                order_id    INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id     INTEGER NOT NULL,
                message_id  INTEGER NOT NULL,
                created_by  INTEGER NOT NULL,
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                status      TEXT NOT NULL DEFAULT 'PENDING'
            );

            -- NEW: Order items table for multi-item orders
            CREATE TABLE IF NOT EXISTS order_items (
                item_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id    INTEGER NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
                name        TEXT NOT NULL,
                size        TEXT,
                quantity    INTEGER,
                unit        TEXT,
                status      TEXT NOT NULL DEFAULT 'PENDING'
            );

            -- NEW: Message mapping table for reply/context mapping
            CREATE TABLE IF NOT EXISTS message_mapping (
                message_id      INTEGER PRIMARY KEY,
                mapped_order_id INTEGER,
                confidence_score REAL
            );
    # === NEW: Helper to get active orders for a chat ===
    def get_active_orders(chat_id, minutes=10):
            """
            Return recent orders in this chat within the last N minutes.
            """
            with get_db() as conn:
                    rows = conn.execute(
                            """
                            SELECT * FROM orders
                            WHERE chat_id = ?
                                AND datetime(created_at) >= datetime('now', ?)
                                AND status = 'PENDING'
                            ORDER BY created_at DESC
                            """,
                            (chat_id, f'-{minutes} minutes')
                    ).fetchall()
                    return [dict(r) for r in rows]
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS inventory (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name   TEXT NOT NULL UNIQUE COLLATE NOCASE,
                quantity    INTEGER NOT NULL DEFAULT 0,
                unit        TEXT DEFAULT 'units',
                status      TEXT NOT NULL DEFAULT 'available'
                                CHECK(status IN ('available','low','not_available','ordered')),
                category    TEXT DEFAULT 'general',
                updated_by  INTEGER,
                updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
                notes       TEXT
            );

            CREATE TABLE IF NOT EXISTS requests (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id         INTEGER REFERENCES inventory(id) ON DELETE SET NULL,
                item_name       TEXT NOT NULL,
                requested_by    INTEGER NOT NULL,
                requested_at    TEXT NOT NULL DEFAULT (datetime('now')),
                status          TEXT NOT NULL DEFAULT 'pending'
                                    CHECK(status IN ('pending','ordered','received','cancelled','done')),
                quantity        INTEGER DEFAULT 1,
                message_id      INTEGER,
                chat_id         INTEGER,
                notes           TEXT
            );

            CREATE TABLE IF NOT EXISTS event_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type  TEXT NOT NULL,
                item_name   TEXT,
                actor_id    INTEGER,
                actor_name  TEXT,
                detail      TEXT,
                raw_message TEXT,
                timestamp   TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                full_name   TEXT,
                role        TEXT NOT NULL DEFAULT 'staff'
                                CHECK(role IN ('incharge','staff','viewer')),
                added_at    TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)

    print("[DB] Database initialized.")


# ─── Inventory helpers ────────────────────────────────────────────────────────

def upsert_item(item_name: str, quantity: int = 0, status: str = "available",
                unit: str = "units", category: str = "general",
                actor_id: int = None, notes: str = None) -> dict:
    with get_db() as conn:
        conn.execute("""
            INSERT INTO inventory (item_name, quantity, status, unit, category, updated_by, updated_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?)
            ON CONFLICT(item_name) DO UPDATE SET
                quantity   = excluded.quantity,
                status     = excluded.status,
                unit       = excluded.unit,
                category   = excluded.category,
                updated_by = excluded.updated_by,
                updated_at = datetime('now'),
                notes      = excluded.notes
        """, (item_name, quantity, status, unit, category, actor_id, notes))
        row = conn.execute(
            "SELECT * FROM inventory WHERE item_name = ? COLLATE NOCASE", (item_name,)
        ).fetchone()
        return dict(row) if row else {}


from typing import Optional

def update_item_status(item_name: str, status: str, actor_id: int = None) -> Optional[dict]:
    with get_db() as conn:
        conn.execute("""
            UPDATE inventory
            SET status = ?, updated_by = ?, updated_at = datetime('now')
            WHERE item_name = ? COLLATE NOCASE
        """, (status, actor_id, item_name))
        row = conn.execute(
            "SELECT * FROM inventory WHERE item_name = ? COLLATE NOCASE", (item_name,)
        ).fetchone()
        return dict(row) if row else None


def get_all_inventory():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM inventory ORDER BY item_name"
        ).fetchall()
        return [dict(r) for r in rows]


def get_item(item_name: str):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM inventory WHERE item_name = ? COLLATE NOCASE", (item_name,)
        ).fetchone()
        return dict(row) if row else None


def get_low_stock():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM inventory WHERE status IN ('low','not_available') ORDER BY status"
        ).fetchall()
        return [dict(r) for r in rows]


# ─── Request helpers ──────────────────────────────────────────────────────────

def create_request(item_name: str, requested_by: int, quantity: int = 1,
                   message_id: int = None, chat_id: int = None, notes: str = None) -> int:
    item = get_item(item_name)
    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO requests (item_id, item_name, requested_by, quantity, message_id, chat_id, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (item["id"] if item else None, item_name, requested_by, quantity, message_id, chat_id, notes))
        return cur.lastrowid


def update_request_status(request_id: int, status: str) -> bool:
    with get_db() as conn:
        conn.execute(
            "UPDATE requests SET status = ? WHERE id = ?", (status, request_id)
        )
        return conn.execute(
            "SELECT changes()"
        ).fetchone()[0] > 0


def get_requests(status: str = None):
    with get_db() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM requests WHERE status = ? ORDER BY requested_at DESC", (status,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM requests ORDER BY requested_at DESC LIMIT 100"
            ).fetchall()
        return [dict(r) for r in rows]


# ─── Event log helpers ────────────────────────────────────────────────────────

def log_event(event_type: str, item_name: str = None, actor_id: int = None,
              actor_name: str = None, detail: str = None, raw_message: str = None):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO event_log (event_type, item_name, actor_id, actor_name, detail, raw_message)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (event_type, item_name, actor_id, actor_name, detail, raw_message))


def get_events(limit: int = 200):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM event_log ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# ─── User helpers ─────────────────────────────────────────────────────────────

def ensure_user(user_id: int, username: str = None, full_name: str = None):
    with get_db() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO users (user_id, username, full_name)
            VALUES (?, ?, ?)
        """, (user_id, username, full_name))


def get_user_role(user_id: int) -> str:
    with get_db() as conn:
        row = conn.execute(
            "SELECT role FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row["role"] if row else "staff"


def set_user_role(user_id: int, role: str) -> bool:
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET role = ? WHERE user_id = ?", (role, user_id)
        )
        return conn.execute("SELECT changes()").fetchone()[0] > 0


def get_stats():
    with get_db() as conn:
        total     = conn.execute("SELECT COUNT(*) FROM inventory").fetchone()[0]
        available = conn.execute("SELECT COUNT(*) FROM inventory WHERE status='available'").fetchone()[0]
        low       = conn.execute("SELECT COUNT(*) FROM inventory WHERE status='low'").fetchone()[0]
        out       = conn.execute("SELECT COUNT(*) FROM inventory WHERE status='not_available'").fetchone()[0]
        ordered   = conn.execute("SELECT COUNT(*) FROM inventory WHERE status='ordered'").fetchone()[0]
        pending_req = conn.execute(
            "SELECT COUNT(*) FROM requests WHERE status='pending'"
        ).fetchone()[0]
        ordered_req = conn.execute(
            "SELECT COUNT(*) FROM requests WHERE status='ordered'"
        ).fetchone()[0]
        return {
            "total_items":     total,
            "available":       available,
            "low_stock":       low,
            "out_of_stock":    out,
            "ordered":         ordered,
            "pending_requests": pending_req,
            "ordered_requests": ordered_req,
        }
