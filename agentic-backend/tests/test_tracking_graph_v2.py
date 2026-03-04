from __future__ import annotations

import json
from typing import cast

import pytest
from fred_core import PostgresStoreConfig
from fred_core.sql import create_async_engine_from_config
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.checkpoint.memory import MemorySaver

from agentic_backend.agents.v2 import PostalTrackingDefinition
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.agents.v2 import (
    AwaitingHumanRuntimeEvent,
    BoundRuntimeContext,
    ExecutionConfig,
    GraphRuntime,
    PortableContext,
    PortableEnvironment,
    RuntimeServices,
    ToolProviderPort,
    inspect_agent,
)
from agentic_backend.core.agents.v2.runtime import FinalRuntimeEvent, RuntimeEventKind
from agentic_backend.core.agents.v2.sql_checkpointer import FredSqlCheckpointer


class TrackingDemoToolProvider(ToolProviderPort):
    def __init__(self) -> None:
        self.bind_calls: list[str | None] = []
        self.activate_calls = 0
        self.close_calls = 0
        self.calls: list[tuple[str, dict[str, object]]] = []

    def bind(self, binding: BoundRuntimeContext) -> None:
        self.bind_calls.append(binding.runtime_context.session_id)

    async def activate(self) -> None:
        self.activate_calls += 1

    def get_tools(self) -> tuple[BaseTool, ...]:
        return (
            StructuredTool.from_function(
                func=None,
                coroutine=self.list_my_active_parcels,
                name="list_my_active_parcels",
                description="List caller parcels linked to the current user.",
            ),
            StructuredTool.from_function(
                func=None,
                coroutine=self.seed_demo_parcel_exception_for_current_user,
                name="seed_demo_parcel_exception_for_current_user",
                description="Seed a business parcel exception for the current user.",
            ),
            StructuredTool.from_function(
                func=None,
                coroutine=self.seed_demo_tracking_incident,
                name="seed_demo_tracking_incident",
                description="Seed an IoT tracking incident for a parcel.",
            ),
            StructuredTool.from_function(
                func=None,
                coroutine=self.track_package,
                name="track_package",
                description="Fetch business parcel tracking details.",
            ),
            StructuredTool.from_function(
                func=None,
                coroutine=self.get_live_tracking_snapshot,
                name="get_live_tracking_snapshot",
                description="Fetch live IoT tracking status.",
            ),
            StructuredTool.from_function(
                func=None,
                coroutine=self.list_tracking_events,
                name="list_tracking_events",
                description="Fetch ordered IoT incident events.",
            ),
            StructuredTool.from_function(
                func=None,
                coroutine=self.get_pickup_points_nearby,
                name="get_pickup_points_nearby",
                description="Return nearby pickup points.",
            ),
            StructuredTool.from_function(
                func=None,
                coroutine=self.get_route_geometry,
                name="get_route_geometry",
                description="Return a demo route geometry.",
            ),
            StructuredTool.from_function(
                func=None,
                coroutine=self.reroute_package_to_pickup_point,
                name="reroute_package_to_pickup_point",
                description="Reroute a parcel to a pickup point.",
            ),
            StructuredTool.from_function(
                func=None,
                coroutine=self.reschedule_delivery,
                name="reschedule_delivery",
                description="Reschedule a parcel home delivery.",
            ),
            StructuredTool.from_function(
                func=None,
                coroutine=self.notify_customer,
                name="notify_customer",
                description="Send a customer notification.",
            ),
        )

    async def aclose(self) -> None:
        self.close_calls += 1

    async def list_my_active_parcels(
        self, include_terminal: bool = False, limit: int = 5
    ) -> dict[str, object]:
        args = {"include_terminal": include_terminal, "limit": limit}
        self.calls.append(("list_my_active_parcels", args))
        return {
            "ok": True,
            "has_active_parcels": False,
            "count": 0,
            "parcels": [],
        }

    async def seed_demo_parcel_exception_for_current_user(self) -> dict[str, object]:
        self.calls.append(("seed_demo_parcel_exception_for_current_user", {}))
        return {
            "ok": True,
            "tracking_id": "PKG-DEMO-001",
            "status": "DELAYED_AT_HUB",
            "incident_kind": "delay",
        }

    async def seed_demo_tracking_incident(self, tracking_id: str) -> dict[str, object]:
        args = {"tracking_id": tracking_id}
        self.calls.append(("seed_demo_tracking_incident", args))
        return {
            "ok": True,
            "tracking_id": tracking_id,
            "incident_id": "IOT-INC-001",
            "phase": "stalled",
        }

    async def track_package(self, tracking_id: str) -> dict[str, object]:
        args = {"tracking_id": tracking_id}
        self.calls.append(("track_package", args))
        return {
            "ok": True,
            "tracking_id": tracking_id,
            "status": "DELAYED_AT_HUB",
            "delivery": {
                "address": {
                    "city": "Paris",
                    "postal_code": "75015",
                }
            },
            "eta": {"delay_minutes": 95},
            "actions_available": [
                "notify_customer",
                "reschedule_delivery",
                "reroute_package_to_pickup_point",
            ],
        }

    async def get_live_tracking_snapshot(self, tracking_id: str) -> dict[str, object]:
        args = {"tracking_id": tracking_id}
        self.calls.append(("get_live_tracking_snapshot", args))
        return {
            "ok": True,
            "tracking_id": tracking_id,
            "phase": "held_at_hub",
            "battery_level": 91,
            "hub_status": {
                "hub_id": "HUB-PAR-01",
                "operational_state": "DEGRADED",
                "congestion_level": "HIGH",
                "queue_depth": 540,
            },
            "vehicle_position": {
                "vehicle_id": "VAN-17",
                "lat": 48.8580,
                "lon": 2.3415,
            },
            "active_alerts": [
                {
                    "alert_id": "ALT-001",
                    "severity": "warning",
                    "message": "Hub congestion detected",
                }
            ],
            "map_overlay": {
                "route_polyline": [
                    {"lat": 48.8566, "lon": 2.3522},
                    {"lat": 48.8607, "lon": 2.3451},
                    {"lat": 48.8625, "lon": 2.3367},
                ],
                "markers": [
                    {
                        "id": "HUB-PAR-01",
                        "kind": "hub",
                        "label": "Paris Distribution Hub",
                        "lat": 48.8566,
                        "lon": 2.3522,
                    },
                    {
                        "id": "VAN-17",
                        "kind": "vehicle",
                        "label": "VAN-17",
                        "lat": 48.8580,
                        "lon": 2.3415,
                    },
                ],
            },
        }

    async def list_tracking_events(
        self, tracking_id: str, since_seq: int = 0, limit: int = 20
    ) -> dict[str, object]:
        args = {"tracking_id": tracking_id, "since_seq": since_seq, "limit": limit}
        self.calls.append(("list_tracking_events", args))
        return {
            "ok": True,
            "tracking_id": tracking_id,
            "events": [
                {
                    "seq": 1,
                    "type": "DELAY_ALERT",
                    "severity": "warning",
                    "message": "Hub congestion impacts route",
                }
            ],
        }

    async def get_pickup_points_nearby(
        self, city: str, postal_code: str, limit: int
    ) -> dict[str, object]:
        args = {"city": city, "postal_code": postal_code, "limit": limit}
        self.calls.append(("get_pickup_points_nearby", args))
        return {
            "pickup_points": [
                {
                    "pickup_point_id": "PP-75015-1",
                    "name": "Paris Beaugrenelle",
                    "lat": 48.8506,
                    "lon": 2.2874,
                    "opening_hours": "08:00-20:00",
                    "type": "pickup_point",
                },
                {
                    "pickup_point_id": "PP-75015-2",
                    "name": "Paris Convention",
                    "lat": 48.8384,
                    "lon": 2.2982,
                    "opening_hours": "09:00-19:00",
                    "type": "pickup_locker",
                },
            ]
        }

    async def get_route_geometry(self, tracking_id: str) -> dict[str, object]:
        args = {"tracking_id": tracking_id}
        self.calls.append(("get_route_geometry", args))
        return {
            "ok": True,
            "route_geometry": {
                "route_id": "ROUTE-001",
                "polyline": [
                    {"lat": 48.8566, "lon": 2.3522},
                    {"lat": 48.8607, "lon": 2.3451},
                    {"lat": 48.8625, "lon": 2.3367},
                ],
            },
            "markers": [
                {
                    "id": "PP-PAR-001",
                    "kind": "pickup_locker",
                    "label": "Paris Louvre Locker",
                    "lat": 48.8625,
                    "lon": 2.3367,
                }
            ],
        }

    async def reroute_package_to_pickup_point(
        self, tracking_id: str, pickup_point_id: str, reason: str
    ) -> dict[str, object]:
        args = {
            "tracking_id": tracking_id,
            "pickup_point_id": pickup_point_id,
            "reason": reason,
        }
        self.calls.append(("reroute_package_to_pickup_point", args))
        point_name = (
            "Paris Beaugrenelle"
            if pickup_point_id == "PP-75015-1"
            else "Paris Convention"
        )
        return {
            "ok": True,
            "status": "rerouted",
            "delivery": {
                "pickup_point_id": pickup_point_id,
                "pickup_point_name": point_name,
            },
        }

    async def reschedule_delivery(
        self, tracking_id: str, requested_date: str, time_window: str
    ) -> dict[str, object]:
        args = {
            "tracking_id": tracking_id,
            "requested_date": requested_date,
            "time_window": time_window,
        }
        self.calls.append(("reschedule_delivery", args))
        return {
            "ok": True,
            "status": "DELIVERY_RESCHEDULED",
            "delivery": {
                "scheduled_date": requested_date,
                "time_window": time_window,
            },
        }

    async def notify_customer(
        self, tracking_id: str, channel: str, message: str
    ) -> dict[str, object]:
        args = {
            "tracking_id": tracking_id,
            "channel": channel,
            "message": message,
        }
        self.calls.append(("notify_customer", args))
        return {
            "ok": True,
            "notification_id": "notif-001",
            "tracking_id": tracking_id,
            "channel": channel,
        }


