"""alerts — in-app alerts triggered by operational events.

This module is driven by the event bus, not by sibling service calls. It exposes reads over HTTP
and creates notifications only in response to published domain events, which is why it has no
write route: there is no HTTP path by which another module could ask it to create an alert.
"""
