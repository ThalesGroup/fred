"""
Authoring-first sample agents.

Purpose:
- provide copy/paste-ready starting points for new v2 agent developers
- stay out of the default product catalog unless explicitly adopted
"""

from .bank_transfer import BankTransferGraphAgent
from .slide_maker import Definition
from .tutorial_tools import TutorialToolsSampleDefinition

__all__ = ["BankTransferGraphAgent", "Definition", "TutorialToolsSampleDefinition"]
