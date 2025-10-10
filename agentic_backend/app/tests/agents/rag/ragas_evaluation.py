
import logging
import sys

def setup_colored_logging():
    """
    Set up colored logging for console output.
    The logging output includes timestamp, log level, and message.
    """
    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }

    class ColorFormatter(logging.Formatter):
        def format(self, record):
            color = COLORS.get(record.levelname, "\033[0m")
            record.levelname = f"{color}{record.levelname}\033[0m"
            return super().format(record)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        ColorFormatter("%(asctime)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    )

    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)