class JsonStringTrackingDemoToolProvider(TrackingDemoToolProvider):
    async def list_my_active_parcels(
        self, include_terminal: bool = False, limit: int = 5
    ) -> str:
        payload = await super().list_my_active_parcels(include_terminal, limit)
        return json.dumps(payload)

    async def seed_demo_parcel_exception_for_current_user(self) -> str:
        payload = await super().seed_demo_parcel_exception_for_current_user()
        return json.dumps(payload)

    async def seed_demo_tracking_incident(self, tracking_id: str) -> str:
        payload = await super().seed_demo_tracking_incident(tracking_id)
        return json.dumps(payload)

    async def track_package(self, tracking_id: str) -> str:
        payload = await super().track_package(tracking_id)
        return json.dumps(payload)

    async def get_live_tracking_snapshot(self, tracking_id: str) -> str:
        payload = await super().get_live_tracking_snapshot(tracking_id)
        return json.dumps(payload)

    async def list_tracking_events(
        self, tracking_id: str, since_seq: int = 0, limit: int = 20
    ) -> str:
        payload = await super().list_tracking_events(tracking_id, since_seq, limit)
        return json.dumps(payload)

    async def get_pickup_points_nearby(
        self, city: str, postal_code: str, limit: int
    ) -> str:
        payload = await super().get_pickup_points_nearby(city, postal_code, limit)
        return json.dumps(payload)

    async def get_route_geometry(self, tracking_id: str) -> str:
        payload = await super().get_route_geometry(tracking_id)
        return json.dumps(payload)

    async def reroute_package_to_pickup_point(
        self, tracking_id: str, pickup_point_id: str, reason: str
    ) -> str:
        payload = await super().reroute_package_to_pickup_point(
            tracking_id, pickup_point_id, reason
        )
        return json.dumps(payload)

    async def reschedule_delivery(
        self, tracking_id: str, requested_date: str, time_window: str
    ) -> str:
        payload = await super().reschedule_delivery(
            tracking_id, requested_date, time_window
        )
        return json.dumps(payload)

    async def notify_customer(
        self, tracking_id: str, channel: str, message: str
    ) -> str:
        payload = await super().notify_customer(tracking_id, channel, message)
        return json.dumps(payload)


