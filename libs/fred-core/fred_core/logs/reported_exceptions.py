# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0

"""Prevent a server from repeating a request-boundary exception diagnostic."""

import logging

_REPORTED = object()
_ATTRIBUTE = "_fred_already_logged"


def mark_reported(exc: BaseException) -> None:
    # Use the exception's own metadata, including on frozen exception subclasses.
    exc.__dict__[_ATTRIBUTE] = _REPORTED


def was_reported(exc: BaseException | None) -> bool:
    return exc is not None and exc.__dict__.get(_ATTRIBUTE) is _REPORTED


class AlreadyReportedExceptionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not (record.exc_info and was_reported(record.exc_info[1]))
