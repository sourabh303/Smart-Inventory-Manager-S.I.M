# 📦 StockWatch — Chat-Driven Inventory System

> Telegram group chat → Bot → Flask backend → SQLite → Web dashboard

---

## System Architecture

```
Telegram Group Chat
        │
        ▼
  python-telegram-bot (bot.py)
        │  parse messages & commands
        ▼
    parser.py (NLP-light intent extraction)
        │
        ▼
   database.py (SQLite via get_db())
        │
        ▼
   Flask REST API (app.py)
        │
        ▼
   index.html dashboard (Vanilla JS, auto-polls every 15s)
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install flask flask-cors python-telegram-bot
```

### 2. Create your Telegram bot

1. Open Telegram → message **@BotFather**
2. Send `/newbot`, follow prompts, copy the **token**
3. Add your bot to a group and give it **admin / read message** permission
4. Get your **Telegram user ID**: message **@userinfobot**

### 3. Configure environment

```bash
cp .env.template .env
nano .env            # Fill in TELEGRAM_TOKEN, INCHARGE_IDS, etc.
source .env
```

### 4. Run the Flask API + Dashboard

```bash
python app.py
```

Dashboard opens at **http://localhost:5050**

### 5. Run the Telegram bot (in a separate terminal)

```bash
source .env
python bot.py
```

---

## Telegram Commands

| Command | Who | What |
|---------|-----|-------|
| `/start` | Anyone | Show help |
| `/stock` | Anyone | List all inventory |
| `/low` | Anyone | List low/out-of-stock items |
| `/status` | Anyone | System stats |
| `/add <item> [qty] [unit]` | Anyone | Add a new item |
| `/update <item> <status>` | **Incharge only** | Update item status |

## Natural Language Chat (Free-form messages)

Staff can just chat normally:

```
"Rice is finished"           → marks Rice as not_available, creates request
"Cooking oil running low"    → marks low, creates request
"Milk packets ordered"       → marks as ordered (incharge only)
"received"  (reply to msg)  → marks item as received/available
"done"      (reply to msg)  → marks request as done
"cancel"    (reply to msg)  → cancels a pending request
```

Supported informal phrases (Hindi/Urdu too):
- `khatam`, `khatam ho gaya` → not_available
- `kam hai` → low stock
- `aa gaya` → received
- `ho gaya` → done
- `order diya` → ordered

---

## REST API Reference

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `GET /api/stats` | GET | — | Dashboard statistics |
| `GET /api/inventory` | GET | — | All inventory items |
| `GET /api/inventory/low` | GET | — | Low/out-of-stock items |
| `GET /api/requests` | GET | — | All requests (filter: `?status=pending`) |
| `GET /api/events` | GET | — | Activity log (filter: `?limit=50`) |
| `POST /api/inventory` | POST | API key | Add/update an item |
| `POST /api/update` | POST | API key | Update item status |
| `PATCH /api/requests/<id>` | PATCH | API key | Update request status |

**Authenticated endpoints** require header: `X-API-Key: <API_SECRET>`


### Example: Update item via curl

```bash
curl -X POST http://localhost:5050/api/update \
   -H "Content-Type: application/json" \
   -H "X-API-Key: <your_api_secret>" \
   -d '{"item_name": "Rice", "status": "available"}'
```

### Example: Add item via curl

```bash
curl -X POST http://localhost:5050/api/inventory \
   -H "Content-Type: application/json" \
   -H "X-API-Key: <your_api_secret>" \
   -d '{"item_name": "Sugar", "quantity": 10, "unit": "kg"}'
```

### Example: Update request status via curl

```bash
curl -X PATCH http://localhost:5050/api/requests/1 \
   -H "Content-Type: application/json" \
   -H "X-API-Key: <your_api_secret>" \
   -d '{"status": "done"}'
```

---

## Running Tests

To run the included unit tests:

```bash
pip install -r requirements.txt
python -m pip install python-dotenv
python test_app.py
```

Tests require a valid `.env` file with at least:

```
API_SECRET=testsecret
TELEGRAM_TOKEN=dummy
INCHARGE_IDS=1
```

---

## Authorization

- Set `INCHARGE_IDS` in `.env` to a comma-separated list of Telegram user IDs
- Only those users can run `/update` and write-commands in chat
- If `INCHARGE_IDS` is blank, **all users** can update (testing mode)
- Dashboard write operations (POST/PATCH) require the `API_SECRET` header

---


## Dashboard Features

- **Auto-refreshes every 15 seconds**
- **Dashboard**: Stats, alert banner, inventory snapshot, activity feed
- **Inventory**: Full table with search + filter by status
- **Requests**: Pending / Ordered / Received / Cancelled tabs
- **Activity Log**: Full audit trail with timestamps

**Note:** The dashboard will display a user-friendly error message if the API is unreachable or returns an error.

---

## Supported Status Values

| Status | Meaning |
|--------|---------|
| `available` | Item is in stock |
| `low` | Stock is low, needs reorder |
| `not_available` | Out of stock |
| `ordered` | Order placed, awaiting delivery |

---


## Docker Support

Build and run the app with Docker:

```bash
docker build -t stockwatch .
docker run -p 5050:5050 --env-file .env stockwatch
```

## Production Deployment

For production, use a webhook instead of polling:

1. Get an HTTPS URL (e.g. via nginx + Let's Encrypt, or Railway/Render)
2. Set the webhook:
   ```
   https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://yourdomain.com/webhook/<TOKEN>
   ```
3. Run Flask behind gunicorn:
   ```bash
   gunicorn app:app -w 2 -b 0.0.0.0:5050
   ```

---

## File Structure

```
inventory_bot/
├── app.py          Flask API server + static file serving
├── bot.py          Telegram bot (polling or webhook mode)
├── parser.py       NLP-light message intent extractor
├── database.py     SQLite helpers (inventory, requests, events, users)
├── templates/
│   └── index.html  Web dashboard (pure HTML/CSS/JS)
├── requirements.txt
├── .env.template   Environment variable template
└── README.md
```
