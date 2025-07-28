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

| Attribute         | Purpose                                                              |
|------------------|----------------------------------------------------------------------|
| `name`, `role`, etc. | Metadata for display and logging                                    |
| `model`           | The language model used by the agent                                 |
| `toolkit`         | Optional LangChain tools (e.g., for querying CSVs, databases, etc.)  |
| `base_prompt`     | The initial `SystemMessage` given to the agent                       |
| `graph`           | The LangGraph flow used to process user input                        |
| `get_compiled_graph()` | Compiles and caches the flow for execution                          |

All agents must call `super().__init__()` inside their `async_init()` once the model, prompt, and graph are ready.

---

## 🧰 Toolkits and Tool Binding

Agents that use external tools (e.g., via MCP or LangChain integrations) should expose them via a `toolkit` object that extends `BaseToolkit`.

### ✅ Requirements for tool-using agents:

1. **Load the tools in `async_init()`** — typically from an external service like MCP.
2. **Bind the tools to the model** using:
   
       self.model = self.model.bind_tools(self.toolkit.get_tools())

   This ensures the model can generate tool calls correctly during reasoning.

3. **Add a `ToolNode`** to the LangGraph using:

       builder.add_node("tools", ToolNode(self.toolkit.get_tools()))

4. **Route via `tools_condition`** in your graph to allow conditional tool invocation:

       builder.add_conditional_edges("reasoner", tools_condition)

### 🔥 Common Pitfall

If you **forget to bind the tools** to the model (`bind_tools(...)`), the agent will:
- Receive the correct prompt and think it can use tools,
- But **never actually call them** — leading to incomplete or incorrect answers.

Always remember: **tool binding is not automatic**. It must be done explicitly in your agent’s `async_init()`.

### Example (excerpt from `TabularExpert`):

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

## ✅ Example: `GeneralistExpert`

This is the simplest kind of agent: no tools, just a reasoning loop.

```python
class GeneralistExpert(AgentFlow):
    name = "GeneralistExpert"
    role = "Generalist Expert"
    nickname = "Georges"
    description = "Provides guidance on a wide range of topics without deep specialization."
    icon = "generalist_agent"
    tag = "Generalist"

    def __init__(self, agent_settings: AgentSettings):
        self.agent_settings = agent_settings
        self.categories = agent_settings.categories or ["General"]
        self.model = None
        self.base_prompt = ""
        self._graph = None

    async def async_init(self):
        self.model = get_model(self.agent_settings.model)
        self.base_prompt = self._generate_prompt()
        self._graph = self._build_graph()

        super().__init__(
            name=self.name,
            role=self.role,
            nickname=self.nickname,
            description=self.description,
            icon=self.icon,
            graph=self._graph,
            base_prompt=self.base_prompt,
            categories=self.categories,
            tag=self.tag,
        )

    def _generate_prompt(self):
        return "\n".join([
            "You are a helpful generalist.",
            "You provide guidance on any topic.",
            f"The current date is {datetime.now().strftime('%Y-%m-%d')}."
        ])

    def _build_graph(self):
        builder = StateGraph(MessagesState)
        builder.add_node("expert", monitor_node(self.reasoner))
        builder.add_edge(START, "expert")
        builder.add_edge("expert", END)
        return builder

    async def reasoner(self, state: MessagesState):
        prompt = SystemMessage(content=self.base_prompt)
        response = await self.model.ainvoke([prompt] + state["messages"])
        return {"messages": [response]}
```

---

## 🧪 Testing & Reuse

- Once instantiated and `await agent.async_init()` is called, the agent is **fully ready** and can be invoked.
- Agents **can be reused across conversations** if desired, since their model and graph are pre-initialized.

---

## 🪜 Next Steps

- See `TabularExpert` for an example agent that loads tools asynchronously and uses LangGraph `ToolNode`.
- In the future, shared utilities for common node types, graph patterns, and memory behaviors will further reduce duplication.