class MultiParcelTrackingDemoToolProvider(TrackingDemoToolProvider):
    async def list_my_active_parcels(
        self, include_terminal: bool = False, limit: int = 5
    ) -> dict[str, object]:
        args = {"include_terminal": include_terminal, "limit": limit}
        self.calls.append(("list_my_active_parcels", args))
        return {
            "ok": True,
            "has_active_parcels": True,
            "count": 2,
            "parcels": [
                {
                    "tracking_id": "PKG-DEMO-A",
                    "status": "DELAYED_AT_HUB",
                    "delay_minutes": 120,
                    "current_location": {"label": "Paris Distribution Hub"},
                },
                {
                    "tracking_id": "PKG-DEMO-B",
                    "status": "DELAYED_AT_HUB",
                    "delay_minutes": 240,
                    "current_location": {"label": "Paris Distribution Hub"},
                },
            ],
        }

    async def track_package(self, tracking_id: str) -> dict[str, object]:
        payload = await super().track_package(tracking_id)
        payload["tracking_id"] = tracking_id
        return payload

    async def seed_demo_tracking_incident(self, tracking_id: str) -> dict[str, object]:
        payload = await super().seed_demo_tracking_incident(tracking_id)
        payload["tracking_id"] = tracking_id
        return payload


def _binding(session_id: str) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(
            session_id=session_id,
            user_id="user-1",
            language="fr",
        ),
        portable_context=PortableContext(
            request_id=f"req-{session_id}",
            correlation_id=f"corr-{session_id}",
            actor="user:demo",
            tenant="fred",
            environment=PortableEnvironment.DEV,
            session_id=session_id,
            agent_id="tracking.graph.demo.v2",
        ),
    )


