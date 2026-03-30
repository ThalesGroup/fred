"""Utility functions for PPT export formatting."""


def convert_maitrise_to_emoji(level: str | int) -> str:
    """Convert maitrise level (1-5) to emoji pattern (●○○○○ to ●●●●●).

    Args:
        level: Integer or string from 1 to 5, or empty string for no skill

    Returns:
        String with filled (●) and empty (○) circles, or empty string if no level
    """
    if isinstance(level, str):
        if not level.strip():
            return ""
        try:
            level = int(level)
        except ValueError:
            return ""
    if not 1 <= level <= 5:
        return ""
    filled = "●" * level
    empty = "○" * (5 - level)
    return filled + empty
