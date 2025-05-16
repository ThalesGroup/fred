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
Select the right connector
"""

from typing import Mapping

from common.structure import DatabaseConfiguration, DatabaseTypeEnum
from common.connectors.elasticsearch_connector import ElasticSearch


def get_client(config: DatabaseConfiguration) -> ElasticSearch:
    if config.type.value == DatabaseTypeEnum.elasticsearch:
        headers: Mapping[str, str] = {'Content-Type': 'application/json'}
        return ElasticSearch(
            scheme=config.scheme,
            host=config.host,
            port=f"{config.port}",
            basic_auth=(config.username,
                        config.password)
            if config.username and config.password else None,
            headers=headers
        )
    else:
        raise NotImplementedError(
            f"No connector available for this configuration type: {config.type.value}")
