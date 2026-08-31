"""StoreOps — retail store operations management REST API.

Five business modules (activities, programmes, staff, alerts, reports), each following a
strict Routes -> Service -> Repository layering, plus ``app.shared`` which holds technical
infrastructure only and must never become a sixth business module.
"""
