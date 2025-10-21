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


import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class AttachementProcessing:
    """
    A singleton class to manage multiple Session instances.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        logger.info("[ℹ️ AttachementProcessing] Initializing AttachementProcessing")

    def process_attachment(self, attachment: Path):
        """
        Process the attachment and return the result.
        """
        logger.info(f"[ℹ️ AttachementProcessing] Processing attachment: {attachment}")
