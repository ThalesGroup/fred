from pydantic import BaseModel, Field


class TeamSummary(BaseModel):
    id: str
    name: str
    member_count: int | None = None
    total_member_count: int | None = None
    sub_teams: list["TeamSummary"] = Field(default_factory=list)


TeamSummary.model_rebuild()
