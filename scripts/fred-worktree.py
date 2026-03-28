#!/usr/bin/env -S uv run --script
#
# /// script
# requires-python = ">=3.12"
# dependencies = ["click"]
# ///
#
# fred-worktree - Manage git worktrees for parallel Fred development
#
# Usage:
#   fred-worktree create <branch> [--from-issue <num>] [--fresh]
#   fred-worktree remove <branch>
#   fred-worktree list

from __future__ import annotations

import json
import os
import random
import re
import shutil
import socket
import subprocess
import textwrap
from pathlib import Path

import click
from click.shell_completion import CompletionItem

# ── Configuration ────────────────────────────────────────────────────────────

FRED_ROOT = Path("/home/fmuller/Documents/fred-universe/fred")
WORKTREE_BASE = Path("/home/fmuller/Documents/fred-universe")
PORT_RANGE = (9300, 9999)

PYTHON_SERVICES = ["agentic-backend", "knowledge-flow-backend", "control-plane-backend"]
ALL_SERVICES = [*PYTHON_SERVICES, "frontend"]

DEFAULT_PORTS = {
    "agentic-backend": 8000,
    "knowledge-flow-backend": 8111,
    "control-plane-backend": 8222,
    "frontend": 5173,
}

# Distinct titlebar colors for worktree identification
TITLEBAR_COLORS = [
    "#6A1B9A",  # purple
    "#00838F",  # teal
    "#DF8C60",  # orange
    "#2E7D32",  # green
    "#AD1457",  # pink
    "#1565C0",  # blue
    "#F9A825",  # yellow
    "#4E342E",  # brown
]


# ── Helpers ──────────────────────────────────────────────────────────────────


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command, raising on failure."""
    return subprocess.run(cmd, check=True, **kwargs)


def run_quiet(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command silently."""
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kwargs)


def worktree_dir(branch: str) -> Path:
    return WORKTREE_BASE / f"fred-wt-{branch}"


def existing_worktree_dirs() -> list[Path]:
    return sorted(p for p in WORKTREE_BASE.iterdir() if p.is_dir() and p.name.startswith("fred-wt-"))


def find_free_port(used: set[int]) -> int:
    """Find a port that is both unused by the OS and not claimed by other worktrees."""
    # Collect ports already claimed in other worktrees' PORTS.md
    for wt in existing_worktree_dirs():
        ports_file = wt / "PORTS.md"
        if ports_file.exists():
            for match in re.findall(r"localhost:(\d+)", ports_file.read_text()):
                used.add(int(match))

    for _ in range(200):
        port = random.randint(*PORT_RANGE)
        if port in used:
            continue
        # Check if the port is actually free on the OS
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                used.add(port)
                return port
            except OSError:
                continue

    raise click.ClickException(f"Could not find a free port in range {PORT_RANGE}")


def pick_color() -> str:
    idx = len(existing_worktree_dirs())
    return TITLEBAR_COLORS[idx % len(TITLEBAR_COLORS)]


def complete_worktree_branch(ctx, param, incomplete: str) -> list[CompletionItem]:
    """Autocomplete existing worktree branch names."""
    return [
        CompletionItem(d.name.removeprefix("fred-wt-"))
        for d in existing_worktree_dirs()
        if d.name.removeprefix("fred-wt-").startswith(incomplete)
    ]


def slugify_issue(issue_num: str) -> str:
    """Fetch a GitHub issue title and create a branch-name slug."""
    result = run_quiet(["gh", "issue", "view", issue_num, "--json", "title", "-q", ".title"])
    title = result.stdout.strip()
    slug = re.sub(r"[^a-z0-9]+", "-", f"{issue_num}-{title}".lower()).strip("-")[:60]
    return slug


# ── VSCode config generators ────────────────────────────────────────────────


def color_customizations(color: str) -> dict:
    return {
        "workbench.colorCustomizations": {
            "titleBar.activeBackground": color,
            "titleBar.activeForeground": "#FFFFFF",
            "titleBar.inactiveBackground": f"{color}CC",
            "titleBar.inactiveForeground": "#FFFFFFAA",
            "statusBar.background": color,
            "statusBar.foreground": "#FFFFFF",
        }
    }


def patch_workspace_file(wt: Path, color: str) -> None:
    """Inject color customizations into the .code-workspace settings block."""
    workspace_file = wt / ".vscode" / "fred.code-workspace"
    if not workspace_file.exists():
        raise click.ClickException(f"Workspace file not found: {workspace_file}")

    # Strip trailing commas so standard json can parse it
    content = workspace_file.read_text()
    clean = re.sub(r",\s*([}\]])", r"\1", content)
    workspace = json.loads(clean)

    workspace.setdefault("settings", {}).update(color_customizations(color))
    workspace_file.write_text(json.dumps(workspace, indent="\t") + "\n")


