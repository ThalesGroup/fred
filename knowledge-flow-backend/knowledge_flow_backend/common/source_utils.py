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


import logging

from knowledge_flow_backend.common.document_structures import SourceType
from knowledge_flow_backend.common.structures import DocumentSourceConfig

logger = logging.getLogger(__name__)


class UnknownSourceTagError(ValueError):
    """Raised when a source_tag is not configured in the system."""


def resolve_source_type(source_tag: str) -> SourceType:
    from knowledge_flow_backend.application_context import ApplicationContext

    config = ApplicationContext.get_instance().get_config()
    try:
        source_config: DocumentSourceConfig = config.document_sources[source_tag]
    except KeyError:
        logger.error(f"[resolve_source_type] Unknown source tag: {source_tag}")
        raise UnknownSourceTagError(f"Unknown source tag: '{source_tag}'")

    if source_config.type == "push":
        return SourceType.PUSH
    elif source_config.type == "pull":
        return SourceType.PULL
    else:
        raise ValueError(f"Invalid source type for tag '{source_tag}': {source_config.type}")
