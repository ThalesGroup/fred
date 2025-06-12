# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
Services to extract and transform the power kepler metrics data
"""
import logging
import os
import pathlib
import sys
import pandas as pd

from fred.application_context import get_configuration
from services.sensor.sensor_structures import SensorSeries, FreqBand
from services.sensor.sensor_structures import SensorConfigurationSeries, SensorConfiguration
from common.utils import format_to_en

logger = logging.getLogger(__name__)

class SensorCsvService:
    """
    A service for providing a frequency sweep.
    It reads data from a CSV file, which contains information about frequency bands.
    """

    def __init__(self):
        configuration = get_configuration()
        if hasattr(sys.modules['__main__'], '__file__'):
            main_path_dir = pathlib.Path(os.path.abspath(sys.modules['__main__'].__file__)).parent
        else:
            raise RuntimeError("This code must be run as part of a main script with a file path.")

        self.freq_data_file = main_path_dir / configuration.database.csv_files.frequencies

    def sweep(self) -> SensorSeries:
        band1 = FreqBand(lower_freq=40, upper_freq=80)
        band2 = FreqBand(lower_freq=140, upper_freq=180)
        band3 = FreqBand(lower_freq=360, upper_freq=400)
        details=[band1, band2, band3]
        return SensorSeries(details=details)

class SensorConfigurationCsvService:
    """
    A service for providing sensor configurations based on given maritime neighbourhood.
    It reads data from a CSV file, which contains information about the usage of specific frequencies.
    It filters the file for active military ships that emit from a specified maritime neighbourhood.
    """

    def __init__(self):
        configuration  = get_configuration()
        if hasattr(sys.modules['__main__'], '__file__'):
            main_path_dir = pathlib.Path(os.path.abspath(sys.modules['__main__'].__file__)).parent
        else:
            raise RuntimeError("This code must be run as part of a main script with a file path.")

        self.radio_data_file = main_path_dir / configuration.database.csv_files.radio

    def get_sensor_configurations(self, neighbourhood_id: str) -> SensorConfigurationSeries:
        return self._process_csv(self.radio_data_file, neighbourhood_id)

    @staticmethod
    def _process_csv(file_path: pathlib.Path, neighbourhood_id: str) -> SensorConfigurationSeries:
        """
        Process the CSV file and return a list of SensorConfigurationSeries objects.
        """
        details=[]
        df = pd.read_csv(file_path, sep=";")
        filtered_df = df.query(f"quartier_maritime == '{neighbourhood_id}' and licence_active == 'ACTIVE' and type_navire == 'MILITAIRE'")[["Fréquence (MHz)",  "Bandwidth (kHz)", "Protocole"]]
        
        for index, row in filtered_df.iterrows():
            details.append(SensorConfiguration(frequency=format_to_en(row["Fréquence (MHz)"]),
                                               bandwidth=format_to_en(row["Bandwidth (kHz)"]),
                                               protocol=row["Protocole"]))

        return SensorConfigurationSeries(details=details)