def patch_vscode_tasks(wt: Path, ports: dict[str, int], autorun_task: str | None = None) -> None:
    """Patch the existing .vscode/tasks.json: replace default ports with worktree ports,
    inject VITE_PORT for the frontend task, and optionally mark a task to run on folder open."""
    tasks_file = wt / ".vscode" / "tasks.json"
    if not tasks_file.exists():
        raise click.ClickException(f"tasks.json not found at {tasks_file}")

    tasks = json.loads(tasks_file.read_text())

    # Port replacement map: default port -> worktree port
    port_map = {str(DEFAULT_PORTS[svc]): str(ports[svc]) for svc in ALL_SERVICES}

    def replace_ports(s: str) -> str:
        for old, new in port_map.items():
            s = s.replace(f":{old}", f":{new}")
            s = s.replace(f"PORT={old}", f"PORT={new}")
        return s

    matched_autorun = False
    for task in tasks.get("tasks", []):
        # Replace ports in args
        if "args" in task:
            task["args"] = [replace_ports(a) for a in task["args"]]
            # Inject env vars for frontend tasks: VITE_PORT + backend URLs for the Vite proxy
            for i, arg in enumerate(task["args"]):
                if "make run" in arg and "frontend" in task.get("label", "").lower():
                    if "VITE_PORT" not in arg:
                        frontend_env = (
                            f"VITE_PORT={ports['frontend']} "
                            f"VITE_BACKEND_URL=http://localhost:{ports['agentic-backend']} "
                            f"VITE_BACKEND_URL_KNOWLEDGE=http://localhost:{ports['knowledge-flow-backend']} "
                            f"VITE_BACKEND_URL_CONTROL_PLANE=http://localhost:{ports['control-plane-backend']}"
                        )
                        task["args"][i] = arg.replace("make run", f"{frontend_env} make run")

        # Replace ports in command string
        if "command" in task and isinstance(task["command"], str):
            task["command"] = replace_ports(task["command"])

        # Mark task to run automatically on folder open
        if autorun_task and task.get("label") == autorun_task:
            task["runOptions"] = {"runOn": "folderOpen"}
            matched_autorun = True

    if autorun_task and not matched_autorun:
        raise click.ClickException(f"Task '{autorun_task}' not found in tasks.json")

    tasks_file.write_text(json.dumps(tasks, indent=2) + "\n")


def generate_ports_md(branch: str, ports: dict[str, int]) -> str:
    return textwrap.dedent(f"""\
        # Worktree: {branch}

        | Service                 | Port  | URL                                                          |
        |-------------------------|-------|--------------------------------------------------------------|
        | Agentic Backend         | {ports["agentic-backend"]} | http://localhost:{ports["agentic-backend"]}/agentic/v1/docs             |
        | Knowledge Flow Backend  | {ports["knowledge-flow-backend"]} | http://localhost:{ports["knowledge-flow-backend"]}/knowledge-flow/v1/docs       |
        | Control Plane Backend   | {ports["control-plane-backend"]} | http://localhost:{ports["control-plane-backend"]}/control-plane/v1/docs         |
        | Frontend                | {ports["frontend"]} | http://localhost:{ports["frontend"]}                                     |
    """)


# ── Commands ─────────────────────────────────────────────────────────────────


@click.group()
def cli():
    """Manage git worktrees for parallel Fred development."""


PROVIDER_MAKE_TARGETS: dict[str, str] = {
    "mistral": "use-mistral",
}


