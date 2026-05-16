## 2024-05-18 - [Optimize `get_stats` query in SQLite using conditional aggregation]
 **Learning:** Using `COUNT(*)` multiple times on the same table for different conditions causes multiple full table scans and separate database queries.
 **Action:** Instead of multiple `COUNT(*)` with `WHERE` clauses, combine them into a single query using conditional aggregation (e.g., `COUNT(CASE WHEN condition THEN 1 END)`). This reduces the number of database trips and scans the table only once, leading to significant performance improvement, especially for frequently accessed dashboard stats.
