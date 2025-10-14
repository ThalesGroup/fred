# 🧠 Fred Agent Design Principles

This document explains how to design and implement agents in the Fred platform using `AgentFlow`. It is intended for developers extending the Fred ecosystem with new domain-specific or tool-using agents.

## ✨ Design Philosophy

Fred agents are **LangGraph-based conversational experts** that follow a few core principles:

- **Agents own their own model**: each agent manages its own `LLM` instance, configured based on its settings.
- **Graph-driven**: agents are implemented as LangGraph `StateGraph`s, describing their reasoning and tool-use logic.
- **Async-compatible**: all agents must implement `async_init()` to support loading tools, model, and graph logic.
- **Minimal boilerplate**: agent class declarations remain clean — `AgentFlow` takes care of lifecycle management, memory, and LangGraph compilation.

---

## 🧩 Key Components in `AgentFlow`

The `AgentFlow` base class defines:

| Attribute              | Purpose                                                             |
| ---------------------- | ------------------------------------------------------------------- |
| `name`, `role`, etc.   | Metadata for display and logging                                    |
| `model`                | The language model used by the agent                                |
| `toolkit`              | Optional LangChain tools (e.g., for querying CSVs, databases, etc.) |
| `base_prompt`          | The initial `SystemMessage` given to the agent                      |
| `graph`                | The LangGraph flow used to process user input                       |
| `get_compiled_graph()` | Compiles and caches the flow for execution                          |

---

## 🧰 Toolkits and Tool Binding

Agents that use external tools (e.g., via MCP or LangChain integrations) should expose them via a `toolkit` object that extends `BaseToolkit`.

### ✅ Requirements for tool-using agents:

1.  **Load the tools in `async_init()`** — typically from an external service like MCP.
2.  **Bind the tools to the model** using:

        self.model = self.model.bind_tools(self.toolkit.get_tools())

    This ensures the model can generate tool calls correctly during reasoning.

3.  **Add a `ToolNode`** to the LangGraph using:

    builder.add_node("tools", ToolNode(self.toolkit.get_tools()))

4.  **Route via `tools_condition`** in your graph to allow conditional tool invocation:

    builder.add_conditional_edges("reasoner", tools_condition)

### 🔥 Common Pitfall

If you **forget to bind the tools** to the model (`bind_tools(...)`), the agent will:

- Receive the correct prompt and think it can use tools,
- But **never actually call them** — leading to incomplete or incorrect answers.

Always remember: **tool binding is not automatic**. It must be done explicitly in your agent’s `async_init()`.

### Example (excerpt from `Tessa`):

```python
async def async_init(self):
        self.model = get_model(self.agent_settings.model)
        self.mcp_client = await get_mcp_client_for_agent(self.agent_settings)
        self.toolkit = TabularToolkit(self.mcp_client)
        self.model = self.model.bind_tools(self.toolkit.get_tools())
        self.base_prompt = self._generate_prompt()
        self._graph = self._build_graph()
```

---

## ✅ Example: `Georges`

This is the simplest kind of agent: no tools, just a reasoning loop.

```python
class Georges(AgentFlow):
    """
    Generalist Expert provides guidance on a wide range of topics
    without deep specialization.
    """

    # Class-level metadata
    name: str | None = "Georges"
    nickname: str | None = "Georges"
    role: str | None = "Fallback Generalist Expert"
    description: str | None = """Provides broad, high-level guidance when no specific expert is better suited.
        Acts as a default agent to assist with general questions across all domains."""
    icon: str = "generalist_agent"
    categories: List[str] = ["General"]
    tag: str = "generalist"

    def __init__(self, agent_settings: AgentSettings):
        super().__init__(agent_settings = agent_settings)

    async def async_init(self):
        self.model = get_model(self.agent_settings.model)
        self.base_prompt = self._generate_prompt()
        self._graph = self._build_graph()

    def _generate_prompt(self) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        return "\n".join(
            [
                "You are a friendly generalist expert, skilled at providing guidance on a wide range of topics without deep specialization.",
                "Your role is to respond with clarity, providing accurate and reliable information.",
                "When appropriate, highlight elements that could be particularly relevant.",
                f"The current date is {today}.",
                "In case of graphical representation, render mermaid diagrams code.",
            ]
        )

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(MessagesState)
        builder.add_node("expert", self.reasoner)
        builder.add_edge(START, "expert")
        builder.add_edge("expert", END)
        return builder

    async def reasoner(self, state: MessagesState):
        messages = self.use_fred_prompts(state["messages"])
        assert self.model is not None
        response = await self.model.ainvoke(messages)
        return {"messages": [response]}
```

---

## 🧪 Testing & Reuse

- Once instantiated and `await agent.async_init()` is called, the agent is **fully ready** and can be invoked.
- Agents **can be reused across conversations** if desired, since their model and graph are pre-initialized.

---

## 🪜 Next Steps

- See `Tessa` for an example agent that loads tools asynchronously and uses LangGraph `ToolNode`.
- In the future, shared utilities for common node types, graph patterns, and memory behaviors will further reduce duplication.
