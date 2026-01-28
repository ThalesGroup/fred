from pydantic import BaseModel, Field

from knowledge_flow_backend.features.users.users_structures import UserSummary


class GroupProfile(BaseModel):
    id: str
    # banner_image_url: str | None = None
    banner_image_url: str | None = "https://www.bio.org/act-root/bio/assets/images/banner-default.png"
    is_private: bool | None = None
    description: str | None = None


class GroupProfileUpdate(BaseModel):
    banner_image_url: str | None = None
    is_private: bool | None = None
    description: str | None = None


class GroupSummary(BaseModel):
    id: str
    name: str
    description: str | None = None
    # banner_image_url: str | None = None
    banner_image_url: str | None = "https://www.bio.org/act-root/bio/assets/images/banner-default.png"
    owners: list[UserSummary] = Field(default_factory=list)
    member_count: int | None = None
    is_private: bool = False
    is_member: bool | None = None
