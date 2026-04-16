# Copyright Thales 2026
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
Graph authoring contracts for Fred v2.

Why this package exists:
- expose the graph authoring surface without bundling runtime implementations
- keep public graph contracts alongside authoring helpers
"""

from .authoring import (
    GraphAgent,
    GraphWorkflow,
    StepResult,
    WorkflowNode,
    choice_step,
    finalize_step,
    intent_router_step,
    model_text_step,
    structured_model_step,
    typed_node,
)
from .runtime import GraphExecutionOutput, GraphNodeContext, GraphNodeResult

__all__ = [
    "GraphExecutionOutput",
    "GraphAgent",
    "GraphWorkflow",
    "GraphNodeContext",
    "GraphNodeResult",
    "StepResult",
    "WorkflowNode",
    "choice_step",
    "finalize_step",
    "intent_router_step",
    "model_text_step",
    "structured_model_step",
    "typed_node",
]
