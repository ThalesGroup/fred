from typing import NewType

# TeamId is a distinct type from str for static type checking.
TeamId = NewType("TeamId", str)
