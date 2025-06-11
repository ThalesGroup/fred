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

"""
metric_store.py

This module defines the `MetricStore` class for in-memory storage, filtering, and persistence
of structured metric logs.
"""

import json
import logging

logger = logging.getLogger("MetricStore")
logger.setLevel(logging.INFO)

class MetricStore:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._data = []
            logger.info("Created new MetricStore instance.")
        return cls._instance

    def add_data(self, json_data: dict):
        if isinstance(json_data, dict):
            self._data.append(json_data)
            logger.info(f"Added data: {json_data}")
        else:
            logger.warning(f"Tried to add non-dict data: {json_data}")

    def all(self):
        count = len(self._data)
        logger.info(f"Accessed all stored metrics. Total count: {count}")
        return self._data
    
# Fonction pour accéder à l'instance
def get_metric_store():
    return MetricStore()
