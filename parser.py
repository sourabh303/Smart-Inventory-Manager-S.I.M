"""
parser.py — NLP-light message parser that extracts inventory intent from raw chat text.
Handles messy, informal language common in staff group chats.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

# ─── Strong commands (exact match, case-insensitive) ─────────────────────────
COMMANDS = {
    # Availability
    "available":      "available",
    "in stock":       "available",
    "instock":        "available",
    "back in stock":  "available",
    "back":           "available",

    # Unavailable
    "not available":  "not_available",
    "unavailable":    "not_available",
    "out of stock":   "not_available",
    "out":            "not_available",
    "empty":          "not_available",
    "finished":       "not_available",
    "khatam":         "not_available",     # Hindi/Urdu "finished"
    "khatam ho gaya": "not_available",

    # Low stock
    "low":            "low",
    "low stock":      "low",
    "almost out":     "low",
    "running low":    "low",
    "kam hai":        "low",              # Hindi "less/low"

    # Ordered
    "ordered":        "ordered",
    "order placed":   "ordered",
    "order diya":     "ordered",          # Hindi "order given"

    # Received
    "received":       "received",
    "aa gaya":        "received",         # Hindi "arrived"
    "delivered":      "received",
    "got it":         "received",

    # Done / completed
    "done":           "done",
    "completed":      "done",
    "complete":       "done",
    "ho gaya":        "done",             # Hindi "done"

    # Cancel
    "cancel":         "cancelled",
    "cancelled":      "cancelled",
    "ignore":         "cancelled",
}

# ─── Quantity extractors ──────────────────────────────────────────────────────
QTY_PATTERNS = [
    r"(\d+)\s*(kg|kgs|ltr|litre|litres|liter|liters|pcs|pieces|pkt|packet|packets|box|boxes|dozen|doz|bags|bag|units?)",
    r"(\d+)\s*(?:left|remaining|only|bache?)",   # "5 left", "3 bache"
    r"qty[:\s]*(\d+)",
    r"quantity[:\s]*(\d+)",
    r"x\s*(\d+)",
    r"(\d+)\s*x\b",
]

# ─── Item extraction ─────────────────────────────────────────────────────────
# Words to strip when detecting an item name from a free-form message
STOPWORDS = {
    "is", "are", "was", "been", "has", "have", "the", "a", "an",
    "and", "or", "not", "no", "yes", "ok", "okay", "please", "pls",
    "sir", "ma'am", "ji", "bhai", "bro", "check", "update", "mark",
    "please", "kindly", "note", "fyi", "hi", "hello", "hey",
}

ITEM_HINTS = re.compile(
    r"\b(stock|inventory|item|material|product|supply|supplies)\b", re.I
)


@dataclass
class ParseResult:
    intent: Optional[str] = None          # e.g. "available", "not_available", "ordered" …
    item_name: Optional[str] = None       # cleaned item name
    quantity: Optional[int] = None
    unit: Optional[str] = None
    raw_command: Optional[str] = None     # the matched command string
    confidence: float = 0.0
    tags: list = field(default_factory=list)


def _extract_quantity(text: str):
    """Return (quantity, unit) or (None, None)."""
    for pattern in QTY_PATTERNS:
        m = re.search(pattern, text, re.I)
        if m:
            qty = int(m.group(1))
            unit = m.group(2) if m.lastindex >= 2 else "units"
            return qty, unit.lower()
    # bare number fallback
    m = re.search(r"\b(\d{1,4})\b", text)
    if m:
        return int(m.group(1)), "units"
    return None, None


def _clean_item_name(text: str, command_str: str) -> Optional[str]:
    """Strip command words, stopwords, and punctuation to get item name."""
    # Remove the matched command phrase
    cleaned = re.sub(re.escape(command_str), "", text, flags=re.I).strip()

    # Remove quantity patterns
    for pattern in QTY_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.I)

    # Remove bare numbers
    cleaned = re.sub(r"\b\d+\b", "", cleaned)

    # Remove punctuation except hyphens (for item names like "PET-bottle")
    cleaned = re.sub(r"[^\w\s\-]", " ", cleaned)

    # Remove stopwords
    tokens = [w for w in cleaned.split() if w.lower() not in STOPWORDS and len(w) > 1]

    if not tokens:
        return None
    name = " ".join(tokens).strip()
    return name.title() if name else None


def parse_message(text: str) -> ParseResult:
    """
    Main parser. Returns a ParseResult describing intent and item.
    """
    if not text:
        return ParseResult()

    text_lower = text.lower().strip()
    result = ParseResult()

    # ── 1. Match a command ────────────────────────────────────────────────────
    matched_cmd = None
    matched_intent = None
    # Sort by length descending so multi-word phrases match first
    for phrase, intent in sorted(COMMANDS.items(), key=lambda x: -len(x[0])):
        if phrase in text_lower:
            matched_cmd = phrase
            matched_intent = intent
            break

    if not matched_cmd:
        return result  # No recognizable command

    result.intent = matched_intent
    result.raw_command = matched_cmd
    result.confidence = 0.9

    # ── 2. Extract quantity ───────────────────────────────────────────────────
    qty, unit = _extract_quantity(text_lower)
    result.quantity = qty
    result.unit = unit

    # ── 3. Extract item name ──────────────────────────────────────────────────
    item = _clean_item_name(text, matched_cmd)
    result.item_name = item

    # ── 4. Tag metadata ───────────────────────────────────────────────────────
    if qty:
        result.tags.append(f"qty:{qty}{unit}")
    if item:
        result.tags.append(f"item:{item}")

    return result


def parse_command_update(text: str):
    """
    Parse slash commands like /update <item> <status> [qty]
    Returns dict or None.
    """
    m = re.match(
        r"/update\s+(.+?)\s+(available|not_available|low|ordered|received|done|cancel)\s*(\d*)",
        text.strip(), re.I
    )
    if not m:
        return None
    return {
        "item_name": m.group(1).strip().title(),
        "status":    m.group(2).lower(),
        "quantity":  int(m.group(3)) if m.group(3) else None,
    }


def parse_add_item(text: str):
    """
    Parse /add <item name> [qty] [unit]
    """
    m = re.match(
        r"/add\s+(.+?)(?:\s+(\d+)\s*(\w+)?)?$",
        text.strip(), re.I
    )
    if not m:
        return None
    return {
        "item_name": m.group(1).strip().title(),
        "quantity":  int(m.group(2)) if m.group(2) else 0,
        "unit":      m.group(3).lower() if m.group(3) else "units",
    }
