# wtf — Fred Worktree Tool

CLI to manage git worktrees for parallel Fred development.

## Installation

```bash
uv tool install --editable scripts/wtf
```

## Usage

```
wtf create <branch>               Create a new worktree
wtf create --from-issue <num>     Create branch name from a GitHub issue title
wtf list                          List all active worktrees
wtf remove <branch>               Remove a worktree (with optional branch deletion)
```

### Options for `create`

| Option | Description |
|---|---|
| `--from-issue <num>` | Derive branch name from GitHub issue title |
| `--provider mistral` | Configure a specific LLM provider |
| `--autorun-task <label>` | VSCode task to run automatically on folder open |

## What it does

- Creates a git worktree at `../fred-wt-<branch>/`
- Copies `.env` files from the main repo
- Allocates unique ports for all services (avoids conflicts between worktrees)
- Patches `.vscode/tasks.json` with the allocated ports
- Sets a distinct titlebar color in VSCode for easy identification
- Opens the worktree in VSCode automatically
