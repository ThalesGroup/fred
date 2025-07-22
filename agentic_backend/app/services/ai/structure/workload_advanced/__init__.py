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

"""
Module to represent advanced informations about a workload knowing its commercial off-the-shelf
software nature.
"""

from typing import Optional, Union

from langfuse.callback import CallbackHandler
from pydantic import BaseModel, Field

from app.services.ai.structure.workload_id import WorkloadId
from app.services.ai.structure.workload_context import WorkloadContext

from app.services.ai.structure.workload_advanced.punchline import PunchlineAdvanced
from app.services.ai.structure.workload_advanced.search_engine import SearchEngineAdvanced

from app.services.ai.structure.workload_advanced.kafka import KafkaAdvanced
from app.services.ai.structure.workload_advanced.search_engine_dashboard import (
    SearchEngineDashboardAdvanced,
)

class WorkloadAdvanced(BaseModel):
    """
    Represents advanced informations about a workload knowing its commercial off-the-shelf software
    nature.
    """
    data: Union[
            KafkaAdvanced, SearchEngineDashboardAdvanced,
            SearchEngineAdvanced, PunchlineAdvanced,
            None
        ] = Field(discriminator="type")

    def __init__(self, data: Union[
            KafkaAdvanced, SearchEngineDashboardAdvanced,
            SearchEngineAdvanced, PunchlineAdvanced
        ]):
        super().__init__(data=data)

    @classmethod
    def from_workload_id_and_context(
        cls,
        workload_id: WorkloadId,
        workload_context: WorkloadContext,
        langfuse_handler: Optional[CallbackHandler] = None,
    ) -> Optional['WorkloadAdvanced']:
        """
        Return an advanced workload instance based on its context and its commercial off-the-shelf
        software name.

        Args:
            workload_id (WorkloadId): The workload id.
            workload_context (WorkloadContext): The workload context.
            langfuse_handler (Optional[CallbackHandler]): The Langfuse callback handler.
        """
        # Get the lowercase commercial off-the-shelf software name.
        workload_name = workload_id.workload_id.lower()

        # Return the appropriate advanced workload instance based on the workload name.
        # Import classes inside to avoid circular imports.
        if 'kafka' in workload_name:
            return cls(
                data=KafkaAdvanced.from_workload_context(
                    workload_context,
                    langfuse_handler
                )
            )

        if 'opensearch' in workload_name and 'dashboard' in workload_name:
            return cls(
                data=SearchEngineDashboardAdvanced.from_workload_context(
                    workload_context,
                    langfuse_handler,
                )
            )

        if 'opensearch' in workload_name:
            return cls(
                data=SearchEngineAdvanced.from_workload_context(
                    workload_context,
                    langfuse_handler,
                )
            )

        if 'punchline' in workload_name:
            return cls(
                data=PunchlineAdvanced.from_workload_context(
                    workload_context,
                    langfuse_handler,
                )
            )

        return cls(data=None)
