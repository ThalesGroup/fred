from __future__ import annotations

from enum import Enum


class PromptCategory(str, Enum):
    """Functional category for one prompt-library record.

    Why this enum exists:
    - prompts are classified by what they *do* (functional axis), not by who
      uses them or their technical nature — those belong to free-form tags
    - a single mutually-exclusive category drives the icon and filter chip in
      the UI; free-form tags handle cross-cutting concerns (domain, technique)
    - defining it here keeps the backend the authoritative source; the OpenAPI
      spec propagates the valid values to the frontend automatically

    How to use it:
    - reference `PromptCategory` in Pydantic request / response models
    - store the `.value` string in the DB column (VARCHAR)
    - add new values here when the functional taxonomy grows; the frontend
      catalog (`promptCategories.ts`) must be updated in the same change
    """

    DOC_ASSIST = "doc-assist"
    SUMMARY = "summary"
    EXTRACTION = "extraction"
    WRITING = "writing"
    ANALYSIS = "analysis"
    MONITORING = "monitoring"
    MIGRATION = "migration"
    CONVERSATIONAL = "conversational"
    INTEGRATION = "integration"
    OTHER = "other"
