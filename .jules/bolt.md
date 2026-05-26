
## 2023-10-24 - Database queries optimization
**Learning:** Found multiple separate SELECT COUNT queries to fetch dashboard statistics which can be batched together. The vanilla JS frontend polls this endpoint every 15 seconds.
**Action:** Replace 7 single queries in get_stats with 2 aggregate queries using SUM with CASE statements.
