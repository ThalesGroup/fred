from pydantic import BaseModel, Field

from knowledge_flow_backend.features.users.users_structures import UserSummary


class GroupSummary(BaseModel):
    id: str
    name: str
    description: str | None = None
    banner_image_url: str | None = None
    owners: list[UserSummary] = Field(default_factory=list)
    member_count: int | None = None
    is_private: bool = False
    # todo: remove sub groups
    total_member_count: int | None = None
    sub_groups: list["GroupSummary"] = Field(default_factory=list)


GroupSummary.model_rebuild()
