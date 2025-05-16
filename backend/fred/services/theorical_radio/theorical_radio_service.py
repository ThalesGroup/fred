from fred.application_context import get_configuration
from services.theorical_radio.theorical_radio_abstract_service import AbstractTheoricalRadioService
from services.theorical_radio.theorical_radio_csv_service import TheoricalRadioCsvService
from common.structure import DatabaseTypeEnum


class TheoricalRadioService:
    def __new__(cls) -> AbstractTheoricalRadioService:
        match get_configuration().database.type:
            case DatabaseTypeEnum.csv:
                return TheoricalRadioCsvService()
            case _:
                raise NotImplementedError(f"Database type {get_configuration().database.type}")
            
