# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
class ManagerError(RuntimeError):
    def __init__(self, code: str, *, permanent: bool = False, reason: str | None = None):
        super().__init__(code)
        self.code = code
        self.permanent = permanent
        # Bounded diagnostic (exception type or HTTP status), never a body or token.
        self.reason = reason
