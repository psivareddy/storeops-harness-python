"""reports — store and regional performance summaries.

**Read-only module.** It aggregates across activities, programmes and staff and never writes to
them. Its own repository exposes no mutating operation, it publishes no events, and it has no
write route: three independent reasons a write cannot originate here.
"""
