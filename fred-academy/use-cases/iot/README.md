# **IoT Use Case**

**Technical Objectives**

- Set up an MCP server connected to a SQL database, allowing an LLM to directly query IoT data.
- Create a dynamic Fred agent capable of automatically generating SQL queries via this MCP server.
- Develop a static agent based on LangGraph, intended to orchestrate checks, business rules, and automated decisions.

# 0 - Setting up the environment

Run in a terminal:

```
git cherry-pick 87e2f2dc            # Updates to delete some Fred features
```

# 1 - Setting up PostgreSQL and connecting to knowledge-flow

## 1.1 - Launch PostgreSQL on your devcontainer

Use this docker command :

```bash
docker run -d \
  --name postgres-test \
  -e FRED_POSTGRES_PASSWORD=postgres\
  -e POSTGRES_DB=base_database\
  -p 5432:5432 \
  postgres:latest
```

<details>
<summary>Some PostgreSQL commands</summary>

Connect to the database via command line:

```bash
psql -h localhost -U postgres -W # enter password ("postgres")
```

List PostgreSQL databases:

```bash
\l
```

Use the `base_database` database:

```bash
\c base_database; # enter password ("postgres")
```

Create a table and insert a row:

```bash
CREATE TABLE my_table (
    id INTEGER PRIMARY KEY,
    name TEXT,
    value FLOAT
);

INSERT INTO my_table (id, name, value)
VALUES (1, 'Example', 12.34);
```

List tables:

```bash
\d
```

Show the newly added row in `my_table`:

```bash
SELECT * FROM my_table;
```

</details>

## 1.2 - Configure knowledge-flow backend to add PostgreSQL database

In `knowledge-flow-backend/config/configuration.yaml`, replace in the `tabular_stores` section:

```yaml
tabular_stores:
  postgres_store:
    type: "sql"
    driver: "postgresql+psycopg2"
    host: "localhost"
    port: 5432
    database: "base_database"
    username: postgres
    password: postgres
    mode: "read_and_write"
```

# 2 - Exploring FastAPI documentation

"Knowledge Flow" is Fred’s backend component dedicated to knowledge management: document ingestion, transformation, vectorization, search, etc.

It supports multiple data types: unstructured documents (PDF, Markdown), as well as structured data like CSVs and SQL databases.

The Knowledge-flow backend exposes APIs (via FastAPI) to manipulate the available documents and data.

This section aims to explore the endpoints provided by knowledge-flow’s Tabular API.

## 2.1 - Ingest example documents

To have tables available, we recommend starting Fred and adding these documents in the resources section:

- `fred-academy/discover/documents/Clients.csv`
- `fred-academy/discover/documents/Sales.csv`

## 2.2 - Exercises on knowledge-flow Tabular endpoints

FastAPI documentation available at: `http://localhost:8111/knowledge-flow/v1/docs`

Questions to explore for understanding knowledge-flow endpoints:

- Are input parameters required?
- What does it return (format and content)? How could an LLM use this?
- What happens if there’s an error in the request body?

### a - List available databases

### b - List tables for at least one database

### c - Use the context endpoint

### d - Retrieve the schema of one of your tables

### e - Try a non-existent table name

### f - Execute a simple SQL command

<details>
<summary>SQL command examples</summary>

```sql
SELECT * FROM table_name LIMIT 10;
SELECT COUNT(*) FROM table_name;
```

</details>

### g - Try an incorrect command or table name

### h - Add an extra column in your database using the `write_query` endpoint

Idea: create a `big_sale` column if `amount` > 250.

<details>
<summary>PostgreSQL example to add a column</summary>

```sql
ALTER TABLE sales ADD COLUMN new_column new_column_type; UPDATE sales SET new_column = value WHERE condition;
```

</details>

### i - Try creating the same column using `read_query`

### j - Create an additional table

<details>
<summary>SQL example</summary>

```sql
CREATE TABLE new_table (
    id INTEGER PRIMARY KEY,
    name TEXT,
    value FLOAT
);
```

</details>

