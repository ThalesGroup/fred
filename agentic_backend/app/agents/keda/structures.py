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

from typing import List

from langgraph.graph import MessagesState
from pydantic import BaseModel, Field


class KedaScaling(BaseModel):
    """
    Represents a KEDA (Kubernetes Event-driven Autoscaling) `ScaledObject` resource.

    This model defines the KEDA `ScaledObject` configuration, which Kubernetes uses to specify how KEDA should scale
    a target application based on defined triggers (e.g., cron-based scaling or Prometheus-based scaling).
    """

    scaled_object: str = Field(
        description=(
            "The KEDA `ScaledObject` resource, represented as a fully-formed JSON configuration. "
            "This configuration defines the scaling behavior of a target application based on triggers, "
            "such as cron schedules or Prometheus metrics. The JSON structure follows the required format for a Kubernetes `ScaledObject`."
        )
    )

    assumptions: List[str] = Field(
        description=(
            "A list of assumptions made while creating the `ScaledObject`. This may include inferred values for missing parameters "
            "or default configurations applied in the absence of specific inputs. The list will be empty if no assumptions were needed."
        )
    )


class MessagesStateWithFinalStructuredResponse(MessagesState):
    # Final structured response from the agent
    final_response: KedaScaling
