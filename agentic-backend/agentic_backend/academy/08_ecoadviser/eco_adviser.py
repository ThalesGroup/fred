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
EcoAdvisor — Agent Fred orienté écologie / mobilité bas carbone.

Fred rationale:
- Cet agent est volontairement simple et pédagogique.
- Il réutilise le même pattern que Tessa:
  - un noeud LLM "reasoner"
  - un noeud "tools" fourni par l'infrastructure MCP
- La différence n'est PAS dans la structure du graphe,
  mais dans:
  - le prompt système (orienté CO₂ / mobilité)
  - la façon dont on guide l'utilisation des outils tabulaires.
- Objectif v1: avoir un agent complet et stable pour la démo,
  quitte à séparer plus tard un noeud compute_co2 dédié.
"""

import asyncio
import csv
import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.constants import START
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import tools_condition
from pydantic import BaseModel, Field, PrivateAttr

from agentic_backend.application_context import get_default_chat_model
from agentic_backend.common.mcp_runtime import MCPRuntime
from agentic_backend.common.structures import AgentSettings
from agentic_backend.common.tool_node_utils import create_mcp_tool_node
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import (
    AgentTuning,
    FieldSpec,
    MCPServerRef,
    UIHints,
)
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Local CSV → SQLite dataset + LangChain tool wrappers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DemoCSVSpec:
    table_name: str
    file_name: str
    description: str = ""


class LocalTabularDataset:
    """Loads the academy CSV files into a lightweight SQLite database."""

    def __init__(
        self,
        dataset_name: str,
        csv_specs: List[DemoCSVSpec],
        data_dir: Optional[Path] = None,
        db_root: Optional[Path] = None,
    ):
        self.dataset_name = dataset_name
        self.csv_specs = csv_specs
        self.data_dir = data_dir or Path(__file__).parent
        self.db_root = db_root or (Path.home() / ".fred" / "academy" / "eco_adviser")
        self.db_path = self.db_root / f"{dataset_name}.sqlite"
        self._schemas: Dict[str, List[str]] = {}
        self._row_counts: Dict[str, int] = {}
        self.ready = False

    # -------------------------- bootstrap helpers ---------------------------

    def _sanitize_headers(self, headers: List[str]) -> List[str]:
        seen: Dict[str, int] = {}
        result: List[str] = []
        for header in headers:
            candidate = (
                header.strip()
                .lower()
                .replace(" ", "_")
                .replace("-", "_")
                .replace("/", "_")
            )
            candidate = "".join(ch for ch in candidate if ch.isalnum() or ch == "_")
            if not candidate:
                candidate = "col"
            if candidate in seen:
                seen[candidate] += 1
                candidate = f"{candidate}_{seen[candidate]}"
            else:
                seen[candidate] = 0
            result.append(candidate)
        return result

    def _detect_delimiter(self, file_path: Path) -> str:
        try:
            sample = file_path.read_text(encoding="utf-8", errors="ignore")[:4096]
            if not sample:
                return ","
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            return dialect.delimiter
        except Exception:
            logger.warning(
                "EcoAdvisor: delimiter detection failed for %s, defaulting to comma.",
                file_path,
            )
            return ","

    def _load_csv_into_sqlite(self, conn: sqlite3.Connection, spec: DemoCSVSpec) -> None:
        csv_path = self.data_dir / spec.file_name
        if not csv_path.exists():
            raise FileNotFoundError(
                f"Missing CSV dataset: {csv_path} (expected for table '{spec.table_name}')"
            )

        delimiter = self._detect_delimiter(csv_path)
        table_name = spec.table_name

        with open(csv_path, "r", encoding="utf-8", errors="ignore", newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter)
            try:
                raw_headers = next(reader)
            except StopIteration as exc:  # pragma: no cover - defensive
                raise ValueError(f"CSV file {csv_path} is empty.") from exc

            headers = self._sanitize_headers(raw_headers)
            columns_def = ", ".join(f'"{col}" TEXT' for col in headers)
            column_names = ", ".join(f'"{col}"' for col in headers)
            placeholders = ", ".join("?" for _ in headers)
            insert_sql = f'INSERT INTO "{table_name}" ({column_names}) VALUES ({placeholders})'

            conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
            conn.execute(f'CREATE TABLE "{table_name}" ({columns_def})')

            batch: List[tuple[str, ...]] = []
            total_rows = 0
            for row in reader:
                if not row:
                    continue
                if len(row) < len(headers):
                    row.extend([""] * (len(headers) - len(row)))
                elif len(row) > len(headers):
                    row = row[: len(headers)]
                batch.append(tuple(row))
                if len(batch) >= 500:
                    conn.executemany(insert_sql, batch)
                    total_rows += len(batch)
                    batch.clear()

            if batch:
                conn.executemany(insert_sql, batch)
                total_rows += len(batch)

        self._schemas[table_name] = list(headers)
        self._row_counts[table_name] = total_rows

    def bootstrap(self) -> bool:
        """Converts all CSVs to tables stored in a dedicated SQLite file."""
        self._schemas.clear()
        self._row_counts.clear()
        try:
            self.db_root.mkdir(parents=True, exist_ok=True)
            if self.db_path.exists():
                self.db_path.unlink()

            with sqlite3.connect(self.db_path) as conn:
                for spec in self.csv_specs:
                    self._load_csv_into_sqlite(conn, spec)
            self.ready = True
            logger.info(
                "EcoAdvisor local dataset ready at %s with tables %s",
                self.db_path,
                list(self._schemas.keys()),
            )
            return True
        except Exception:
            logger.exception("EcoAdvisor failed to transform CSV files into SQLite.")
            self.ready = False
            return False

    # ------------------------------- metadata -------------------------------

    def list_tables(self) -> List[str]:
        if not self.ready:
            return []
        return [spec.table_name for spec in self.csv_specs if spec.table_name in self._schemas]

    def describe_table(self, table_name: str) -> Dict[str, Any]:
        if not self.ready:
            raise RuntimeError("Local dataset not available. Check CSV files and permissions.")
        table = table_name.strip()
        if table not in self._schemas:
            raise ValueError(f"Unknown table '{table}'. Available: {self.list_tables()}")
        return {
            "database": self.dataset_name,
            "table": table,
            "columns": self._schemas[table],
            "row_count": self._row_counts.get(table, 0),
        }

    def describe_all_tables(self) -> List[Dict[str, Any]]:
        if not self.ready:
            raise RuntimeError("Local dataset not available. Check CSV files and permissions.")
        descriptions: List[Dict[str, Any]] = []
        for table in self.list_tables():
            payload = self.describe_table(table)
            descriptions.append(
                {
                    **payload,
                    "description": next(
                        (spec.description for spec in self.csv_specs if spec.table_name == table),
                        "",
                    ),
                }
            )
        return descriptions

    def get_context_entry(self) -> Optional[Dict[str, Any]]:
        if not self.ready:
            return None
        return {
            "database": self.dataset_name,
            "tables": self.list_tables(),
            "source": "local_csv_demo",
        }

    # -------------------------------- queries -------------------------------

    def run_query(self, sql: str, limit: int = 50) -> Dict[str, Any]:
        if not self.ready:
            raise RuntimeError("Local dataset not available. Check CSV files and permissions.")
        cleaned_sql = sql.strip()
        if not cleaned_sql.lower().startswith("select"):
            raise ValueError("Only SELECT statements are allowed on the demo database.")
        limit = max(1, min(limit, 200))
        wrapped_query = cleaned_sql
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(wrapped_query)
                raw_rows = cursor.fetchmany(limit + 1)
                columns = [meta[0] for meta in cursor.description or []]
                truncated = len(raw_rows) > limit
                rows = raw_rows[:limit]
            return {
                "database": self.dataset_name,
                "query": cleaned_sql,
                "columns": columns,
                "rows": [dict(row) for row in rows],
                "row_count": len(rows),
                "truncated": truncated,
            }
        except sqlite3.Error as exc:
            raise ValueError(f"SQLite error: {exc}") from exc


class _ListTablesArgs(BaseModel):
    refresh: bool = Field(
        default=False,
        description="Set to true to rebuild the SQLite database from the CSV files before listing tables.",
    )


class _DescribeTableArgs(BaseModel):
    table_name: str = Field(..., description="Name of the table to describe (e.g. 'bike_infra_demo').")


class _SQLQueryArgs(BaseModel):
    sql: str = Field(..., description="SELECT statement to run against the local EcoAdvisor demo dataset.")
    limit: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of rows returned from the local database (default 50, max 200).",
    )


class LocalListTablesTool(BaseTool):
    name: str = "eco_demo_list_tables"
    description: str = (
        "List the locally bundled EcoAdvisor tables converted from CSV files. "
        "Returns column names, row counts, and a short description for each table."
    )
    args_schema: type[BaseModel] = _ListTablesArgs
    _dataset: LocalTabularDataset = PrivateAttr()

    def __init__(self, dataset: LocalTabularDataset):
        super().__init__()
        self._dataset = dataset

    def _run(self, refresh: bool = False) -> str:
        if refresh:
            self._dataset.bootstrap()
        try:
            payload = self._dataset.describe_all_tables()
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})
        return json.dumps(payload, ensure_ascii=False)

    async def _arun(self, refresh: bool = False) -> str:
        return await asyncio.to_thread(self._run, refresh)


class LocalDescribeTableTool(BaseTool):
    name: str = "eco_demo_describe_table"
    description: str = (
        "Return schema information (columns, row count) for a single local EcoAdvisor table. "
        "Use this before writing SQL queries."
    )
    args_schema: type[BaseModel] = _DescribeTableArgs
    _dataset: LocalTabularDataset = PrivateAttr()

    def __init__(self, dataset: LocalTabularDataset):
        super().__init__()
        self._dataset = dataset

    def _run(self, table_name: str) -> str:
        try:
            payload = self._dataset.describe_table(table_name)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})
        return json.dumps(payload, ensure_ascii=False)

    async def _arun(self, table_name: str) -> str:
        return await asyncio.to_thread(self._run, table_name)


class LocalSQLQueryTool(BaseTool):
    name: str = "eco_demo_sql_query"
    description: str = (
        "Execute a read-only SQL SELECT query against the EcoAdvisor local SQLite database. "
        "Only SELECT statements are allowed."
    )
    args_schema: type[BaseModel] = _SQLQueryArgs
    _dataset: LocalTabularDataset = PrivateAttr()

    def __init__(self, dataset: LocalTabularDataset):
        super().__init__()
        self._dataset = dataset

    def _run(self, sql: str, limit: int = 50) -> str:
        try:
            payload = self._dataset.run_query(sql, limit=limit)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc), "sql": sql})
        return json.dumps(payload, ensure_ascii=False)

    async def _arun(self, sql: str, limit: int = 50) -> str:
        return await asyncio.to_thread(self._run, sql, limit)


# ---------------------------------------------------------------------------
# 1) Tuning: ce que l'UI peut éditer
# ---------------------------------------------------------------------------

ECO_TUNING = AgentTuning(
    role="Eco Mobility Advisor",
    description=(
        "Helps users understand and reduce the CO₂ impact of their daily trips, "
        "using structured mobility datasets (bike lanes, public transport stops, etc.)."
    ),
    tags=["eco", "mobility", "co2", "data"],
    fields=[
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System Prompt",
            description=(
                "EcoAdvisor's operating instructions: guide the user to describe "
                "their trip, query tabular mobility datasets (CSV/Excel via MCP), "
                "estimate CO₂ impact and propose low-carbon alternatives."
            ),
            required=True,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
            default=(
                "You are **EcoAdvisor**, a mobility and CO₂ impact assistant.\n\n"
                "Your mission is to help users understand and reduce the carbon footprint "
                "of their daily trips (home ↔ work, regular commutes, etc.).\n\n"
                "### Data & Tools\n"
                "- You can access structured tabular datasets (CSV/Excel) via tools.\n"
                "- Typical datasets include:\n"
                "  - bike_infra_demo: bike lanes and infrastructure in the Rhône / Lyon area\n"
                "  - tcl_stops_demo: public transport stops (TCL) with coordinates and served lines\n"
                "- First, **list the available datasets and their schema** using the tools.\n"
                "- Then, select the relevant tables and run queries to inspect nearby bike lanes\n"
                "  and public transport options.\n\n"
                "### CO₂ Estimates (simplified factors)\n"
                "When you need to estimate CO₂ emissions, you can use the following factors:\n"
                "- Car (thermal): 0.192 kg CO₂ per km\n"
                "- Public transport (average): 0.01 kg CO₂ per km\n"
                "- Bike / walking: 0 kg CO₂ per km\n"
                "These are simplified emission factors inspired by ADEME data, for demo purposes.\n\n"
                "### Workflow\n"
                "1. Clarify the user's context:\n"
                "   - origin and destination (city or district is enough)\n"
                "   - main current mode of transport (car, bike, TCL, etc.)\n"
                "   - approximate one-way distance or time if available\n"
                "   - frequency (e.g., 5 days/week)\n"
                "2. Use tools to **list datasets and their schema**.\n"
                "3. Identify which tables are relevant (e.g., bike_infra_demo, tcl_stops_demo).\n"
                "4. Run SQL-like queries to:\n"
                "   - find long bike lanes near the origin/destination city\n"
                "   - find TCL stops in the same city or within a geographic area\n"
                "5. Based on distance and mode, estimate weekly CO₂ emissions using the factors above.\n"
                "6. Compare current mode vs alternatives (TCL, bike, walking if realistic).\n"
                "7. Produce a clear, concise **markdown summary** with:\n"
                "   - a short explanation in natural language\n"
                "   - a markdown table comparing modes and weekly CO₂\n"
                "   - explicit assumptions you made (distance, days/week, factors)\n\n"
                "### Rules\n"
                "- ALWAYS base your conclusions on actual tool results when referring to datasets.\n"
                "- NEVER invent columns or tables that do not exist in the schema.\n"
                "- Use markdown tables to present numeric comparisons.\n"
                "- If the user did not provide enough information (distance, frequency),\n"
                "  ask targeted follow-up questions before estimating CO₂.\n"
                "- If you are unsure about a detail, state your assumptions explicitly.\n\n"
                "Current date: {today}.\n\n"
            ),
        ),
    ],
    mcp_servers=[
        MCPServerRef(name="mcp-knowledge-flow-mcp-tabular"),
    ],
)


class EcoState(TypedDict):
    """State LangGraph pour EcoAdvisor."""

    messages: Annotated[list[AnyMessage], add_messages]
    database_context: List[Dict[str, Any]]


@expose_runtime_source("agent.EcoAdvisor")
class EcoAdvisor(AgentFlow):
    """EcoAdvisor — Agent Fred spécialisé mobilité / CO₂, basé sur le pattern Tessa."""

    tuning = ECO_TUNING

    def __init__(self, agent_settings: AgentSettings):
        super().__init__(agent_settings=agent_settings)
        self.mcp = MCPRuntime(agent=self)
        self.local_dataset: Optional[LocalTabularDataset] = None
        self._local_demo_tools: List[BaseTool] = []
        self._local_db_context: Optional[Dict[str, Any]] = None
        self._tool_node = None

    # -----------------------------------------------------------------------
    # Bootstrap: modèle + MCP + graphe
    # -----------------------------------------------------------------------
    async def async_init(self, runtime_context: RuntimeContext):
        await super().async_init(runtime_context)
        self.model = get_default_chat_model()

        await self.mcp.init()

        await self._bootstrap_local_demo_dataset()

        tool_list = list(self.mcp.get_tools())
        if self._local_demo_tools:
            tool_list.extend(self._local_demo_tools)

        if tool_list:
            self.model = self.model.bind_tools(tool_list)
            self._tool_node = create_mcp_tool_node(tool_list)
        else:
            self._tool_node = self.mcp.get_tool_nodes()

        self._graph = self._build_graph()

    async def aclose(self):
        await self.mcp.aclose()

    # -----------------------------------------------------------------------
    # Helpers MCP / contexte tabulaire
    # -----------------------------------------------------------------------

    async def _bootstrap_local_demo_dataset(self) -> None:
        """Charge les CSV académiques dans une base SQLite locale."""

        csv_specs = [
            DemoCSVSpec(
                table_name="bike_infra_demo",
                file_name="bike_infra_demo.csv",
                description="Bike lanes and cycling infrastructure for the Lyon metro area.",
            ),
            DemoCSVSpec(
                table_name="tcl_stops_demo",
                file_name="tcl_stops_demo.csv",
                description="Public transport stops (TCL) with served lines and coordinates.",
            ),
        ]

        dataset = LocalTabularDataset(
            dataset_name="eco_local_mobility",
            csv_specs=csv_specs,
            data_dir=Path(__file__).parent,
        )

        try:
            success = await asyncio.to_thread(dataset.bootstrap)
        except Exception:
            logger.exception(
                "EcoAdvisor: unexpected error while preparing the local CSV dataset. "
                "Continuing with MCP tools only."
            )
            success = False

        if not success:
            logger.warning(
                "EcoAdvisor: local CSV files could not be converted to SQLite. Tools will rely on MCP only."
            )
            self.local_dataset = None
            self._local_demo_tools = []
            self._local_db_context = None
            return

        self.local_dataset = dataset
        self._local_db_context = dataset.get_context_entry()
        self._local_demo_tools = [
            LocalListTablesTool(dataset),
            LocalDescribeTableTool(dataset),
            LocalSQLQueryTool(dataset),
        ]

    def _maybe_parse_json(self, payload: Any) -> Any:
        if isinstance(payload, str):
            try:
                return json.loads(payload)
            except Exception:  # noqa: BLE001
                return payload
        return payload

    def _latest_tool_output(self, state: EcoState, tool_name: str) -> Any:
        for msg in reversed(state["messages"]):
            if isinstance(msg, ToolMessage) and getattr(msg, "name", "") == tool_name:
                return self._maybe_parse_json(msg.content)
        return None

    def _format_context_for_prompt(self, database_context: List[Dict[str, Any]]) -> str:
        if not database_context:
            return "No databases or tables currently loaded.\n"

        lines = ["You currently have access to the following structured datasets:\n"]
        for entry in database_context:
            entry = self._maybe_parse_json(entry)
            db = entry.get("database", "unknown_database")
            tables = entry.get("tables", [])
            lines.append(f"- Database: `{db}` with tables: {tables}")
        return "\n".join(lines) + "\n\n"

    def _merge_local_context(self, context: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        base: List[Dict[str, Any]] = list(context or [])
        if self._local_db_context:
            local_db_name = self._local_db_context.get("database")
            already_present = any(entry.get("database") == local_db_name for entry in base)
            if not already_present:
                base.append(self._local_db_context)
        return base

    async def _fetch_remote_database_context(self) -> List[Dict[str, Any]]:
        logger.info("EcoAdvisor: fetching database context via MCP (get_context)...")
        try:
            tools = self.mcp.get_tools()
            tool = next((t for t in tools if t.name == "get_context"), None)
            if not tool:
                logger.warning(
                    "EcoAdvisor: unable to find tool 'get_context' in MCP server."
                )
                return []

            raw_context = await tool.ainvoke({})
            return json.loads(raw_context) if isinstance(raw_context, str) else raw_context

        except Exception as e:  # noqa: BLE001
            logger.warning(f"EcoAdvisor: could not load database context: {e}")
            return []

    async def _ensure_database_context(self, state: EcoState) -> List[Dict[str, Any]]:
        context = state.get("database_context")
        if not context:
            context = await self._fetch_remote_database_context()

        merged = self._merge_local_context(context)
        state["database_context"] = merged
        return merged

    # -----------------------------------------------------------------------
    # 2) Construction du graphe LangGraph
    # -----------------------------------------------------------------------
    def _build_graph(self) -> StateGraph:
        builder = StateGraph(EcoState)

        builder.add_node("reasoner", self.reasoner)
        tool_node = self._tool_node or self.mcp.get_tool_nodes()
        builder.add_node("tools", tool_node)

        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges("reasoner", tools_condition)
        builder.add_edge("tools", "reasoner")

        return builder

    # -----------------------------------------------------------------------
    # 3) Noeud LLM principal
    # -----------------------------------------------------------------------
    async def reasoner(self, state: EcoState):
        if self.model is None:
            raise RuntimeError(
                "EcoAdvisor: model is not initialized. Call async_init() first."
            )

        tpl = self.get_tuned_text("prompts.system") or ""

        database_context = await self._ensure_database_context(state)
        tpl += self._format_context_for_prompt(database_context)
        system_text = self.render(tpl)

        recent_history = self.recent_messages(state["messages"], max_messages=5)
        messages = self.with_system(system_text, recent_history)
        messages = self.with_chat_context_text(messages)

        try:
            response = await self.model.ainvoke(messages)

            tool_payloads: Dict[str, Any] = {}
            for msg in state["messages"]:
                if isinstance(msg, ToolMessage) and getattr(msg, "name", ""):
                    raw = msg.content
                    try:
                        normalized = json.loads(raw) if isinstance(raw, str) else raw
                    except Exception:  # noqa: BLE001
                        normalized = raw
                    tool_payloads[msg.name or "unknown_tool"] = normalized

            md = getattr(response, "response_metadata", {}) or {}
            tools_md = md.get("tools", {}) or {}
            tools_md.update(tool_payloads)
            md["tools"] = tools_md
            response.response_metadata = md

            return {
                "messages": [response],
                "database_context": database_context,
            }

        except Exception:  # noqa: BLE001
            logger.exception("EcoAdvisor failed during reasoning.")
            fallback = await self.model.ainvoke(
                [
                    HumanMessage(
                        content=(
                            "An error occurred while analyzing mobility data. "
                            "Please try again or simplify your question."
                        )
                    )
                ]
            )
            return {
                "messages": [fallback],
                "database_context": [],
            }
