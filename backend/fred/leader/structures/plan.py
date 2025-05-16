from typing import List

from pydantic import BaseModel, Field


class Plan(BaseModel):
    """Series of steps to follow."""

    steps: List[str] = Field(
        description="Different steps to follow, MUST be in sorted order."
    )

    def __str__(self):
        """
        Return a string representation of the plan.
        """
        return "\n".join(f"{i+1}. {step}" for i, step in enumerate(self.steps))
