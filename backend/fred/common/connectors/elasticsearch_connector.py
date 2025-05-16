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
from datetime import datetime
import logging
from typing import Type, TypeVar

from elasticsearch import Elasticsearch as Els

from common.structure import HttpSchemeEnum
from common.connectors.connector import Connector

# 🔹 Create a module-level logger
logger = logging.getLogger(__name__)

class ElasticSearch(Connector):
    """
    ElasticSearch Connector class
    """
    connection = None
    T = TypeVar('T')

    def __init__(self, scheme: HttpSchemeEnum, host: str, port: str, basic_auth, headers):
        try:
            if basic_auth:
                self.__connection = Els(
                    [f'{scheme}://{basic_auth[0]}:{basic_auth[1]}@{host}:{port}'],
                    headers=headers
                )
            else:
                self.__connection = Els([
                    f'http://{host}:{port}'
                ], headers=headers)
            # print(self.__connection.info)
        except Exception as e:
            logger.error("Error while create ElasticSearch connector", str(e))

    def find(self, target: str, start_time: datetime = None, end_time: datetime = None,
             class_to_cast: Type[T] = None,
             **kwargs) -> list[T] | list[dict]:

        time_attribute_name = kwargs.pop("time_attribute_name", None)

        if start_time and end_time:
            if not time_attribute_name:
                time_attribute_name = "@timestamp"
                logger.warning("No time attribute name set, default time attribute key set to @timestamp")
            query = {
                "query": {
                    "range": {
                        time_attribute_name: {
                            "gte": start_time.isoformat(),
                            "lte": end_time.isoformat()
                        }
                    }
                },
                "sort": [
                    {time_attribute_name: {"order": "asc"}}
                ]
            }
        else:
            query = {
                "query": {
                    "match_all": {}
                }
            }
        documents = self.search_elements(index_name=target, query=query, **kwargs)

        if class_to_cast:
            try:
                return [class_to_cast(**document.get("_source")) for document in documents]
            except Exception as e:
                logger.error(f"Error while casting document to {class_to_cast}: {str(e)}")
        else:
            return documents

    def search_elements(self, index_name=None, query=None, scroll=None, size=100, **kwargs) -> list[dict]:
        if not scroll:
            res = []
            # Initial search request with scroll
            response = self.__connection.search(index=index_name, body=query, size=size, **kwargs)
            documents = response['hits']['hits']
            res.extend(documents)
            return res
        else:
            res = []
            # Initial search request with scroll
            response = self.__connection.search(index=index_name, body=query, scroll=scroll, size=size, **kwargs)
            if not '_scroll_id' in response: return []
            scroll_id = response['_scroll_id']
            documents = response['hits']['hits']
            res.extend(documents)
            # Next requests based on scroll_id
            while documents:
                response = self.__connection.scroll(scroll_id=scroll_id, scroll=scroll)
                scroll_id = response['_scroll_id']
                documents = response['hits']['hits']
                res.extend(documents)
            return res

    def list_collections(self, **kwargs) -> list[str]:
        return self.__connection.indices.get_alias(**kwargs).keys()
