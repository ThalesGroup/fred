# Agent Design Note: `Tessa`

The `Tessa` agent is a specialized LLM-driven expert in the Fred agentic platform. Its role is to help users analyze structured **tabular data** (CSV, Excel) via a tool-based interaction loop. This agent demonstrates how to integrate **external tools** (via MCP) into an agent’s reasoning cycle using `LangGraph`.

---

## 🎯 Purpose

`Tessa` is designed to:

- Access metadata about tabular datasets (via an MCP tool).
- Answer analytical questions using SQL-like queries.
- Present results clearly, with markdown tables and LaTeX math when appropriate.

It showcases:

- **Asynchronous initialization**, using `async_init()`.
- **Tool-assisted reasoning**, via LangChain and `ToolNode`.
- **Stateful execution**, using LangGraph’s `MessagesState`.
- **Agent-owned model logic**, where tools are explicitly bound via `.bind_tools(...)`.

---

## 🧩 Agent Structure

The agent is implemented as a subclass of `AgentFlow` and uses the following lifecycle:

    agent = Tessa(agent_settings)
    await agent.async_init()  # mandatory to load tools and build graph

### Key Fields

| Field        | Value              |
| ------------ | ------------------ |
| `name`       | "Tessa"            |
| `tag`        | "data"             |
| `categories` | ["tabular", "sql"] |
| `icon`       | "tabulat_agent"    |

---

## 🛠 Initialization (Async)

Tessa uses `async_init()` to:

- Load the LLM using `get_model(...)`.
- Retrieve the MCP client (typically connected to the tabular vector DB).
- Construct its `TabularToolkit` using the MCP client.
- **Bind the tools** to the model using `.bind_tools(...)`.
- Set its base prompt with date and tool usage instructions.
- Build its LangGraph using `_build_graph()`.

This split ensures agents are **fully async-ready** and can dynamically resolve remote resources before graph compilation. Tool binding is done explicitly by the agent, giving it full control over how the model interacts with its toolkit.

---

## 🔄 Graph Logic

The LangGraph is composed of two core nodes:

- `reasoner`: Handles LLM thinking and interpreting tool results.
- `tools`: A `ToolNode` from `langgraph.prebuilt` that runs MCP-backed tool invocations.

Mermaid diagram:

    graph TD
      START --> reasoner
      reasoner --> tools
      tools --> reasoner
      reasoner --> END

Routing between `reasoner` and `tools` is handled by `tools_condition`.

---

## 🧠 Reasoning Logic

    async def _run_reasoning_step(self, state: MessagesState):

This method:

- Sends the full conversation to the model, prepending the base prompt.
- Intercepts `ToolMessage` results and parses dataset metadata (via `json.loads`).
- Appends a short human-readable summary of available datasets to the model response.

Fallbacks and logging are included to ensure robustness.

---

## 📋 Prompt Design

The prompt is carefully structured to:

- Enforce **step-by-step thinking**.
- Prioritize tool invocation before answering.
- Use **LaTeX** for math and **markdown** for table output.

Agents are reminded **not to hallucinate schema or data**.

---

## ✅ Summary

| Component             | Purpose                                         |
| --------------------- | ----------------------------------------------- |
| `async_init()`        | Fetches model + tools + builds graph            |
| `.bind_tools()`       | Informs model of tool availability              |
| `_run_reasoning_step` | Invokes LLM + parses tool output                |
| `ToolNode`            | Executes actions like listing/querying datasets |
| `base_prompt`         | Guides behavior and output formatting           |

This agent design can serve as a **template** for any tool-augmented expert in Fred.

---

## 📦 Reusability Tip

Toolkits like `TabularToolkit` can be reused across agents. Just make sure to:

- Check async loading if needed.
- Bind tools explicitly using `model.bind_tools(...)` to enable tool-based reasoning.
