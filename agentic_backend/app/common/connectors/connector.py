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
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Type, TypeVar

"""
Abstract Connector class. It defines the interface for connectors
used to fetch data from different data sources. As of today 
the only supported connector is the local filesystem connector
"""


class Connector(ABC):
    __connection = None
    T = TypeVar('T')

    @abstractmethod
    def find(self, target: str, start_time: datetime = None, end_time: datetime = None, class_to_cast: Type[T] = None,
             **kwargs) -> list[T] | list[dict]:
        pass

    @abstractmethod
    def list_collections(self, **kwargs) -> list[str]:
        pass
