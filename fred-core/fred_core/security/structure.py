from pydantic import BaseModel


class Security(BaseModel):
    enabled: bool
    keycloak_url: str
    client_id: str
    authorized_origins: list[str]
