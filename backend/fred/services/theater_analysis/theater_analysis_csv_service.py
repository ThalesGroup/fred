#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Services to extract and transform data from theater of operation captured by a sensor
"""
from fred.application_context import get_configuration
import logging
import os
import pathlib
import sys
import pandas as pd

from services.theater_analysis.theater_analysis_structures import (
    TheaterAnalysisSeries,
    ShipSignalLocation
    )
from services.theater_analysis.theater_analysis_structures import (
    Mission, MissionSeries
    )
from services.theater_analysis.theater_analysis_structures import (
    DetectedData, DetectedDataSeries
    )

logger = logging.getLogger(__name__)

class TheaterAnalysisCsvService:
    """
    A service for providing a location from a radio protocol.
    It reads data from a CSV file, which contains information about the standards and lists of radio protocol usage worldwide.
    """

    def __init__(self):
        configuration = get_configuration()
        if hasattr(sys.modules['__main__'], '__file__'):
            main_path_dir = pathlib.Path(os.path.abspath(sys.modules['__main__'].__file__)).parent
        else:
            raise RuntimeError("This code must be run as part of a main script with a file path.")

        self.mission_data_file = main_path_dir / configuration.database.csv_files.mission
        self.sensors_data_file = main_path_dir / configuration.database.csv_files.sensors_test_new
        self.radio_data_file = main_path_dir / configuration.database.csv_files.radio

    def get_active_ships_from_mission_plan(self) -> pd.DataFrame:
        df = pd.read_csv(self.mission_data_file, sep=";")
        filtered_df = df[df["actif"] == 1]
        return filtered_df[["navire", "modulation"]]

    def add_data_to_active_ships(self) -> pd.DataFrame:
        radio_df = pd.read_csv(self.radio_data_file, sep=";")
        active_ships = self.get_active_ships_from_mission_plan()
        df = pd.merge(active_ships, radio_df, left_on='navire', right_on='indicatif_appel', how='left')
        return df[["navire", "Fréquence (MHz)", "Bandwidth (kHz)", "modulation"]]
    
    def active_military_ships_detected(self) -> pd.DataFrame:
        military_protocols = ["Link-11", "STANAG-4204"]        
        df = pd.read_csv(self.sensors_data_file, sep=";")
        filtered_df = df[df.protocole.isin(military_protocols)]

        return filtered_df[["Fc (MHz)", "Bw (kHz)", "protocole", "localisation"]]

    def get_theater_analysis(self) -> TheaterAnalysisSeries:
        return self._process_data(expected_active_ships=self.add_data_to_active_ships(),
                                  detected_active_ships=self.active_military_ships_detected())

    def get_active_ships(self) -> TheaterAnalysisSeries:
        details = []
        active_ships_detected = pd.read_csv(self.sensors_data_file, sep=";")
        for index, row in active_ships_detected.iterrows():
            details.append(ShipSignalLocation(frequency=to_en_float(row["Fc (MHz)"]),
                                                     bandwidth=to_en_float(row["Bw (kHz)"]),
                                                     protocol=row["protocole"],
                                                     location=row["localisation"]))
        return TheaterAnalysisSeries(details=details)

    @staticmethod
    def _process_data(expected_active_ships: pd.DataFrame, 
                    detected_active_ships: pd.DataFrame) -> TheaterAnalysisSeries:
        """
        Process the CSV file and return a TheaterAnalysisSeries object.
        """
        detected_active_ships['Bw (kHz)'] = detected_active_ships['Bw (kHz)'].astype(str)
        expected_active_ships['Bandwidth (kHz)'] = expected_active_ships['Bandwidth (kHz)'].astype(str)
        details=[]
        merged_df = detected_active_ships.merge(
            right=expected_active_ships,
            left_on=['Fc (MHz)', 'Bw (kHz)', 'protocole'],
            right_on=['Fréquence (MHz)', 'Bandwidth (kHz)', 'modulation'],
            how='left',
            indicator=True
        )

        unexpected_ships = merged_df[merged_df['_merge'] == 'left_only']
        unexpected_ships = unexpected_ships[['Fc (MHz)', 'Bw (kHz)', 'protocole', 'localisation']]
        
        for index, row in unexpected_ships.iterrows():
            details.append(ShipSignalLocation(frequency=to_en_float(row["Fc (MHz)"]),
                                                     bandwidth=to_en_float(row["Bw (kHz)"]),
                                                     protocol=row["protocole"],
                                                     location=row["localisation"]))
        return TheaterAnalysisSeries(details=details)


    #Get mission related information tool
    def get_mission(self) -> MissionSeries:
        df = pd.read_csv(self.mission_data_file, sep=";")
        details=[]
        for index, row in df.iterrows():
            details.append(Mission(ship=row["navire"],
                                   active=row["actif"],
                                   protocol=row["modulation"]))
        
        return MissionSeries(details=details)

    #Get sensor related data tool
    def get_sensor_data(self) -> DetectedDataSeries:
        df = pd.read_csv(self.sensors_data_file, sep=";")
        details=[]
        for index, row in df.iterrows():
            details.append(DetectedData(id=row["id"],
                                        type=row["type"],
                                        frequency=to_en_float(row["Fc (MHz)"]),
                                        bandwidth=row["Bw (kHz)"],
                                        level=row["niveau (dBm)"],
                                        azimuth=row["az (°)"],
                                        modulation=row["modulation"],
                                        protocol=row["protocole"],
                                        beginning_s=row["debut (s)"],
                                        duration_ms=row["duree (ms)"],
                                        location=row["localisation"]))
        
        return DetectedDataSeries(details=details)


def to_en_float(nb: str | int | float) -> float:
    return float(str(nb).replace(",", "."))