@pytest.mark.asyncio
async def test_tracking_graph_demo_inspection_exposes_real_graph_preview() -> None:
    definition = PostalTrackingDefinition()

    inspection = inspect_agent(definition)

    assert inspection.agent_id == "tracking.graph.demo.v2"
    assert inspection.execution_category.value == "graph"
    assert [server.id for server in inspection.default_mcp_servers] == [
        "mcp-postal-business-demo",
        "mcp-iot-tracking-demo",
    ]
    assert inspection.preview.kind.value == "mermaid"
    assert "Route request" in inspection.preview.content
    assert "Ensure IoT context" in inspection.preview.content
    assert "Choose resolution" in inspection.preview.content
    assert "Apply reroute" in inspection.preview.content
    assert "Apply reschedule" in inspection.preview.content


@pytest.mark.asyncio
async def test_tracking_graph_demo_executes_hitl_reroute_and_returns_geo_part() -> None:
    definition = PostalTrackingDefinition()
    tool_provider = TrackingDemoToolProvider()
    checkpointer = MemorySaver()
    runtime = GraphRuntime(
        definition=definition,
        services=RuntimeServices(
            tool_provider=tool_provider,
            checkpointer=checkpointer,
        ),
    )
    runtime.bind(_binding("tracking-demo-session"))
    executor = await runtime.get_executor()

    first_run = [
        event
        async for event in executor.stream(
            definition.input_model()(
                message="Peux-tu rerouter ce colis vers un point relais ?"
            ),
            ExecutionConfig(),
        )
    ]

    event_kinds = [event.kind.value for event in first_run]
    assert event_kinds[0] == RuntimeEventKind.STATUS.value
    assert RuntimeEventKind.TOOL_CALL.value in event_kinds
    assert RuntimeEventKind.TOOL_RESULT.value in event_kinds
    assert event_kinds[-1] == RuntimeEventKind.AWAITING_HUMAN.value

    awaited = cast(AwaitingHumanRuntimeEvent, first_run[-1])
    assert awaited.request.stage == "tracking_resolution"
    assert awaited.request.choices[0].id.startswith("reroute:")
    assert awaited.request.checkpoint_id is not None
    assert tool_provider.bind_calls == ["tracking-demo-session"]
    assert tool_provider.activate_calls == 1
    called_tools = [name for name, _ in tool_provider.calls]
    assert called_tools[0] == "list_my_active_parcels"
    assert "seed_demo_parcel_exception_for_current_user" in called_tools
    assert "track_package" in called_tools
    assert "get_live_tracking_snapshot" in called_tools
    assert "list_tracking_events" in called_tools
    assert "get_pickup_points_nearby" in called_tools
    assert "get_route_geometry" in called_tools

    resumed_run = [
        event
        async for event in executor.stream(
            definition.input_model()(message="ignored-on-resume"),
            ExecutionConfig(
                thread_id="tracking-demo-session",
                checkpoint_id=awaited.request.checkpoint_id,
                resume_payload={"choice_id": "reroute:PP-75015-1"},
            ),
        )
    ]

    resumed_kinds = [event.kind.value for event in resumed_run[:-1]]
    assert RuntimeEventKind.TOOL_CALL.value in resumed_kinds
    assert RuntimeEventKind.TOOL_RESULT.value in resumed_kinds
    final_event = cast(FinalRuntimeEvent, resumed_run[-1])
    assert final_event.kind == RuntimeEventKind.FINAL
    assert "PKG-DEMO-001" in final_event.content
    assert "PP-75015-1" in final_event.content
    assert "notif-001" in final_event.content
    assert len(final_event.ui_parts) == 1
    assert final_event.ui_parts[0].type == "geo"
    assert final_event.ui_parts[0].geojson["type"] == "FeatureCollection"
    assert len(final_event.ui_parts[0].geojson["features"]) >= 2

    assert [name for name, _ in tool_provider.calls[-2:]] == [
        "reroute_package_to_pickup_point",
        "notify_customer",
    ]


