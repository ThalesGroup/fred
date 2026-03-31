"""
Small authoring helpers for workflow-shaped graph nodes.

Why this module exists:
- graph agents currently repeat the same typed-state, model-call, and HITL choice
  plumbing across multiple candidate agents
- these helpers keep LangGraph orchestration in the runtime while shrinking the
  amount of Fred-specific ceremony inside each business node

How to use it:
- import only the helpers that remove real duplication in your graph
- keep business rules, prompts, and validation policy inside the agent

Example:
```python
@typed_node(MyState)
async def draft(
    state: MyState,
    context: GraphNodeContext,
) -> StepResult:
    return StepResult(
        state_update={"draft_sql": "SELECT * FROM sales LIMIT 20"},
        route_key="valid",
    )
```
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import ClassVar, TypeVar

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from ...contracts.context import BoundRuntimeContext, JsonScalar
from ...contracts.models import (
    GraphAgentDefinition,
    GraphConditionalDefinition,
    GraphDefinition,
    GraphEdgeDefinition,
    GraphNodeDefinition,
    GraphRouteDefinition,
)
from ...contracts.runtime import HumanChoiceOption, HumanInputRequest
from ..runtime import (
    GraphExecutionOutput,
    GraphNodeContext,
    GraphNodeResult,
)

StateT = TypeVar("StateT", bound=BaseModel)
StructuredT = TypeVar("StructuredT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class StepResult:
    """
    Author-facing description of what one workflow step decided.

    Why this model exists:
    - graph authors usually need only two things after one step runs:
      which workflow values changed, and which branch should run next
    - this model keeps that shape small and readable without exposing lower-level
      graph runtime objects in every author-written step

    How to use it:
    - return `StepResult(...)` from a node when the step learned new business
      facts or wants to choose the next branch
    - put changed workflow values in `state_update`
    - put the next branch key in `route_key` when the graph should branch
    - omit `route_key` when the graph should follow its normal direct edge

    Example:
    ```python
    # SQL step
    return StepResult(
        state_update={"draft_sql": sql},
        route_key="valid",
    )

    # Banking step
    return StepResult(
        state_update={"risk_flags": ["high_amount"]},
        route_key="review",
    )
    ```

    Author meaning:
    - think of this as "what this step changed" plus "where the workflow goes
      next"
    """

    state_update: dict[str, object] = field(default_factory=dict)
    route_key: str | None = None

    def to_graph_node_result(self) -> GraphNodeResult:
        """
        Convert the compact authoring result to the runtime node result model.

        Why this method exists:
        - authors should work with `StepResult`
        - the runtime still needs its internal graph result shape underneath

        How to use it:
        - normally called by `typed_node(...)`
        - direct calls are useful in unit tests

        Example:
        ```python
        runtime_result = StepResult(
            state_update={"customer_id": "cust-42"},
            route_key="next",
        ).to_graph_node_result()
        ```
        """

        return GraphNodeResult(
            state_update=dict(self.state_update),
            route_key=self.route_key,
        )


TypedNodeReturn = GraphNodeResult | StepResult
TypedNodeHandler = Callable[
    [StateT, GraphNodeContext],
    TypedNodeReturn | Awaitable[TypedNodeReturn],
]
GraphStepHandler = Callable[
    [BaseModel, GraphNodeContext],
    GraphNodeResult | Awaitable[GraphNodeResult],
]


@dataclass(frozen=True, slots=True)
class WorkflowNode:
    """
    One authored node inside a declarative workflow graph.

    Why this model exists:
    - authors should be able to bind a node id directly to its business handler
      without maintaining a second `node_handlers(...)` registry elsewhere

    How to use it:
    - pass a handler and optionally a title when creating `GraphWorkflow`
    - omit `title` to derive a readable title from the node id

    Example:
    ```python
    WorkflowNode(
        handler=draft_sql_step,
        title="Draft SQL",
    )
    ```
    """

    handler: GraphStepHandler
    title: str | None = None


@dataclass(frozen=True, slots=True)
class GraphWorkflow:
    """
    Author-facing declarative description of a workflow-shaped graph.

    Why this model exists:
    - graph authors should declare node handlers, direct edges, and branches in
      one place rather than spreading them across several definition methods

    How to use it:
    - set `entry` to the first node id
    - register each node in `nodes`
    - use `edges` for direct next steps
    - use `routes` only for real business branches

    Example:
    ```python
    workflow = GraphWorkflow(
        entry="load_context",
        nodes={
            "load_context": load_context_step,
            "choose_database": WorkflowNode(
                handler=choose_database_step,
                title="Choose database",
            ),
        },
        edges={"load_context": "choose_database"},
        routes={
            "choose_database": {
                "selected": "draft_sql",
                "finish": "finalize",
            }
        },
    )
    ```
    """

    entry: str
    nodes: Mapping[str, WorkflowNode | GraphStepHandler]
    edges: Mapping[str, str] = field(default_factory=dict)
    routes: Mapping[str, Mapping[str, str]] = field(default_factory=dict)

    def to_graph_definition(self) -> GraphDefinition:
        """
        Convert the declarative workflow to the runtime graph structure.

        Why this method exists:
        - the runtime still executes `GraphDefinition`, while authors work with a
          smaller workflow-shaped description

        How to use it:
        - normally used by `GraphAgent.build_graph()`
        - direct calls are useful for previews and tests

        Example:
        ```python
        graph = workflow.to_graph_definition()
        ```
        """

        return GraphDefinition(
            state_model_name="workflow_state",
            entry_node=self.entry,
            nodes=tuple(
                GraphNodeDefinition(
                    node_id=node_id,
                    title=_workflow_node_title(node_id, node_spec),
                )
                for node_id, node_spec in self.nodes.items()
            ),
            edges=tuple(
                GraphEdgeDefinition(source=source, target=target)
                for source, target in self.edges.items()
            ),
            conditionals=tuple(
                GraphConditionalDefinition(
                    source=source,
                    routes=tuple(
                        GraphRouteDefinition(
                            route_key=route_key,
                            target=target,
                            label=route_key.replace("_", " "),
                        )
                        for route_key, target in route_map.items()
                    ),
                )
                for source, route_map in self.routes.items()
            ),
        )

    def node_handlers(self) -> dict[str, GraphStepHandler]:
        """
        Return the node handler mapping declared by this workflow.

        Why this method exists:
        - the runtime still validates a `node_id -> handler` mapping

        How to use it:
        - normally used by `GraphAgent.node_handlers()`
        - direct calls are useful in tests

        Example:
        ```python
        handlers = workflow.node_handlers()
        ```
        """

        handlers: dict[str, GraphStepHandler] = {}
        for node_id, node_spec in self.nodes.items():
            if isinstance(node_spec, WorkflowNode):
                handlers[node_id] = node_spec.handler
            else:
                handlers[node_id] = node_spec
        return handlers


class GraphAgent(GraphAgentDefinition):
    """
    Simpler authoring base for workflow-shaped graph agents.

    Why this base class exists:
    - authors should describe identity, models, workflow, and initial state
      directly, without re-implementing repeated definition methods

    How to use it:
    - declare `input_schema`, `state_schema`, and `workflow` as class attributes
    - declare `input_to_state` only when input field names differ from state
      field names
    - optionally set `output_state_field` when the final text lives in one state
      field
    - override `build_initial_state(...)` only when simple field mapping is not
      enough

    Example:
    ```python
    class SqlAgentDefinition(GraphAgent):
        input_schema = SqlAgentInput
        state_schema = SqlAgentState
        input_to_state = {"message": "latest_user_text"}
        workflow = GraphWorkflow(
            entry="load_context",
            nodes={"load_context": load_context_step},
        )
        output_state_field = "final_text"
    ```
    """

    input_schema: ClassVar[type[BaseModel] | None] = None
    state_schema: ClassVar[type[BaseModel] | None] = None
    input_to_state: ClassVar[Mapping[str, str]] = {}
    output_schema: ClassVar[type[BaseModel]] = GraphExecutionOutput
    workflow: ClassVar[GraphWorkflow | None] = None
    output_state_field: ClassVar[str | None] = "final_text"

    def build_graph(self) -> GraphDefinition:
        workflow = self._required_workflow()
        graph = workflow.to_graph_definition()
        state_schema = self._required_state_schema()
        return graph.model_copy(update={"state_model_name": state_schema.__name__})

    def input_model(self) -> type[BaseModel]:
        return self._required_input_schema()

    def state_model(self) -> type[BaseModel]:
        return self._required_state_schema()

    def output_model(self) -> type[BaseModel]:
        return type(self).output_schema

    def build_initial_state(
        self,
        input_model: BaseModel,
        binding: BoundRuntimeContext,
    ) -> BaseModel:
        """
        Build the first workflow state from validated input.

        Why this method exists:
        - the runtime needs one concrete state object before the first node runs
        - the default behavior should cover simple agents without forcing authors
          to write a trivial input-to-state bridge

        How to use it:
        - declare `input_to_state` when input and state field names differ
        - override this method only when initial state requires real business
          logic beyond simple field mapping

        Example:
        ```python
        class SqlAgentDefinition(GraphAgent):
            input_schema = SqlAgentInput
            state_schema = SqlAgentState
            input_to_state = {"message": "latest_user_text"}
        ```
        """

        del binding
        input_schema = self._required_input_schema()
        state_schema = self._required_state_schema()
        validated_input = input_schema.model_validate(input_model)
        input_payload = validated_input.model_dump()
        state_fields = state_schema.model_fields

        state_payload: dict[str, object] = {
            field_name: value
            for field_name, value in input_payload.items()
            if field_name in state_fields
        }

        for input_field, state_field in type(self).input_to_state.items():
            if input_field not in input_payload:
                raise ValueError(
                    f"GraphAgent input_to_state references unknown input field '{input_field}'."
                )
            if state_field not in state_fields:
                raise ValueError(
                    f"GraphAgent input_to_state references unknown state field '{state_field}'."
                )
            state_payload[state_field] = input_payload[input_field]

        return state_schema.model_validate(state_payload)

    def node_handlers(self) -> Mapping[str, object]:
        return self._required_workflow().node_handlers()

    def build_output(self, state: BaseModel) -> BaseModel:
        output_schema = self.output_model()
        if output_schema is not GraphExecutionOutput:
            raise NotImplementedError(
                "GraphAgent only defaults build_output for GraphExecutionOutput. "
                "Override build_output(...) for custom output schemas."
            )
        output_field = type(self).output_state_field
        if not output_field:
            return GraphExecutionOutput(content="")
        content = getattr(state, output_field, "")
        normalized_content = content if isinstance(content, str) else str(content or "")
        return GraphExecutionOutput(content=normalized_content)

    def _required_input_schema(self) -> type[BaseModel]:
        input_schema = type(self).input_schema
        if input_schema is None:
            raise NotImplementedError(
                "GraphAgent subclasses must declare `input_schema`."
            )
        return input_schema

    def _required_state_schema(self) -> type[BaseModel]:
        state_schema = type(self).state_schema
        if state_schema is None:
            raise NotImplementedError(
                "GraphAgent subclasses must declare `state_schema`."
            )
        return state_schema

    def _required_workflow(self) -> GraphWorkflow:
        workflow = type(self).workflow
        if workflow is None:
            raise NotImplementedError("GraphAgent subclasses must declare `workflow`.")
        return workflow


def _workflow_node_title(
    node_id: str,
    node_spec: WorkflowNode | GraphStepHandler,
) -> str:
    """
    Return a readable node title for one authored workflow node.

    Why this helper exists:
    - authoring should not require explicit titles for obvious node ids

    How to use it:
    - used internally by `GraphWorkflow.to_graph_definition()`

    Example:
    ```python
    title = _workflow_node_title("load_context", load_context_step)
    ```
    """

    if isinstance(node_spec, WorkflowNode) and node_spec.title:
        return node_spec.title
    return node_id.replace("_", " ").title()


def typed_node(
    state_model: type[StateT],
) -> Callable[
    [TypedNodeHandler[StateT]],
    Callable[[BaseModel, GraphNodeContext], Awaitable[GraphNodeResult]],
]:
    """
    Wrap one node handler so it receives validated typed state directly.

    Why this helper exists:
    - graph nodes currently repeat `StateModel.model_validate(state)` in every
      handler
    - typed handlers should focus on business rules, not state plumbing

    How to use it:
    - decorate a handler that accepts `(typed_state, context)`
    - return either `StepResult` or `GraphNodeResult`

    Example:
    ```python
    @typed_node(MyState)
    async def route(
        state: MyState,
        context: GraphNodeContext,
    ) -> StepResult:
        if state.amount > 10_000:
            return StepResult(route_key="manual_review")
        return StepResult(route_key="auto_approve")
    ```
    """

    def decorator(
        handler: TypedNodeHandler[StateT],
    ) -> Callable[[BaseModel, GraphNodeContext], Awaitable[GraphNodeResult]]:
        async def wrapped(
            state: BaseModel, context: GraphNodeContext
        ) -> GraphNodeResult:
            typed_state = state_model.model_validate(state)
            result = handler(typed_state, context)
            resolved = await result if inspect.isawaitable(result) else result
            if isinstance(resolved, GraphNodeResult):
                return resolved
            if isinstance(resolved, StepResult):
                return resolved.to_graph_node_result()
            raise TypeError(
                "typed_node handlers must return StepResult or GraphNodeResult."
            )

        return wrapped

    return decorator


async def model_text_step(
    context: GraphNodeContext,
    *,
    operation: str,
    user_prompt: str,
    system_prompt: str | None = None,
    fallback_text: str = "",
) -> str:
    """
    Invoke the bound chat model and return one stripped text payload.

    Why this helper exists:
    - graph nodes should not repeatedly rebuild the same message list and string
      extraction logic
    - the first authoring layer should make model calls smaller without hiding
      prompt ownership from the agent

    How to use it:
    - pass one operation name plus the user and optional system prompt
    - provide `fallback_text` when the node should stay runnable without a model

    Example:
    ```python
    text = await model_text_step(
        context,
        operation="draft_sql",
        system_prompt="Write one read-only SQL query.",
        user_prompt=question,
        fallback_text="SELECT 1",
    )
    ```
    """

    if context.model is None:
        return fallback_text

    messages: list[BaseMessage] = [HumanMessage(content=user_prompt)]
    if system_prompt is not None:
        messages.insert(0, SystemMessage(content=system_prompt))
    response = await context.invoke_model(messages, operation=operation)
    return str(getattr(response, "content", "")).strip() or fallback_text


async def structured_model_step(
    context: GraphNodeContext,
    *,
    operation: str,
    output_model: type[StructuredT],
    user_prompt: str,
    system_prompt: str | None = None,
    fallback_output: StructuredT | Mapping[str, object] | None = None,
) -> StructuredT:
    """
    Invoke the bound model and return one validated structured result.

    Why this helper exists:
    - routing and extraction nodes should work with typed control decisions
      instead of free-text parsing
    - graph authors should not repeat structured-output invocation and fallback
      handling in every control node

    How to use it:
    - pass the Pydantic model that defines the decision or extraction schema
    - pass one user prompt and optionally one system prompt
    - provide `fallback_output` when the node should still run without a model

    Example:
    ```python
    decision = await structured_model_step(
        context,
        operation="route_request",
        output_model=RouteDecision,
        system_prompt="Classify the request.",
        user_prompt=user_text,
        fallback_output={"route": "specialist", "reason": "fallback"},
    )
    ```
    """

    messages: list[BaseMessage] = [HumanMessage(content=user_prompt)]
    if system_prompt is not None:
        messages.insert(0, SystemMessage(content=system_prompt))

    if context.model is None:
        if fallback_output is None:
            raise RuntimeError(
                "structured_model_step requires a bound chat model or fallback_output."
            )
        return _validate_structured_output(output_model, fallback_output)

    resolved = await context.invoke_structured_model(
        output_model,
        messages,
        operation=operation,
    )
    return _validate_structured_output(output_model, resolved)


async def intent_router_step(
    context: GraphNodeContext,
    *,
    operation: str,
    route_model: type[StructuredT],
    user_prompt: str,
    system_prompt: str | None = None,
    fallback_output: StructuredT | Mapping[str, object] | None = None,
    route_field: str = "route",
    state_update_builder: Callable[[StructuredT], Mapping[str, object]] | None = None,
) -> StepResult:
    """
    Run one structured routing decision and convert it to `StepResult`.

    Why this helper exists:
    - many business graphs start with the same control problem: classify the
      request into one of a few routes, then branch the workflow
    - this helper keeps the routing mechanism shared while each agent still owns
      its own route labels and prompt

    How to use it:
    - define a small Pydantic route model with a string field such as `route`
    - pass the agent-specific routing prompt and current user text
    - optionally map the decision to state updates with `state_update_builder`

    Example:
    ```python
    return await intent_router_step(
        context,
        operation="route_request",
        route_model=RouteDecision,
        system_prompt=ROUTER_PROMPT,
        user_prompt=state.latest_user_text,
        fallback_output={"route": "domain_request", "reason": "fallback"},
    )
    ```
    """

    decision = await structured_model_step(
        context,
        operation=operation,
        output_model=route_model,
        user_prompt=user_prompt,
        system_prompt=system_prompt,
        fallback_output=fallback_output,
    )
    route_value = getattr(decision, route_field, None)
    if not isinstance(route_value, str) or not route_value.strip():
        raise ValueError(
            f"intent_router_step expected non-empty string field '{route_field}'."
        )
    state_update = (
        dict(state_update_builder(decision)) if state_update_builder is not None else {}
    )
    return StepResult(state_update=state_update, route_key=route_value.strip())


async def choice_step(
    context: GraphNodeContext,
    *,
    stage: str | None,
    title: str | None,
    question: str,
    choices: Sequence[HumanChoiceOption],
    metadata: Mapping[str, JsonScalar] | None = None,
) -> str | None:
    """
    Ask the user for a structured choice and return the selected `choice_id`.

    Why this helper exists:
    - graph nodes currently repeat `HumanInputRequest` construction and response
      parsing for simple choice-based pauses

    How to use it:
    - pass already-built `HumanChoiceOption` items
    - interpret a `None` result as cancel or invalid resume payload

    Example:
    ```python
    choice_id = await choice_step(
        context,
        stage="scope_selection",
        title="Choose database",
        question="Which database should I use?",
        choices=options,
        metadata={"agent_family": "sql_analyst_graph"},
    )
    ```
    """

    decision = await context.request_human_input(
        HumanInputRequest(
            stage=stage,
            title=title,
            question=question,
            choices=tuple(choices),
            metadata=dict(metadata or {}),
        )
    )
    payload = decision if isinstance(decision, dict) else {}
    choice_id = payload.get("choice_id")
    if not isinstance(choice_id, str):
        return None
    normalized = choice_id.strip()
    return normalized or None


def finalize_step(
    *,
    final_text: str | None,
    summary_text: str | None = None,
    fallback_text: str,
    done_reason: str | None = None,
    fallback_reason: str = "completed_without_summary",
) -> GraphNodeResult:
    """
    Return the standard terminal update for a graph node.

    Why this helper exists:
    - many workflow agents end with the same rule: keep the existing final text if
      present, otherwise set one explicit fallback

    How to use it:
    - pass the current candidate final and summary text values
    - the helper returns an empty update when the graph already has user-facing text

    Example:
    ```python
    return finalize_step(
        final_text=state.final_text,
        summary_text=state.result_summary,
        fallback_text="No summary available.",
        done_reason=state.done_reason,
    )
    ```
    """

    normalized_final = (final_text or "").strip()
    normalized_summary = (summary_text or "").strip()
    if normalized_final or normalized_summary:
        return GraphNodeResult(state_update={})
    return GraphNodeResult(
        state_update={
            "final_text": fallback_text,
            "done_reason": done_reason or fallback_reason,
        }
    )


def _validate_structured_output(
    output_model: type[StructuredT],
    raw_output: StructuredT | Mapping[str, object] | BaseModel,
) -> StructuredT:
    """
    Normalize one structured model result to the requested Pydantic schema.

    Why this helper exists:
    - runtime and fallback paths can return slightly different structured shapes
    - authoring helpers should still hand the node one consistent model type

    How to use it:
    - used internally by `structured_model_step(...)`

    Example:
    ```python
    decision = _validate_structured_output(
        RouteDecision,
        {"route": "capabilities", "reason": "fallback"},
    )
    ```
    """

    if isinstance(raw_output, output_model):
        return raw_output
    if isinstance(raw_output, BaseModel):
        return output_model.model_validate(raw_output.model_dump())
    return output_model.model_validate(dict(raw_output))
