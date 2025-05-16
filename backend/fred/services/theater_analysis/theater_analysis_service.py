from fred.application_context import get_configuration
from services.theater_analysis.theater_analysis_abstract_service import AbstractTheaterAnalysisService
from services.theater_analysis.theater_analysis_csv_service import TheaterAnalysisCsvService
from common.structure import DatabaseTypeEnum

class TheaterAnalysisService:
    def __new__(cls) -> AbstractTheaterAnalysisService:
        match get_configuration().database.type:
            case DatabaseTypeEnum.csv:
                return TheaterAnalysisCsvService()
            case _:
                raise NotImplementedError(f"Database type {get_configuration().database.type}")
            