@pytest.mark.asyncio
async def test_tracking_graph_demo_executes_hitl_reschedule() -> None:
    definition = PostalTrackingDefinition()
    tool_provider = TrackingDemoToolProvider()
    checkpointer = MemorySaver()
    runtime = GraphRuntime(
        definition=definition,
        services=RuntimeServices(
            tool_provider=tool_provider,
            checkpointer=checkpointer,
        ),
    )
    runtime.bind(_binding("tracking-demo-reschedule"))
    executor = await runtime.get_executor()

    first_run = [
        event
        async for event in executor.stream(
            definition.input_model()(
                message="Peux-tu reprogrammer la livraison de ce colis ?"
            ),
            ExecutionConfig(thread_id="tracking-demo-reschedule"),
        )
    ]

    awaited = cast(AwaitingHumanRuntimeEvent, first_run[-1])
    assert awaited.request.stage == "tracking_reschedule"
    assert awaited.request.choices[0].id.startswith("reschedule:")
    assert awaited.request.checkpoint_id is not None

    resumed_run = [
        event
        async for event in executor.stream(
            definition.input_model()(message="ignored-on-resume"),
            ExecutionConfig(
                thread_id="tracking-demo-reschedule",
                checkpoint_id=awaited.request.checkpoint_id,
                resume_payload={"choice_id": awaited.request.choices[0].id},
            ),
        )
    ]

    final_event = cast(FinalRuntimeEvent, resumed_run[-1])
    assert "Reprogrammation exécutée" in final_event.content
    assert "notif-001" in final_event.content
    assert [name for name, _ in tool_provider.calls[-2:]] == [
        "reschedule_delivery",
        "notify_customer",
    ]


