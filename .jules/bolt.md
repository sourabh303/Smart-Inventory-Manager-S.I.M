## 2026-05-10 - Combine aggregate queries to reduce roundtrips
**Learning:** Running multiple `COUNT(...)` queries sequentially on the same table causes unnecessary database roundtrips and latency overhead.
**Action:** Use conditional aggregation (`SUM(CASE WHEN ... THEN 1 ELSE 0 END)`) to compute all statistics in a single query when analyzing the same table.
