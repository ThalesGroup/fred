# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import uuid
from fastapi import HTTPException


def raise_internal_error(logger: logging.Logger, msg: str, exc: Exception):
    """
    Raise a FastAPI HTTPException (500) while logging the full exception with a unique error ID.

    This function should be used whenever an unexpected server-side error occurs that:
    - Cannot be recovered from at runtime
    - Should be logged with full context (traceback)
    - Needs to be exposed to the user in a safe, non-leaky way

    What it does:
    - Logs the exception using `logger.exception(...)` (includes full traceback)
    - Attaches a unique error ID to the log for traceability
    - Raises an HTTPException(500) with a user-friendly message including the error ID

    Example use:

        try:
            result = do_critical_work()
        except Exception as e:
            raise_internal_error(logger, "Failed to complete ingestion step", e)

    The user will receive:
        HTTP 500 with: "Failed to complete ingestion step. Contact support with error ID: ab12cd34"

    The log will contain:
        [ab12cd34] Failed to complete ingestion step
        Traceback (most recent call last):
        ...

    Args:
        logger (logging.Logger): The logger instance to write the exception to.
        msg (str): A short, user-appropriate description of what failed.
        exc (Exception): The actual exception that was raised.
    """

    error_id = str(uuid.uuid4())[:8]
    logger.exception(f"[{error_id}] {msg}")
    raise HTTPException(
        status_code=500,
        detail=f"{msg}. Contact support with error ID: {error_id}."
    )
