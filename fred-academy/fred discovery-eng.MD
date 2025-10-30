# Express Hackathon – Discovering Fred

Objective: Get hands-on with Thales’ Fred project, explore its AI agent capabilities, knowledge management features, and customize a few components.

## Prerequisites

- A machine with Docker or the ability to run services locally (see documentation).
- Access to the repository: https://github.com/ThalesGroup/fred
- Node.js and Python installed according to the “Getting Started” guide.
- Ideally, a recent web browser and internet access.

## Ressources

- Fred “Getting Started” guide: https://fredk8.dev/docs/guides/getting-started/
- Fred architecture & design paper: Fred: A Modular Multi-Agent AI Assistant for Kubernetes
- GitHub repository: https://github.com/ThalesGroup/fred
- Quick solutions/corrections will be shared as toggles under each exercise.

## Tips for Success

- Start by launching the system and familiarize yourself with the UI.
- For each exercise, note your changes and observe their effects.
- If you get stuck, move on and return later.
- Don’t forget to test your modifications (e.g., start a conversation, ask a question…).
- Ask the facilitator if you need help!

## How to Launch FRED

### Launching Fred via the Dev Container

1 - Clone the Fred repository:

```
git clone https://github.com/ThalesGroup/fred
```

2 - Verify that all required dependencies are installed:

<details>
  <summary>First, make sure you have all the requirements installed</summary>

| Tool         | Type                       | Version                                                                                             | Install hint                                                                                |
| ------------ | -------------------------- | --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Pyenv        | Python installer           | latest                                                                                              | [Pyenv installation instructions](https://github.com/pyenv/pyenv#installation)              |
| Python       | Programming language       | 3.12.8                                                                                              | Use `pyenv install 3.12.8`                                                                  |
| python3-venv | Python venv module/package | matching                                                                                            | Bundled with Python 3 on most systems; otherwise `apt install python3-venv` (Debian/Ubuntu) |
| nvm          | Node installer             | latest                                                                                              | [nvm installation instructions](https://github.com/nvm-sh/nvm#installing-and-updating)      |
| Node.js      | Programming language       | 22.13.0                                                                                             | Use `nvm install 22.13.0`                                                                   |
| Make         | Utility                    | system                                                                                              | Install via system package manager (e.g., `apt install make`, `brew install make`)          |
| yq           | Utility                    | system                                                                                              | Install via system package manager                                                          |
| SQLite       | Local RDBMS engine         | ≥ 3.35.0                                                                                            | Install via system package manager                                                          |
| Pandoc       | 2.9.2.1                    | [Pandoc installation instructions](https://pandoc.org/installing.html)                              | For DOCX document ingestion                                                                 |
| LibreOffice  | Headless doc converter     | [LibreOffice installation instructions](https://www.libreoffice.org/download/download-libreoffice/) | For PPTX conversion into PDF                                                                |

</details>

3 - Open the Dev Container in VS Code:

3.a - Open the cloned fred folder in VS Code.

3.b - Create a .fred folder in your home directory:

```
cd ~
mkdir .fred
```

3.c - Press F1, then select: Dev Containers: Build and Open in Container.

4 - Launch the three main services (use a separate terminal for each):

4.a - frontend:

```
cd frontend
make run
```

4.b - knowledge-flow:

```
cd knowledge-flow-backend
make run
```

4.c - agentic-backend

```
cd agentic-backend
make run              # or make run-academy to run the academy FRED
```

5 - Open the UI in your browser: http://localhost:5173/chat

## 🧩 Practical Exercises

### 1. Getting Started with the UI & Basic Agent

- Launch Fred in academy mode.
- Select the agent llm_responder and ask it a question.

### 2. Customize Chat with “Chat Profiles”

- Create a chat profile. Example:
"You are an Italian teacher agent. For every question I ask, respond only in Italian. Your goal is to help me learn Italian as fast as possible."
- Start a test conversation using this profile and observe how responses differ.

### 3. Customize an Agent via the UI + Fine-Tuning Settings

- Select the generalist agent Georges in the UI and ask a question.
- Modify its system prompt and note changes in its behavior.
- Start a new conversation to compare before/after behaviors.

### 4. Add a Response Template in Agent > Assets

- Add a template in the agent’s Assets Management section.
- Test and note differences in responses with and without the template.

### 5. Monitoring / Logs

- Go to Monitoring > KPIs to analyze Fred’s usage during your session.
- Go to Monitoring > Logs.
- Restart the two backends and examine their logs to understand internal backend processes.

### 6. Upload & Explore a PDF Document

- Import a Markdown or PDF document into Fred.
- Verify that associated objects are created: preview, markdown/pdf conversion, metadata objects.
- If a vector engine (e.g., ChromaDB) is configured, explore the embeddings generated.
- Ask a relevant query and check if the document appears in results.

### 7. Upload & Explore a CSV Document

- Import a CSV file into Fred.
- Verify that associated objects are created: preview, conversion, addition to the SQL database.
- Explore any tables created in the database.
- Ask a relevant query and check if the document appears in results.

### 8. Display Messages Between AI, Tools, and Humans (Debug Mode)

- Launch agentic backend in debug mode.
- Run one or two simple queries and observe the processing flow: agent → model → vector DB → response.
- Identify key points in the agent to inspect transmitted messages.
- Read messages exchanged between Fred components.

### 9. Test Another Model Provider

- Modify configuration.yaml in the agentic backend to switch between a “local” vs. “cloud” model.
- Compare results: response time, style, cost, and configuration complexity.
- Document your observations.

### 10. Explore the Knowledge-Flow API Documentation

- Launch Knowledge-Flow.
- Explore endpoints at: http://localhost:8111/knowledge-flow/v1/docs
