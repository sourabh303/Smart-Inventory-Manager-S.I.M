## 2024-05-18 - [Optimize Multiple Count Queries]
**Learning:** In the `get_stats()` function in `database.py`, 7 separate `SELECT COUNT(*)` queries were being executed consecutively. This was particularly impactful because the Vanilla JS dashboard auto-polls the `/api/stats` endpoint every 15 seconds. Executing multiple separate count queries on the same table is a performance anti-pattern in SQLite when they can be batched.
**Action:** Use conditional aggregation (`SUM(CASE WHEN condition THEN 1 ELSE 0 END)`) to batch multiple counts on the same table into a single query.
