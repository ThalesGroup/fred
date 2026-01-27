from pydantic import BaseModel, Field


class GroupSummary(BaseModel):
    id: str
    name: str
    member_count: int | None = None
    total_member_count: int | None = None
    sub_groups: list["GroupSummary"] = Field(default_factory=list)


GroupSummary.model_rebuild()
