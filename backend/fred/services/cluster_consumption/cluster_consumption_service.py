from fred.application_context import get_app_context, get_configuration
from services.cluster_consumption.cluster_consumption_abstract_service import AbstractClusterConsumptionService
from services.cluster_consumption.cluster_consumption_csv_service import ClusterConsumptionCsvService
from common.structure import Configuration, DatabaseTypeEnum


class ClusterConsumptionService:
    def __new__(cls) -> AbstractClusterConsumptionService:
        match get_configuration().database.type:
            case DatabaseTypeEnum.csv:
                return ClusterConsumptionCsvService()
            case _:
                raise NotImplementedError(f"Database type {get_configuration().database.type} is not supported.")
