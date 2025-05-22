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

from typing import Literal

from pydantic import BaseModel


class PlanDecision(BaseModel):
    """Decision after evaluation."""

    action: Literal["planning", "respond"]


class ExecuteDecision(BaseModel):
    """
    Decision before expert execution.
    """

    # Add your custom expert flows here to include them in Fred
    expert: Literal[
        "GeneralistExpert", 
        "DocumentsExpert",
        "TechnicalKubernetesExpert", 
        "TheoreticalKubernetesExpert", 
        "KedaExpert",
        "MonitoringExpert",
        "K8SOperatorExpert"]