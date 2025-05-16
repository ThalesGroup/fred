
import logging
from pathlib import Path

logger = logging.getLogger(__name__)
class AttachementProcessing:
    """
    A singleton class to manage multiple Session instances.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    def __init__(self):
        logger.info("[ℹ️ AttachementProcessing] Initializing AttachementProcessing")

    def process_attachment(self, attachment: Path):
        """
        Process the attachment and return the result.
        """
        logger.info(f"[ℹ️ AttachementProcessing] Processing attachment: {attachment}")