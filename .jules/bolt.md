## 2025-02-28 - [Performance Insight: get_stats()]
**Learning:** The frontend polls `get_stats()` every 15 seconds! The current `get_stats()` executes 7 separate `COUNT(*)` queries on the inventory and requests tables. Since it is polled frequently, this is a prime candidate for database optimization. It can be collapsed into single queries using conditional aggregation (e.g. `SUM(CASE WHEN status='available' THEN 1 ELSE 0 END)`).
**Action:** Optimize `get_stats` by reducing the number of SQL queries and write these learnings to this journal before proposing PR.
