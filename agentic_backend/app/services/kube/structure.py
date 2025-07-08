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
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""
Pydantic structure definitions to use in the kube microservice
"""
import re
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any

from croniter import croniter, CroniterBadCronError, CroniterBadDateError
from pydantic import BaseModel, ConfigDict, Field, model_validator, RootModel

from app.common.structure import WorkloadKind


class Cluster(BaseModel):
    sensor: Optional[str] = Field(None, description="The name of sensor used")
    fullname: Optional[str] = Field(None, description="The fullname he full name of the observed entity.")
    alias: Optional[str] = Field(None, description="The alias of the observed entity.")
    region: Optional[str] = Field(None, description="The region of the observed entity.")
    provider: Optional[str] = Field(None, description="The provider of the observed entity.")


class ClusterList(BaseModel):
    clusters_list: List[Cluster] = Field(default_factory=list, description="List of clusters")


class NamespacesList(BaseModel):
    cluster: str = Field(default_factory=str, description="The name of the cluster where the Namespaces reside")
    namespaces: List[str] = Field(default_factory=list, description="List of namespaces")


class Namespace(BaseModel):
    cluster: str = Field(default_factory=str, description="The name of the cluster where the Namespace resides")
    namespace: str = Field(default_factory=str, description="Namespace")
    labels: Optional[Dict[str, str]] = Field(default=None,
                                             description="The labels of the namespace associated to their value")
    annotations: Optional[Dict[str, str]] = Field(default=None,
                                                  description="The annotations of the namespace associated to their value")
    status: str = Field(default_factory=str, description="The status of the namespace")
    resource_quota: Optional[Dict[str, Dict[str, str]]] = Field(default=None,
                                                                description="The resource quota of the namespace associated to their value")
    limitrange_resource: Optional[Dict[str, Dict[str, str]]] = Field(default=None,
                                                                     description="The limit range resources of the namespace associated to their value")


class WorkloadNameList(BaseModel):
    cluster: str = Field(default_factory=str, description="The name of the cluster where the workloads reside")
    namespace: str = Field(default_factory=str, description="The namespace where the workloads are located")
    workloads: List[str] = Field(default_factory=list, description="List of workloads")
    kind: WorkloadKind = Field(description="The kind of workloads")


class Workload(BaseModel):
    cluster: str = Field(default_factory=str, description="The name of the cluster where the workload resides")
    namespace: str = Field(default_factory=str, description="The namespace where the workload is located")
    kind: WorkloadKind = Field(description="The kind of the workload")
    object: Dict[str, Any] = Field(default={}, description="The workload object")


class CustomObjectInfo(BaseModel):
    group: str = Field(default_factory=str, description="The group of the custom objects' definition")
    version: str = Field(default_factory=str, description="The version of the custom objects' definition")
    plural: str = Field(default_factory=str, description="The plural of the custom objects' definition")
    cluster: str = Field(default_factory=str, description="The name of the cluster where the custom objects reside")
    namespace: str = Field(default_factory=str, description="The namespace of the custom objects")


class CustomObject(CustomObjectInfo):
    name: str = Field(default_factory=str, description="The name of the custom object")
    body: Optional[Dict[str, Any]] = Field(default=None, description="The custom object body")


class ConfigMapsList(BaseModel):
    cluster: str = Field(default_factory=str, description="The name of the cluster where the resource resides")
    namespace: str = Field(default_factory=str, description="The namespace where the resource is located")
    resource_name: str = Field(default_factory=str,
                               description="The name of the resource associated with this overview")
    config_maps_list: List[Dict[str, Any]] = Field(default_factory=str,
                                                   description="The list of ConfigMaps associated with this resource")
    kind: WorkloadKind = Field(description="The kind of workloads")


class ServicesList(BaseModel):
    cluster: str = Field(default_factory=str, description="The name of the cluster where the resource resides")
    namespace: str = Field(default_factory=str, description="The namespace where the resource is located")
    resource_name: str = Field(default_factory=str,
                               description="The name of the resource associated with this overview")
    services_list: List[Dict[str, Any]] = Field(default_factory=str,
                                                description="The list of Services associated with this resource")
    kind: WorkloadKind = Field(description="The kind of workloads")


class IngressesList(BaseModel):
    cluster: str = Field(default_factory=str, description="The name of the cluster where the resource resides")
    namespace: str = Field(default_factory=str, description="The namespace where the resource is located")
    resource_name: str = Field(default_factory=str,
                               description="The name of the resource associated with this overview")
    ingresses_list: List[Dict[str, Any]] = Field(default_factory=str,
                                                 description="The list of Ingresses associated with this resource")
    kind: WorkloadKind = Field(description="The kind of workloads")


class RuleType(str, Enum):
    DATE = "date"
    DURATION = "duration"
    PROMETHEUS = "prometheus"


class Settings(RootModel[Dict[str, str]]):
    model_config = ConfigDict(
        json_schema_extra={
            "settings": {
                "value": "2023-08-05T13:45:30",
                "additional_key": "additional_value"
            }
        }
    )

    @model_validator(mode='after')
    def check_fields(self) -> "Settings":
        if 'value' not in self.root:
            raise ValueError("The key 'value' is required")
        return self

    def __iter__(self):
        return iter(self.root)

    def __getitem__(self, item):
        return self.root[item]


class Rule(BaseModel):
    type: RuleType = Field(description="The rule type.")
    settings: Settings = Field(description="The rule's settings. Must include the key 'value'.")

    @model_validator(mode='after')
    def check_value_based_on_rule_type(self):
        value = self.settings.root['value']

        if self.type == RuleType.DATE:
            try:
                datetime.fromisoformat(value)
            except ValueError:
                raise ValueError(f"For type 'date', 'value' must be a valid ISO date. Received: {value}")

        elif self.type == RuleType.PROMETHEUS:
            try:
                croniter(value)
            except (CroniterBadCronError, CroniterBadDateError):
                raise ValueError(f"For type 'cron', 'value' must be a valid cron expression. Received: {value}")

        elif self.type == RuleType.DURATION:
            if not re.match(r'^\d+[hms]$', value):
                raise ValueError(
                    f"For type 'duration', 'value' must be a valid duration (e.g., '3h', '2m', '5s'). Received: {value}")

        return self
