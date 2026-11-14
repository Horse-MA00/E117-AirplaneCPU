"""Shared HTTP-facing error types.

NotFound subclasses ValueError so existing callers and tests that expect a
ValueError keep working, while the HTTP layer can still answer 404 instead of
400. Unexpected KeyError/IndexError bugs are no longer disguised as 404s.
"""


class NotFound(ValueError):
    """A requested route or resource does not exist."""
