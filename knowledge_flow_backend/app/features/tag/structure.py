from pydantic import BaseModel


class TagModel(BaseModel):
    id: str
    name: str
    description: str | None = None
    