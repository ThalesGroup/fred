
from fred.application_context import get_configuration
from services.mission.mission_abstract_service import AbstractMissionService
from services.mission.mission_csv_service import MissionCsvService
from common.structure import DatabaseTypeEnum


class MissionService:
    def __new__(cls) -> AbstractMissionService:
        match get_configuration().database.type:
            case DatabaseTypeEnum.csv:
                return MissionCsvService()
            case _:
                raise NotImplementedError(f"Database type {get_configuration().database.type}")
            
