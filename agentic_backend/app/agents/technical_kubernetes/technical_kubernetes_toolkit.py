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

from langchain_core.tools import BaseToolkit, StructuredTool
from pydantic import BaseModel, Field


class ClusterTopologyArgs(BaseModel):
    """
    Arguments for the get_cluster_topology function
    """

    cluster_fullname: str = Field(description="The fullname of the cluster")


def wrapper(ai_service):
    def get_cluster_topology(cluster_fullname: str) -> str:
        """
        "Retrieves a condensed representation of a Kubernetes cluster"
        """
        return ai_service.get_cluster_topology(cluster_fullname)

    return get_cluster_topology


class TechnicalKubernetesToolkit(BaseToolkit):
    """
    The technical Kubernetes toolkit
    """

    tools: list = Field(
        default_factory=list, description="List of tools in the toolkit."
    )

    def get_tools(self):
        return self.tools


class TechnicalKubernetesToolkitBuilder:
    def __init__(self, ai_service):
        self.ai_service = ai_service

    def build(self):
        func = wrapper(ai_service=self.ai_service)
        raw_tool = StructuredTool.from_function(
            func=func,
            name="get_cluster_topology",
            description="Retrieves a condensed representation of a Kubernetes cluster.",
            args_schema=ClusterTopologyArgs,
            return_direct=True,
        )
        return TechnicalKubernetesToolkit(tools=[raw_tool])