@pytest.mark.asyncio
async def test_tracking_graph_demo_remembers_selected_parcel_across_turns() -> None:
    definition = PostalTrackingDefinition()
    tool_provider = MultiParcelTrackingDemoToolProvider()
    checkpointer = MemorySaver()
    runtime = GraphRuntime(
        definition=definition,
        services=RuntimeServices(
            tool_provider=tool_provider,
            checkpointer=checkpointer,
        ),
    )
    runtime.bind(_binding("tracking-demo-memory"))
    executor = await runtime.get_executor()

    first_pass = [
        event
        async for event in executor.stream(
            definition.input_model()(message="Bonjour, ai-je un colis en cours ?"),
            ExecutionConfig(thread_id="tracking-demo-memory"),
        )
    ]

    first_interrupt = cast(AwaitingHumanRuntimeEvent, first_pass[-1])
    assert first_interrupt.request.stage == "tracking_parcel_selection"
    assert first_interrupt.request.checkpoint_id is not None

    resumed_first_pass = [
        event
        async for event in executor.stream(
            definition.input_model()(message="ignored-on-resume"),
            ExecutionConfig(
                thread_id="tracking-demo-memory",
                checkpoint_id=first_interrupt.request.checkpoint_id,
                resume_payload={"choice_id": "track:PKG-DEMO-B"},
            ),
        )
    ]
    first_final = cast(FinalRuntimeEvent, resumed_first_pass[-1])
    assert "PKG-DEMO-B" in first_final.content

    calls_before_second_turn = len(tool_provider.calls)
    second_pass = [
        event
        async for event in executor.stream(
            definition.input_model()(
                message="J'aimerais reprogrammer une livraison stp"
            ),
            ExecutionConfig(thread_id="tracking-demo-memory"),
        )
    ]

    second_interrupt = cast(AwaitingHumanRuntimeEvent, second_pass[-1])
    assert second_interrupt.request.stage == "tracking_reschedule"
    second_turn_calls = tool_provider.calls[calls_before_second_turn:]
    assert all(name != "list_my_active_parcels" for name, _ in second_turn_calls)


@pytest.mark.asyncio
async def test_tracking_graph_demo_resume_survives_runtime_rebind() -> None:
    definition = PostalTrackingDefinition()
    tool_provider = TrackingDemoToolProvider()
    checkpointer = MemorySaver()
    runtime = GraphRuntime(
        definition=definition,
        services=RuntimeServices(
            tool_provider=tool_provider,
            checkpointer=checkpointer,
        ),
    )
    runtime.bind(_binding("tracking-demo-rebind"))
    first_executor = await runtime.get_executor()

    first_run = [
        event
        async for event in first_executor.stream(
            definition.input_model()(
                message="J'ai un colis en retard, peux-tu proposer un point relais ?"
            ),
            ExecutionConfig(thread_id="tracking-demo-rebind"),
        )
    ]

    awaiting = cast(AwaitingHumanRuntimeEvent, first_run[-1])
    assert awaiting.kind == RuntimeEventKind.AWAITING_HUMAN
    assert awaiting.request.checkpoint_id is not None

    # Simulate the cached-agent rebind that happens on the next user action.
    runtime.bind(_binding("tracking-demo-rebind"))
    resumed_executor = await runtime.get_executor()
    resumed_run = [
        event
        async for event in resumed_executor.stream(
            definition.input_model()(message="ignored-on-resume"),
            ExecutionConfig(
                thread_id="tracking-demo-rebind",
                checkpoint_id=awaiting.request.checkpoint_id,
                resume_payload={"choice_id": "reroute:PP-75015-1"},
            ),
        )
    ]

    final_event = cast(FinalRuntimeEvent, resumed_run[-1])
    assert final_event.kind == RuntimeEventKind.FINAL
    assert "PKG-DEMO-001" in final_event.content
    assert "PP-75015-1" in final_event.content


