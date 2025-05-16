from fred.application_context import get_app_context, get_configuration
from services.sensor.sensor_abstract_service import AbstractSensorService, AbstractSensorConfigurationService
from services.sensor.sensor_csv_service import SensorCsvService, SensorConfigurationCsvService
from common.structure import DatabaseTypeEnum


class SensorService:
    def __new__(cls) -> AbstractSensorService:
        match get_configuration().database.type:
            case DatabaseTypeEnum.csv:
                return SensorCsvService()
            case _:
                raise NotImplementedError(f"Database type {get_configuration().database.type}")
            

class SensorConfigurationService:
    def __new__(cls) -> AbstractSensorConfigurationService:
        match get_configuration().database.type:
            case DatabaseTypeEnum.csv:
                return SensorConfigurationCsvService()
            case _:
                raise NotImplementedError(f"Database type {get_configuration().database.type}")