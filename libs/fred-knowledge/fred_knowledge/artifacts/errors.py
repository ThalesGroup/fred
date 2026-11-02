# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
class ManagerError(RuntimeError):
    def __init__(self, code: str, *, permanent: bool = False):
        super().__init__(code)
        self.code = code
        self.permanent = permanent