@pytest.mark.asyncio
async def test_tracking_graph_demo_resume_survives_runtime_reconstruction() -> None:
    definition = PostalTrackingDefinition()
    checkpointer = MemorySaver()
    first_runtime = GraphRuntime(
        definition=definition,
        services=RuntimeServices(
            tool_provider=TrackingDemoToolProvider(),
            checkpointer=checkpointer,
        ),
    )
    first_runtime.bind(_binding("tracking-demo-restart"))
    first_executor = await first_runtime.get_executor()

    first_run = [
        event
        async for event in first_executor.stream(
            definition.input_model()(
                message="Mon colis est en retard, peux-tu proposer un point relais ?"
            ),
            ExecutionConfig(thread_id="tracking-demo-restart"),
        )
    ]

    awaiting = cast(AwaitingHumanRuntimeEvent, first_run[-1])
    assert awaiting.request.checkpoint_id is not None

    # Simulate a new process/runtime using the same durable checkpoint backend.
    second_runtime = GraphRuntime(
        definition=definition,
        services=RuntimeServices(
            tool_provider=TrackingDemoToolProvider(),
            checkpointer=checkpointer,
        ),
    )
    second_runtime.bind(_binding("tracking-demo-restart"))
    second_executor = await second_runtime.get_executor()

    resumed_run = [
        event
        async for event in second_executor.stream(
            definition.input_model()(message="ignored-on-resume"),
            ExecutionConfig(
                thread_id="tracking-demo-restart",
                checkpoint_id=awaiting.request.checkpoint_id,
                resume_payload={"choice_id": "reroute:PP-75015-1"},
            ),
        )
    ]

    final_event = cast(FinalRuntimeEvent, resumed_run[-1])
    assert final_event.kind == RuntimeEventKind.FINAL
    assert "PKG-DEMO-001" in final_event.content


@pytest.mark.asyncio
async def test_tracking_graph_demo_resume_survives_sql_checkpointer_reconstruction(
    tmp_path,
) -> None:
    definition = PostalTrackingDefinition()
    sqlite_path = tmp_path / "tracking_graph_checkpoints.sqlite3"
    engine = create_async_engine_from_config(
        PostgresStoreConfig(sqlite_path=str(sqlite_path))
    )
    try:
        first_checkpointer = FredSqlCheckpointer(engine)
        first_runtime = GraphRuntime(
            definition=definition,
            services=RuntimeServices(
                tool_provider=TrackingDemoToolProvider(),
                checkpointer=first_checkpointer,
            ),
        )
        first_runtime.bind(_binding("tracking-demo-sql"))
        first_executor = await first_runtime.get_executor()

        first_run = [
            event
            async for event in first_executor.stream(
                definition.input_model()(
                    message="Mon colis est en retard, peux-tu proposer un point relais ?"
                ),
                ExecutionConfig(thread_id="tracking-demo-sql"),
            )
        ]

        awaiting = cast(AwaitingHumanRuntimeEvent, first_run[-1])
        assert awaiting.request.checkpoint_id is not None

        # Simulate a new runtime/process reopening the same durable SQL store.
        second_checkpointer = FredSqlCheckpointer(engine)
        second_runtime = GraphRuntime(
            definition=definition,
            services=RuntimeServices(
                tool_provider=TrackingDemoToolProvider(),
                checkpointer=second_checkpointer,
            ),
        )
        second_runtime.bind(_binding("tracking-demo-sql"))
        second_executor = await second_runtime.get_executor()

        resumed_run = [
            event
            async for event in second_executor.stream(
                definition.input_model()(message="ignored-on-resume"),
                ExecutionConfig(
                    thread_id="tracking-demo-sql",
                    checkpoint_id=awaiting.request.checkpoint_id,
                    resume_payload={"choice_id": "reroute:PP-75015-1"},
                ),
            )
        ]

        final_event = cast(FinalRuntimeEvent, resumed_run[-1])
        assert final_event.kind == RuntimeEventKind.FINAL
        assert "PKG-DEMO-001" in final_event.content
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_tracking_graph_demo_rejects_stale_checkpoint_replay() -> None:
    definition = PostalTrackingDefinition()
    checkpointer = MemorySaver()
    runtime = GraphRuntime(
        definition=definition,
        services=RuntimeServices(
            tool_provider=TrackingDemoToolProvider(),
            checkpointer=checkpointer,
        ),
    )
    runtime.bind(_binding("tracking-demo-stale"))
    executor = await runtime.get_executor()

    first_run = [
        event
        async for event in executor.stream(
            definition.input_model()(
                message="Mon colis est en retard, peux-tu proposer un point relais ?"
            ),
            ExecutionConfig(thread_id="tracking-demo-stale"),
        )
    ]
    awaiting = cast(AwaitingHumanRuntimeEvent, first_run[-1])
    checkpoint_id = awaiting.request.checkpoint_id
    assert checkpoint_id is not None

    _ = [
        event
        async for event in executor.stream(
            definition.input_model()(message="ignored-on-resume"),
            ExecutionConfig(
                thread_id="tracking-demo-stale",
                checkpoint_id=checkpoint_id,
                resume_payload={"choice_id": "reroute:PP-75015-1"},
            ),
        )
    ]

    with pytest.raises(RuntimeError, match="stale or unknown checkpoint"):
        _ = [
            event
            async for event in executor.stream(
                definition.input_model()(message="ignored-on-resume"),
                ExecutionConfig(
                    thread_id="tracking-demo-stale",
                    checkpoint_id=checkpoint_id,
                    resume_payload={"choice_id": "reroute:PP-75015-1"},
                ),
            )
        ]


