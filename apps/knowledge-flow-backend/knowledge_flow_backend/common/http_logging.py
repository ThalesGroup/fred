# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Compatibility import for the shared request completion middleware."""

from fred_core.logs.http import RequestLoggingMiddleware as RequestResponseLogger

__all__ = ["RequestResponseLogger"]
