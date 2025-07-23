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
Pydantic structure definitions to use in the UI microservice. 
"""

from typing import List, Optional

from pydantic import BaseModel, Field

from app.features.frugal.structure.facts import Fact
from app.features.frugal.structure.workload_scores import WorkloadScores
from app.features.k8.structure import Cluster, WorkloadKind

class WorkloadDescription(BaseModel):
    """
    A resource is meant to describe a cluster workload. For example for Kubernetes a Deployment or StatefulSet.
    """
    name: str = Field(default_factory=str, description="The name of the workload")
    kind: WorkloadKind = Field(..., description="The kind of workload, either 'Deployment' or 'StatefulSet'")
    facts: List[Fact] = Field(default_factory=list, description="The facts about the workload components")

class NamespaceDescription(BaseModel):
    """
    A namespace is meant to describe a cluster namespace. It contains a list of resources.
    Of course for Kubernetes a namespace is a Kubernetes namespace. But it could be any other
    kind of namespace in other cluster types.
    """
    name: str = Field(default_factory=str, description="The name of the namespace")
    workloads: List[WorkloadDescription] = Field(default_factory=list, description="List of resources")
    facts: List[Fact] = Field(default_factory=list, description="The facts about the namespace components")

class WorkloadScore(BaseModel):
    name: str = Field(default_factory=str, description="The name of the workload")
    namespace: str = Field(default_factory=str, description="The name of the namespace")
    kind: WorkloadKind = Field(..., description="The kind of workload, either 'Deployment' or 'StatefulSet'")
    scores: Optional[WorkloadScores] = Field(default=None, description="The scores of the workload")

class ClusterScore(BaseModel):
    cluster: str = Field(default_factory=str, description="The name of the cluster")
    alias: str = Field(default_factory=str, description="The alias of the cluster")
    workload_scores: List[WorkloadScore] = Field(default_factory=list, description="List of workload scores")
    
class ClusterDescription(BaseModel):
    """
    A cluster is meant to describe a cluster. It contains a list of namespaces.
    This structure is handy for the UI to display cluster information and easily navigate
    through namespaces and resources.
    """
    cluster: str = Field(default_factory=str, description="The name of the cluster")
    alias: str = Field(default_factory=str, description="The alias of the cluster")
    namespaces: List[NamespaceDescription] = Field(default_factory=list, description="List of namespaces")
    facts: List[Fact] = Field(default_factory=list, description="The facts about the cluster components")

class Observation(BaseModel):
    """
    An observation is a value with a unit. It is used to represent a cost, a carbon footprint or an energy consumption.
    """
    value: float = Field(..., description="The value of the observation.")
    unit: str = Field(..., description="The unit of the observation.")


class ClusterFootprint(BaseModel):
    """
    A very global view of an overall cluster footprint. This is handy to display a global view of the cluster.
    """
    cluster: Cluster = Field(..., description="The name of the cluster.")
    cost: Observation = Field(..., description="The cost of the cluster.")
    carbon: Observation = Field(..., description="The carbon footprint of the cluster.")
    energy: Observation = Field(..., description="The energy consumption of the cluster.")