@pytest.mark.asyncio
async def test_tracking_graph_demo_accepts_natural_parcel_incident_request() -> None:
    definition = PostalTrackingDefinition()
    tool_provider = TrackingDemoToolProvider()
    runtime = GraphRuntime(
        definition=definition,
        services=RuntimeServices(tool_provider=tool_provider),
    )
    runtime.bind(_binding("tracking-demo-natural"))
    executor = await runtime.get_executor()

    first_run = [
        event
        async for event in executor.stream(
            definition.input_model()(
                message="Mon colis est en retard, peux-tu m'aider et proposer une solution ?"
            ),
            ExecutionConfig(),
        )
    ]

    event_kinds = [event.kind.value for event in first_run]
    assert event_kinds[0] == RuntimeEventKind.STATUS.value
    assert RuntimeEventKind.TOOL_CALL.value in event_kinds
    assert event_kinds[-1] == RuntimeEventKind.AWAITING_HUMAN.value


@pytest.mark.asyncio
async def test_tracking_graph_demo_rejects_non_postal_request() -> None:
    definition = PostalTrackingDefinition()
    runtime = GraphRuntime(definition=definition, services=RuntimeServices())
    runtime.bind(_binding("tracking-demo-unsupported"))
    executor = await runtime.get_executor()

    events = [
        event
        async for event in executor.stream(
            definition.input_model()(message="Quelle heure est-il a Paris ?"),
            ExecutionConfig(),
        )
    ]

    assert [event.kind.value for event in events] == [RuntimeEventKind.FINAL.value]
    final_event = cast(FinalRuntimeEvent, events[-1])
    assert "Cette démo attend une question sur ton colis" in final_event.content


@pytest.mark.asyncio
async def test_tracking_graph_demo_accepts_json_string_runtime_tool_outputs() -> None:
    definition = PostalTrackingDefinition()
    tool_provider = JsonStringTrackingDemoToolProvider()
    runtime = GraphRuntime(
        definition=definition,
        services=RuntimeServices(tool_provider=tool_provider),
    )
    runtime.bind(_binding("tracking-demo-json-string"))
    executor = await runtime.get_executor()

    first_run = [
        event
        async for event in executor.stream(
            definition.input_model()(
                message="Mon colis est en retard, peux-tu proposer un point relais ?"
            ),
            ExecutionConfig(),
        )
    ]

    assert first_run[-1].kind == RuntimeEventKind.AWAITING_HUMAN
