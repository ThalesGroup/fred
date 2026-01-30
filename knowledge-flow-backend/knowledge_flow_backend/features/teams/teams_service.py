from fred_core import KeycloakUser

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.teams.teams_structures import Team


async def list_teams(user: KeycloakUser) -> list[Team]:
    rebac = ApplicationContext.get_instance().get_rebac_engine()

    return []