@cli.command()
@click.argument("branch", required=False)
@click.option("--from-issue", type=str, help="Create branch name from a GitHub issue number")
@click.option(
    "--provider",
    type=click.Choice(list(PROVIDER_MAKE_TARGETS), case_sensitive=False),
    default=None,
    help="Configure a specific LLM provider in the worktree (e.g. mistral)",
)
@click.option(
    "--autorun-task",
    type=str,
    default=None,
    help="VSCode task label to run automatically when the worktree folder is opened (e.g. 'All Services PROD')",
)
def create(branch: str | None, from_issue: str | None, provider: str | None, autorun_task: str | None):
    """Create a new worktree with full dev environment."""
    # Resolve branch name
    if from_issue and not branch:
        click.echo(f":: Fetching issue #{from_issue}...")
        branch = slugify_issue(from_issue)
        click.echo(f":: Branch name: {branch}")

    if not branch:
        raise click.UsageError("Provide a branch name or --from-issue <num>")

    wt = worktree_dir(branch)
    if wt.exists():
        raise click.ClickException(f"Worktree already exists: {wt}")

    # Create worktree
    click.echo(f":: Creating worktree at {wt}...")
    os.chdir(FRED_ROOT)

    branch_exists_local = subprocess.run(
        ["git", "show-ref", "--verify", f"refs/heads/{branch}"], capture_output=True
    ).returncode == 0
    branch_exists_remote = subprocess.run(
        ["git", "show-ref", "--verify", f"refs/remotes/origin/{branch}"], capture_output=True
    ).returncode == 0

    if branch_exists_local:
        run(["git", "worktree", "add", str(wt), branch])
    elif branch_exists_remote:
        run(["git", "worktree", "add", str(wt), f"origin/{branch}"])
    else:
        run(["git", "worktree", "add", "-b", branch, str(wt)])

    # Copy .env files
    click.echo(":: Copying .env files...")
    for svc in PYTHON_SERVICES:
        src = FRED_ROOT / svc / "config" / ".env"
        dst = wt / svc / "config" / ".env"
        if src.exists():
            shutil.copy2(src, dst)
            click.echo(f"   {svc}/config/.env")

    # Configure LLM provider
    if provider:
        make_target = PROVIDER_MAKE_TARGETS[provider]
        click.echo(f":: Configuring provider '{provider}' (make {make_target})...")
        run(["make", make_target], cwd=wt)

    # Disable prometheus metrics in prod configs (avoids port collisions between worktrees)
    for svc in PYTHON_SERVICES:
        prod_cfg = wt / svc / "config" / "configuration_prod.yaml"
        if prod_cfg.exists():
            content = prod_cfg.read_text()
            content = content.replace("metrics_enabled: true", "metrics_enabled: false")
            prod_cfg.write_text(content)

    # Allocate ports
    click.echo(":: Allocating ports...")
    used_ports: set[int] = set()
    ports = {}
    for svc in ALL_SERVICES:
        ports[svc] = find_free_port(used_ports)

    # Write PORTS.md
    (wt / "PORTS.md").write_text(generate_ports_md(branch, ports))

    # Copy .vscode from main repo (ensures latest tasks.json) then patch
    vscode_dir = wt / ".vscode"
    vscode_dir.mkdir(exist_ok=True)
    for f in (FRED_ROOT / ".vscode").iterdir():
        shutil.copy2(f, vscode_dir / f.name)

    color = pick_color()
    patch_workspace_file(wt, color)
    patch_vscode_tasks(wt, ports, autorun_task)
    click.echo(":: VSCode config patched")

    # Open VSCode
    click.echo(":: Opening VSCode...")
    workspace_file = wt / ".vscode" / "fred.code-workspace"
    subprocess.Popen(["code", str(workspace_file)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Summary
    click.echo()
    click.echo("=" * 50)
    click.echo(f"  Worktree ready: {branch}")
    click.echo("=" * 50)
    click.echo(f"  Directory:  {wt}")
    click.echo(f"  Agentic:    http://localhost:{ports['agentic-backend']}/agentic/v1/docs")
    click.echo(f"  KF:         http://localhost:{ports['knowledge-flow-backend']}/knowledge-flow/v1/docs")
    click.echo(f"  CP:         http://localhost:{ports['control-plane-backend']}/control-plane/v1/docs")
    click.echo(f"  Frontend:   http://localhost:{ports['frontend']}")
    click.echo()
    click.echo(f"  Run services: Ctrl+Shift+P > Tasks: Run Task > 'All Services (wt: {branch})'")
    click.echo("=" * 50)


@cli.command()
@click.argument("branch", shell_complete=complete_worktree_branch)
@click.option("-p", "--prune", is_flag=True, help="Delete the branch without confirmation if fully merged")
def remove(branch: str, prune: bool):
    """Remove a worktree and optionally its branch."""
    wt = worktree_dir(branch)
    if not wt.exists():
        raise click.ClickException(f"Worktree not found: {wt}")

    click.echo(f":: Removing worktree {branch}...")
    os.chdir(FRED_ROOT)
    try:
        run(["git", "worktree", "remove", "--force", str(wt)])
    except subprocess.CalledProcessError:
        # git worktree remove fails when directory has untracked files;
        # fall back to manual removal + prune
        click.echo(":: Force-removing directory and pruning worktree list...")
        shutil.rmtree(wt)
        run(["git", "worktree", "prune"])
    click.echo(f":: Worktree removed: {wt}")

    # Delete the branch if fully merged
    result = subprocess.run(["git", "branch", "--merged"], capture_output=True, text=True)
    if branch in result.stdout:
        if prune or click.confirm(f"Branch '{branch}' is fully merged. Delete it?", default=False):
            run(["git", "branch", "-d", branch])
            click.echo(f":: Branch deleted: {branch}")


@cli.command(name="list")
def list_worktrees():
    """List all Fred worktrees."""
    dirs = existing_worktree_dirs()
    if not dirs:
        click.echo("No Fred worktrees found.")
        return

    for wt in dirs:
        name = wt.name.removeprefix("fred-wt-")
        try:
            branch = run_quiet(["git", "branch", "--show-current"], cwd=wt).stdout.strip()
        except subprocess.CalledProcessError:
            branch = "???"

        click.echo(f"  {click.style(name, bold=True)}")
        click.echo(f"    Dir:    {wt}")
        click.echo(f"    Branch: {branch}")

        ports_file = wt / "PORTS.md"
        if ports_file.exists():
            for match in re.findall(r"(http://localhost:\d+\S*)", ports_file.read_text()):
                click.echo(f"    {match}")
        click.echo()


if __name__ == "__main__":
    cli()
