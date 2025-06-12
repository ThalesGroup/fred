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
Services to extract theorical radio data
"""
import logging
import os
import pathlib
import sys
import pandas as pd

from fred.services.theorical_radio.theorical_radio_structures import RadioData, TheoricalRadioSeries
from fred.common.utils import format_to_en
from fred.application_context import get_configuration

logger = logging.getLogger(__name__)

class TheoricalRadioCsvService:
    """
    A service for providing information on theorical radio data.
    It reads data from a CSV file, which contains information about radio: description,
    signal type, frequency, location, bandwidth, freq min/max.
    """

    def __init__(self):
        configuration = get_configuration()
        if hasattr(sys.modules['__main__'], '__file__'):
            main_path_dir = pathlib.Path(os.path.abspath(sys.modules['__main__'].__file__)).parent
        else:
            raise RuntimeError("This code must be run as part of a main script with a file path.")

        self.sigwiki_data_file = main_path_dir / configuration.database.csv_files.signal_identification_guide
    
    def get_radio_data(self) -> TheoricalRadioSeries:
        df = pd.read_csv(self.sigwiki_data_file, sep=";")
        str_cols = ["Signal type", "Description", "Frequency", "Mode", "Modulation", "Bandwidth", "Location"]
        float_cols = ["fréq min", "fréq max"]
        df[str_cols] = df[str_cols].fillna("")
        df[float_cols] = df[float_cols].fillna(0.0)
        details=[]
        for index, row in df.iterrows():
            details.append(RadioData(type=row["Signal type"],
                                   description=row["Description"],
                                   frequency=row["Frequency"],
                                   mode=row["Mode"],
                                   modulation=row["Modulation"],
                                   bandwidth=row["Bandwidth"],
                                   location=row["Location"],
                                   min_freq=format_to_en(row["fréq min"]),
                                   max_freq=format_to_en(row["fréq max"])))
        
        return TheoricalRadioSeries(details=details)
