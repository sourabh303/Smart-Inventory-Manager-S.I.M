## 2026-05-17 - [Optimize Database Stats Aggregation]
**Learning:** Polling architecture (every 15s) constantly hits the `/api/stats` endpoint which made 7 distinct `COUNT(*)` queries to SQLite. This caused unnecessary overhead due to repeated full table scans or repeated index traversals.
**Action:** Use conditional aggregation (`SUM(status='available')`) to consolidate the counts into fewer queries (1 for inventory, 1 for requests) for efficiency when polled frequently.
