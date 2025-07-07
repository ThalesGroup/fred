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

from abc import ABC, abstractmethod

from fred.services.theorical_radio.theorical_radio_structures import TheoricalRadioSeries

class AbstractTheoricalRadioService(ABC):
    """
    Interface to retrieve information on theorical radio data.
    One implementations is provided that uses real data
    stored in some file backends.
    """

    @abstractmethod
    def radio_data(self) \
            -> TheoricalRadioSeries:
        """
        Retrieves a list of radio data.

        Returns:
            TheoricalRadioSeries: The object containing the radio data.
        """
        ...