"""Shared technical infrastructure: error contract, event bus, audit sink, config, logging.

This package must not import any business module (activities, programmes, staff, alerts,
reports). The ``shared-is-infrastructure-only`` contract in ``.importlinter`` enforces it: if
``app.shared`` starts depending on a domain, the dependency direction inverts and the event bus
begins to know about the modules it exists to decouple.
"""
