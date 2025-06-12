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
Services to extract and analyze information on the mission
"""
import csv
import logging
import os
import pathlib
import sys
import pandas as pd

from fred.application_context import get_configuration
from fred.services.mission.mission_structures import Mission, MissionSeries

logger = logging.getLogger(__name__)

class MissionCsvService:
    """
    A service for providing information on a ongoing mission.
    It reads data from a CSV file, which contains information about the mission, active ships,
    protocols used for communication etc.
    """

    def __init__(self):
        configuration = get_configuration()
        if hasattr(sys.modules['__main__'], '__file__'):
            main_path_dir = pathlib.Path(os.path.abspath(sys.modules['__main__'].__file__)).parent
        else:
            raise RuntimeError("This code must be run as part of a main script with a file path.")

        self.mission_data_file = main_path_dir / configuration.database.csv_files.mission
    
    def get_mission(self) -> MissionSeries:
        df = pd.read_csv(self.mission_data_file, sep=";")
        details=[]
        for index, row in df.iterrows():
            details.append(Mission(ship=row["navire"],
                                   active=row["actif"],
                                   protocol=row["modulation"]))
        
        return MissionSeries(details=details)
