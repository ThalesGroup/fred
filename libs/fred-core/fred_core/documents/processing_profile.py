# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
from enum import StrEnum


class IngestionProcessingProfile(StrEnum):
    fast = "fast"
    medium = "medium"
    rich = "rich"