### k - Drop the table created above

# 3 - Expose FastAPI endpoints in MCP with FastAPI-MCP

## 3.1 - Identify how other endpoints are exposed via FastAPI-MCP

### 3.1.a - Identify where Tabular API endpoints are created

Each service type is split into two parts:

- A service instantiating the logic behind the controller
- A controller exposing different commands (GET, UPDATE, DELETE) defined in the service

<details>
<summary>Hint</summary>
Search in the knowledge-flow backend.
</details>

### 3.1.a - Identify where and how these endpoints are exposed

<details>
<summary>Hint</summary>
Usually, FastAPI exposes backend endpoints in its `main.py`.
</details>

### 3.1.a - Check how other services are exposed in MCP

Study how the MCP server is created: `mcp-statistic`.

<details>
<summary>Hint</summary>
Search the entire current folder in VS Code (`ctrl+shift+f`): <code>mcp-statistic</code>
</details>

## 3.2 - Add the code to create the MCP server: **mcp-tabular**

<details>
<summary>Hint</summary>
The tag for tabular endpoints is: `"Tabular"`.
</details>

## 3.3 (OPTIONAL) - Verify MCP server with MCP-Inspector

# 4 - Use the previously created MCP server with a dynamic agent from the UI

Fred allows creating MCP agents from the UI. We will use this to test the previously created MCP server.

## 4.1 - Add MCP server to configuration

In `agentic-backend/config/configuration.yaml`, add to the `servers` section:

```
servers:
    - name: "mcp-knowledge-flow-mcp-tabular"
      transport: "streamable_http"
      url: "http://localhost:8111/knowledge-flow/v1/mcp-tabular"
      sse_read_timeout: 2000
      auth_mode: "user_token"
```

## 4.2 - Create an MCP agent from the UI

- Go to the **Agents** page and click **Create**.
- Fill in the fields, remembering to add the MCP server created.

<details>
<summary>Hint</summary>
Don’t forget to enable the agent after creation.
</details>

## 4.3 - Test endpoints from section 2.2 with the created agent

- Can it use all the endpoints?
- Are all endpoints necessary?
- What improvements can be made?

# 5 - Create a static agent in agentic-backend from a template

We use LangGraph to build our agents.

LangGraph is an open-source framework built on LangChain that allows creating agents and AI workflows as structured graphs. It facilitates defining states, transitions, and loops to precisely control an agent’s behavior. Its deterministic architecture improves reliability and traceability of LLM-based systems. It is particularly suited for applications requiring complex interactions.

Tip: work step by step: first a functional agent, then one using MCP, then iterate to improve.

## 5.1 - Explore the implementation of the Statistic agent

### 5.1.a - Analyze Sage agent code

Go to: `agentic-backend/agentic_backend/agents/statistics/statistics_expert.py`

- Which parameters are configurable?
- How is the graph defined? How is the graph linked to MCP tools?

### 5.1.b - Configure the agent

Explore references to Sage in: `agentic-backend/config/configuration_academy.yaml`

Note: This file allows launching Fred in "academy" mode with demo agents exposing other capabilities and MCP servers.

## 5.2 - Adapt the Sage agent to create a new agent with the MCP server

### 5.2.a - Copy Sage agent code

- Copy `statistics_expert.py` to a new `tabular` folder: `agentic-backend/agentic_backend/agents/tabular/`
- Rename it `tabular_expert.py`

### 5.2.b - Modify code to create an agent querying the MCP server

First iteration: modify `STATISTIC_TUNING`, model name, and Sage class name to quickly obtain a functional agent sharing the same graph but using a different system prompt and MCP server.

### 5.2.c - Add the created agent to your configuration file

To add a static agent in Fred: in `agentic-backend/config/configuration.yaml`, add to `agents` section:

```yaml
agents:
  - id: "toto"
    name: "Toto"
    type: "agent"
    class_path: "agentic_backend.agents.agent_folder.python_filename.agent_class_name"
    enabled: true
```

## 5.3 - Test this agent with questions from section 2.2
