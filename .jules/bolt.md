## 2024-05-24 - Database Optimization in get_stats()
**Learning:** The `/api/stats` endpoint relies heavily on the `get_stats()` database function, making seven separate `COUNT` queries which leads to unnecessary DB round-trips. This logic was run locally via frequent polling, which is problematic for performance.
**Action:** Used conditional aggregation (`SUM` with `CASE WHEN`) to consolidate queries down to just two, optimizing SQLite query performance effectively. Next time, always check for N+1 queries or repetitive counting queries in heavily polled endpoints.
