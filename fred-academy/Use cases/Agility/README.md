#**Agile Agent use case**

## Introduction

Welcome to this use case! The goal is to build and customize an **Agile Expert Conversational Agent** capable of interacting with documentation resources and a Jira/Confluence environment.

This guide is your roadmap to quickly setting up the technical environment based on the **Model Context Protocol (MCP)** and the Fred platform. Follow the steps below to maximize your development time.

---

## Prerequisites: What You Need

Before starting, make sure the following tools are installed on your machine. They are essential for working with the recommended **Dev Container** environment.

- **Git**
- **Docker**
- **Visual Studio Code (VS Code)**
- **VS Code Extension:** `Dev Containers`

---

# Phase 1: Installing and Launching the Infrastructure

## 1. Launching the Dev Container

We will use a **Dev Container** to isolate the server environment.

1. **Open the Project:** In VS Code, open Fred.
2. **Start the Dev Container:** Follow the prompt to reopen the project in a development container, or press `Ctrl + Shift + P` and type `Reopen in container`.

## 3. Launching the MCP Jira Server

Once inside the container, follow the specific instructions to start the Jira MCP server.  
The detailed guide for this step is available here: [README of the MCP Atlassian Server](./atlassian-mcp-server/README.md)

---

# Phase 2: Agent Configuration and Service Connection

## 1. Overview of the tools provided by the MCP Atlassian server with `MCP Inspector`

Use `MCP Inspector` to confirm that the MCP server is accessible.

1. **Launch MCP Inspector**

In the terminal (inside or outside the Dev Container), run:

```bash
npx @modelcontextprotocol/inspector@0.17.2
```

2. **Configure MCP Inspector**

Once the web UI page opens, configure the tool with the following settings (top left of the page):

- **Transport Type:** `Streamable HTTP`
- **URL:** `http://127.0.0.1:8885/mcp`
- **Connection type:** `Via Proxy`

Select **Tools** in the top bar and click **List tools**. You can then browse the list of tools and run some of them to see what they do.

> **Troubleshooting Tip (Dev Container):** If the connection fails, check the forwarded ports in VS Code. Sometimes port `6274` is mapped to another external port (e.g., `6275`). If that happens, you must use the URL displayed by the Inspector in your browser, for example: `http://localhost:6274//?MCP_PROXY_AUTH_TOKEN...`

3. **Verify that the MCP server is working**

- Go to the **tools** tab, then click on `List Tools`
- Find the tool: `jira_get_agile_boards` and click `Run Tool`

You should get a response like:

```json
[
  {
    "id": "1",
    "name": "your_sprint",
    "state": "opened"
    ...
  }
  ...
]
```

# Phase 3: Create the Agile Agent

## 1. Creating and Associating the Agent

Let's now create your Agile Agent in the **Agent Hub**.

1. In **`Agent Hub`**, click **`Create`** to instantiate a new agent.
2. Go to its **Settings**.
3. Edit its role and description to customize it.
4. Associate the two MCP servers so it can access data and Jira:
   - `mcp-atlassian-jira-server`
   - `mcp-knowledge-flow-text`
5. Finish by clicking **`APPLY CHANGES FOR ALL USERS`**.

_For reference: The configuration that makes these servers available in Agent Hub looks like this:_

```yaml
mcp:
  servers:
    - name: "mcp-knowledge-flow-text"
      transport: "streamable_http"
      url: "http://localhost:8111/knowledge-flow/v1/mcp-text"
      sse_read_timeout: 2000
      auth_mode: "user_token"
    - name: "mcp-atlassian-jira-server"
      transport: "streamable_http"
      url: "http://localhost:8885/mcp"
      sse_read_timeout: 2000
      auth_mode: "no_token"
```

## 2. Defining the Conversation Context (Agent Customization)

To ensure the agent behaves like an Agile coach, we will give it a clear profile.

1. Go to the **`Resources`** page, tab **`CONVERSATION CONTEXTS`**.
2. Create a new library named **`Agility`**.
3. Inside, create a new context with the content below:

```
You are a Senior Agile Expert and Coach Agent.

- Role: Guide the "Hackathon Laposte" team to maximize value and ensure adherence to Agile principles (Scrum, Kanban).

- Expertise (Internal Documentation): Agile management (leadership, feedback) and facilitation of effective retrospectives.

- Tools and Context:
  * Project: Hackathon Laposte for Jira with project key SCRUM.
  * Confluence: Software Development space (Key: SD) (for PI Planning, reports, retrospectives).

- Instructions/Style: Provide structured, practical, and actionable guidance.
```

You can experiment with changes to observe how your agent’s behavior adapts.

3. Associate this **Conversation Context** with your agent via the Chat page.

---

# Phase 3: Test Jira and Confluence Integration

Your agent is ready! Ask it questions and request actions to verify full integration.

## 1. Testing Jira and Confluence Integration

**Queries:**

- How many story points were completed in sprint 3, and how many are left to finish?
- Which tickets have not been started yet?
- Are the tickets in "To Do" sufficiently detailed to be worked on?

**Actions:**

- Move ticket XX to "In Progress" and comment: `"I can take this item, estimated work: 2 story points"`.

---

# # Conclusion and Next Steps

Congratulations! You have successfully followed the steps. You now have all the tools to create an Agile Coach Agent and explore Fred’s capabilities on your own.