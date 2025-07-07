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
Pydantic structure definitions to use in the carbon microservice
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.common.structure import Series
from app.services.kube.structure import Cluster


class Detail(BaseModel):
    timestamp: Optional[datetime] = Field(None, description="The timestamp of the post of consumption.")
    name: str = Field(..., description="The name of the post of consumption.")
    kind: str = Field(..., description="The kind of the post of consumption.")
    value: float = Field(..., description="The global value of the post of consumption.")


class ClusterConsumption(BaseModel):
    timestamp: datetime = Field(..., description="The list of timestamps of the consumption period.")
    value: float = Field(..., description="The global values of the consumption during the period.")
    details: List[Detail] = Field(..., description="The details of the consumption during the period.")
    unit: str = Field(..., description="The unit of the consumption.")
    cluster: Cluster = Field(..., description="The cluster of the consumption.")


class DetailSeries(BaseModel):
    name: str = Field(..., description="The name of the consumption source.")
    kind: str = Field(..., description="The kind of the consumption source, for example a namespace.")
    values: List[float] = Field(..., description="The values.")


class ClusterConsumptionSeries(Series, BaseModel):
    details: List[DetailSeries] = Field(...,
                                        description="The details of the consumption during the period.")
