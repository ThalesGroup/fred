from __future__ import annotations

import itertools
import json
import os
import random
import re
import select
import shutil
import socket
import subprocess
import sys
import termios
import textwrap
import threading
import time
import tty
from pathlib import Path

import click
from click.shell_completion import CompletionItem

# ── Configuration ────────────────────────────────────────────────────────────

FRED_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
WORKTREE_BASE = FRED_ROOT.parent
PORT_RANGE = (9300, 9999)

PYTHON_SERVICES = ["fred-agents", "knowledge-flow-backend", "control-plane-backend"]
ALL_SERVICES = [*PYTHON_SERVICES, "frontend"]
SERVICE_DIRS = {
    "fred-agents": Path("apps/fred-agents"),
    "knowledge-flow-backend": Path("apps/knowledge-flow-backend"),
    "control-plane-backend": Path("apps/control-plane-backend"),
    "frontend": Path("apps/frontend"),
}

DEFAULT_PORTS = {
    "fred-agents": 8000,
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
    "#00695C",  # dark teal
    "#C62828",  # dark red
    "#4527A0",  # deep purple
    "#558B2F",  # light green
    "#E65100",  # deep orange
    "#0277BD",  # light blue
    "#6D4C41",  # dark brown
    "#283593",  # indigo
    "#00796B",  # teal 700
    "#7B1FA2",  # purple 700
    "#1B5E20",  # green 900
    "#880E4F",  # pink 900
]


# ── Output helpers ───────────────────────────────────────────────────────────

def step(msg: str) -> None:
    """Print a colored step indicator."""
    click.echo(click.style("▶ ", fg="cyan", bold=True) + msg)


def ok(msg: str) -> None:
    """Print a success line."""
    click.echo(click.style("✓ ", fg="green", bold=True) + msg)


def info(msg: str) -> None:
    """Print an indented info line."""
    click.echo("  " + click.style("·", fg="bright_black") + " " + msg)


class Spinner:
    """Context manager that shows an animated spinner while work is running."""

    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, msg: str):
        self._msg = msg
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)

    def _spin(self) -> None:
        for frame in itertools.cycle(self.FRAMES):
            if self._stop.is_set():
                break
            sys.stderr.write(f"\r{click.style(frame, fg='cyan', bold=True)} {self._msg}")
            sys.stderr.flush()
            time.sleep(0.08)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._thread.join()
        sys.stderr.write("\r\033[K")  # clear the spinner line
        sys.stderr.flush()


def _read_key() -> str:
    """Read one keypress in raw mode, folding arrow-key escape sequences into one string."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        # TCSADRAIN (not the default TCSAFLUSH) so keys typed during a redraw are not discarded.
        # os.read (not sys.stdin.read) so escape-sequence bytes stay visible to select().
        tty.setraw(fd, termios.TCSADRAIN)
        key = os.read(fd, 1).decode(errors="replace")
        # Arrow keys arrive as "\x1b[A".."\x1b[D"; a bare Esc has no follow-up bytes
        if key == "\x1b" and select.select([fd], [], [], 0.05)[0]:
            key += os.read(fd, 1).decode(errors="replace")
            if key.endswith("[") and select.select([fd], [], [], 0.05)[0]:
                key += os.read(fd, 1).decode(errors="replace")
        return key
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def multi_select(options: list[str]) -> list[int] | None:
    """Interactive checklist: ↑/↓ move, space toggles, enter confirms.

    Returns the selected indices, or None if cancelled (q, Esc, Ctrl+C).
    """
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise click.ClickException("Interactive selection requires a terminal")

    selected = [False] * len(options)
    cursor = 0
    footer = click.style("  ↑/↓ move · space toggle · a all · enter confirm · q cancel", fg="bright_black")

    sys.stdout.write("\x1b[?25l")  # hide cursor
    try:
        first = True
        while True:
            if not first:
                sys.stdout.write(f"\x1b[{len(options) + 1}A")  # move back up to redraw in place
            first = False
            for i, opt in enumerate(options):
                pointer = click.style("❯", fg="cyan", bold=True) if i == cursor else " "
                box = click.style("◉", fg="green", bold=True) if selected[i] else "◯"
                label = click.style(opt, bold=True) if i == cursor else opt
                sys.stdout.write(f"\r\x1b[K {pointer} {box} {label}\n")
            sys.stdout.write(f"\r\x1b[K{footer}\n")
            sys.stdout.flush()

            key = _read_key()
            if key in ("\x1b[A", "k"):
                cursor = (cursor - 1) % len(options)
            elif key in ("\x1b[B", "j"):
                cursor = (cursor + 1) % len(options)
            elif key == " ":
                selected[cursor] = not selected[cursor]
            elif key == "a":
                everything_on = all(selected)
                selected = [not everything_on] * len(options)
            elif key in ("\r", "\n"):
                return [i for i, on in enumerate(selected) if on]
            elif key in ("q", "\x1b", "\x03"):
                return None
    finally:
        sys.stdout.write("\x1b[?25h")  # restore cursor
        sys.stdout.flush()


# ── Helpers ──────────────────────────────────────────────────────────────────


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command, raising on failure."""
    return subprocess.run(cmd, check=True, **kwargs)


def run_quiet(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command silently."""
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kwargs)


def service_dir(service: str) -> Path:
    """Return the repository-relative directory for one service name."""

    return SERVICE_DIRS.get(service, Path(service))


def worktree_dir(branch: str) -> Path:
    return WORKTREE_BASE / f"fred-wt-{branch}"


def current_worktree() -> tuple[Path, str]:
    """Return (worktree_root, branch) for the worktree containing cwd, or raise."""
    cwd = Path.cwd().resolve()
    for wt in existing_worktree_dirs():
        if cwd == wt or cwd.is_relative_to(wt):
            branch = wt.name.removeprefix("fred-wt-")
            return wt, branch
    raise click.ClickException(
        f"{cwd} is not inside a Fred worktree — run this command from within a worktree directory"
    )


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

    start, end = PORT_RANGE
    candidates = list(range(start, end + 1))
    random.shuffle(candidates)

    for port in candidates:
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
    """Pick a random color not already used by another worktree."""
    used: set[str] = set()
    for wt in existing_worktree_dirs():
        workspace_file = wt / ".vscode" / "fred.code-workspace"
        if workspace_file.exists():
            try:
                content = workspace_file.read_text()
                clean = re.sub(r",\s*([}\]])", r"\1", content)
                settings = json.loads(clean).get("settings", {})
                color = settings.get("workbench.colorCustomizations", {}).get("titleBar.activeBackground")
                if color:
                    used.add(color)
            except (json.JSONDecodeError, KeyError):
                # Workspace file is malformed or missing expected keys — skip it
                click.echo(f"[DEBUG] Skipping unreadable workspace file: {workspace_file}", err=True)

    available = [c for c in TITLEBAR_COLORS if c not in used]
    pool = available if available else TITLEBAR_COLORS
    return random.choice(pool)


def complete_worktree_branch(ctx, param, incomplete: str) -> list[CompletionItem]:
    """Autocomplete existing worktree branch names."""
    return [
        CompletionItem(d.name.removeprefix("fred-wt-"))
        for d in existing_worktree_dirs()
        if d.name.removeprefix("fred-wt-").startswith(incomplete)
    ]


def complete_git_branch(_ctx, _param, incomplete: str) -> list[CompletionItem]:
    """Autocomplete git branch names (local + remote) from the repo."""
    result = subprocess.run(
        ["git", "branch", "--all", "--format=%(refname:short)"],
        cwd=FRED_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    branches = [
        b.removeprefix("origin/")
        for b in result.stdout.splitlines()
        if not b.startswith("HEAD")
    ]
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique = [b for b in branches if not (b in seen or seen.add(b))]  # type: ignore[func-returns-value]
    return [CompletionItem(b) for b in unique if b.startswith(incomplete)]


def complete_provider(_ctx, _param, incomplete: str) -> list[CompletionItem]:
    """Autocomplete provider names from use-<provider> targets in the root Makefile."""
    makefile = FRED_ROOT / "Makefile"
    if not makefile.exists():
        return []
    providers = re.findall(r"^use-([a-z0-9_-]+):", makefile.read_text(), re.MULTILINE)
    return [CompletionItem(p) for p in providers if p.startswith(incomplete)]


def complete_vscode_task(_ctx, _param, incomplete: str) -> list[CompletionItem]:
    """Autocomplete VSCode task labels from .vscode/tasks.json."""
    tasks_file = FRED_ROOT / ".vscode" / "tasks.json"
    if not tasks_file.exists():
        return []
    try:
        tasks = json.loads(tasks_file.read_text())
        return [
            CompletionItem(t["label"])
            for t in tasks.get("tasks", [])
            if "label" in t and t["label"].startswith(incomplete)
        ]
    except (json.JSONDecodeError, KeyError):
        return []


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


def patch_workspace_file(wt: Path, color: str, branch: str) -> None:
    """Inject color customizations and window title into the .code-workspace settings block."""
    workspace_file = wt / ".vscode" / "fred.code-workspace"
    if not workspace_file.exists():
        raise click.ClickException(f"Workspace file not found: {workspace_file}")

    # Strip trailing commas so standard json can parse it
    content = workspace_file.read_text()
    clean = re.sub(r",\s*([}\]])", r"\1", content)
    workspace = json.loads(clean)

    workspace.setdefault("settings", {}).update(color_customizations(color))
    workspace["settings"]["window.title"] = f"fred [{branch}]${{dirty}}"
    workspace_file.write_text(json.dumps(workspace, indent="\t") + "\n")


def patch_launch_json(wt: Path, ports: dict[str, int]) -> None:
    """Patch .vscode/launch.json: replace default ports with worktree ports in args arrays."""
    launch_file = wt / ".vscode" / "launch.json"
    if not launch_file.exists():
        return

    # Strip trailing commas so standard json can parse it
    content = launch_file.read_text()
    clean = re.sub(r",\s*([}\]])", r"\1", content)
    launch = json.loads(clean)

    port_map = {str(DEFAULT_PORTS[svc]): str(ports[svc]) for svc in PYTHON_SERVICES}

    for config in launch.get("configurations", []):
        args = config.get("args", [])
        for i, arg in enumerate(args):
            if arg == "--port" and i + 1 < len(args) and args[i + 1] in port_map:
                args[i + 1] = port_map[args[i + 1]]

    launch_file.write_text(json.dumps(launch, indent=2) + "\n")


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
                            f"VITE_BACKEND_URL=http://localhost:{ports['fred-agents']} "
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


# Config files that hold cross-service `localhost:<port>` URLs and therefore need
# their ports rewritten to the worktree's allocation. Both the dev (`configuration.yaml`,
# loaded by `make run`) and prod (`configuration_prod.yaml`, loaded by `make run-prod`)
# variants are listed — patching only the prod one leaves the default dev task pointing
# at the main checkout's ports.
INTER_SERVICE_CONFIGS = [
    *[f"{service_dir(svc)}/config/configuration.yaml" for svc in PYTHON_SERVICES],
    *[f"{service_dir(svc)}/config/configuration_prod.yaml" for svc in PYTHON_SERVICES],
    f"{service_dir('fred-agents')}/config/mcp_catalog.yaml",
    "apps/knowledge-flow-backend/config/configuration_worker.yaml",
    "apps/control-plane-backend/config/configuration_worker.yaml",
]


def inter_service_config_paths(wt: Path) -> list[Path]:
    """Return the existing config files whose cross-service ports must be rewritten."""

    return [wt / p for p in INTER_SERVICE_CONFIGS if (wt / p).exists()]


def worktree_skip_paths(wt: Path) -> list[str]:
    """Return the list of worktree-local config paths that should be hidden from git status."""
    paths = [
        *INTER_SERVICE_CONFIGS,
        f"{service_dir('fred-agents')}/config/models_catalog.yaml",
        "deploy/local/k3d/values-local.yaml",
        ".vscode/tasks.json",
        ".vscode/launch.json",
        ".vscode/fred.code-workspace",
    ]
    return [p for p in paths if (wt / p).exists()]


def hide_config_files(wt: Path) -> None:
    """Mark worktree-local config files as skip-worktree so they don't show in git status."""
    existing = worktree_skip_paths(wt)
    if existing:
        run_quiet(["git", "update-index", "--skip-worktree", *existing], cwd=wt)


def read_ports_md(wt: Path) -> dict[str, int]:
    """Parse PORTS.md and return a {service: port} dict."""
    ports_file = wt / "PORTS.md"
    if not ports_file.exists():
        raise click.ClickException(f"PORTS.md not found in {wt} — cannot read port allocation")
    content = ports_file.read_text()
    service_patterns = {
        "fred-agents": r"Fred Agents\s*\|\s*(\d+)",
        "knowledge-flow-backend": r"Knowledge Flow Backend\s*\|\s*(\d+)",
        "control-plane-backend": r"Control Plane Backend\s*\|\s*(\d+)",
        "frontend": r"Frontend\s*\|\s*(\d+)",
    }
    ports: dict[str, int] = {}
    for svc, pattern in service_patterns.items():
        m = re.search(pattern, content)
        if not m:
            raise click.ClickException(f"Could not find port for '{svc}' in PORTS.md")
        ports[svc] = int(m.group(1))
    return ports


def warn_unpatched_default_ports(wt: Path, ports: dict[str, int]) -> None:
    """Warn about service config files still pointing at a default port after patching.

    A leftover default port means the worktree would talk to the main checkout's
    services instead of its own. This is the failure mode that went unnoticed when
    fred-agents was added, so surface it loudly rather than letting it fail at runtime.
    """
    default_ports = {str(p): svc for svc, p in DEFAULT_PORTS.items()}
    # Only ports we actually reallocated are stale; a service left on its default is fine.
    stale = {p: svc for p, svc in default_ports.items() if ports[svc] != int(p)}
    if not stale:
        return

    findings: list[str] = []
    for cfg in sorted((wt / "apps").glob("*/config/*.yaml")):
        try:
            content = cfg.read_text()
        except OSError:
            continue
        for port, svc in stale.items():
            if f"localhost:{port}" in content:
                findings.append(f"{cfg.relative_to(wt)} → localhost:{port} ({svc})")

    if findings:
        click.echo(
            click.style("! ", fg="yellow", bold=True)
            + "Config still references default ports — these may hit the main checkout:"
        )
        for f in findings:
            info(f)


def disable_prometheus_exporter(content: str) -> str:
    """Force `observability.kpi.prometheus.enabled: false` in a service config.

    Every backend (and Temporal worker) binds a hardcoded Prometheus scrape port
    (`observability.kpi.prometheus.port`) that is identical across worktrees, and
    the sink model defaults to enabled — so the second worktree to start a service
    dies with "Address already in use" on the metrics port, not the service port.
    Handles both config shapes: an explicit `enabled: true` right under the
    `prometheus:` key, and a block that only sets `port:` (relying on the
    enabled-by-default model).
    """
    patched = re.sub(
        r"^(\s*)prometheus:\n(\s+)enabled: true\b",
        r"\1prometheus:\n\2enabled: false",
        content,
        flags=re.MULTILINE,
    )
    return re.sub(
        r"^(\s*)prometheus:\n(\s+)port:",
        r"\1prometheus:\n\2enabled: false\n\2port:",
        patched,
        flags=re.MULTILINE,
    )


def apply_patch_pipeline(wt: Path, branch: str, ports: dict[str, int], autorun_task: str | None = None) -> None:
    """Apply the full worktree patch pipeline: prod configs, .vscode, and skip-worktree hiding."""
    # Patch inter-service URLs that reference another service by its default port.
    # Every service in DEFAULT_PORTS is rewritten (not just knowledge-flow): fred-agents
    # also dials control-plane via platform.control_plane_url, and leaving that at the
    # default port makes managed agent-instance execution fail with a connection error.
    # The same pass disables the Prometheus KPI exporter, whose scrape port cannot be
    # shared between worktrees.
    for cfg_path in inter_service_config_paths(wt):
        content = cfg_path.read_text()
        patched = content
        for svc, default_port in DEFAULT_PORTS.items():
            patched = patched.replace(f"localhost:{default_port}", f"localhost:{ports[svc]}")
        patched = disable_prometheus_exporter(patched)
        if patched != content:
            cfg_path.write_text(patched)
            info(f"Patched {cfg_path.relative_to(wt)}")

    # Copy .vscode from main repo (ensures latest tasks.json) then patch
    vscode_dir = wt / ".vscode"
    vscode_dir.mkdir(exist_ok=True)
    for f in (FRED_ROOT / ".vscode").iterdir():
        if f.is_file():
            shutil.copy2(f, vscode_dir / f.name)

    color = pick_color()
    patch_workspace_file(wt, color, branch)
    patch_vscode_tasks(wt, ports, autorun_task)
    patch_launch_json(wt, ports)
    ok("VSCode config patched")

    hide_config_files(wt)
    ok("Patched files hidden from git status (skip-worktree)")

    warn_unpatched_default_ports(wt, ports)


def open_vscode(wt: Path) -> None:
    """Open the VSCode workspace of a worktree."""
    workspace_file = wt / ".vscode" / "fred.code-workspace"
    if not workspace_file.exists():
        raise click.ClickException(f"Workspace file not found: {workspace_file}")

    step("Opening VSCode...")
    subprocess.Popen(
        ["code", str(workspace_file)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    ok(f"VSCode opened: {workspace_file}")


def _claude_terminal_command(wt: Path) -> list[str] | None:
    """Build the command that opens a new terminal window at `wt` running `claude`."""
    terminal_env = os.environ.get("TERMINAL")
    candidates: list[tuple[str, list[str]]] = []
    if terminal_env:
        candidates.append((terminal_env, [terminal_env, "-e", "claude"]))
    candidates += [
        ("gnome-terminal", ["gnome-terminal", f"--working-directory={wt}", "--", "claude"]),
        ("konsole", ["konsole", "--workdir", str(wt), "-e", "claude"]),
        ("xfce4-terminal", ["xfce4-terminal", f"--working-directory={wt}", "-x", "claude"]),
        ("kitty", ["kitty", "--directory", str(wt), "claude"]),
        ("alacritty", ["alacritty", "--working-directory", str(wt), "-e", "claude"]),
        ("wezterm", ["wezterm", "start", "--cwd", str(wt), "--", "claude"]),
        ("xterm", ["xterm", "-e", "claude"]),
    ]
    for binary, cmd in candidates:
        if shutil.which(binary):
            return cmd
    return None


def open_claude_terminal(wt: Path) -> None:
    """Open a new terminal window in the worktree with `claude` started."""
    cmd = _claude_terminal_command(wt)
    if cmd is None:
        click.echo(
            click.style("! ", fg="yellow", bold=True)
            + "No terminal emulator found — set $TERMINAL or start claude manually:\n"
            + f"    cd {wt} && claude"
        )
        return

    step("Opening claude terminal...")
    subprocess.Popen(
        cmd,
        cwd=wt,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    ok(f"Claude terminal opened in {wt}")


def generate_ports_md(branch: str, ports: dict[str, int]) -> str:
    return textwrap.dedent(f"""\
        # Worktree: {branch}

        | Service                 | Port  | URL                                                          |
        |-------------------------|-------|--------------------------------------------------------------|
        | Fred Agents             | {ports["fred-agents"]} | http://localhost:{ports["fred-agents"]}/agentic/v1/docs                 |
        | Knowledge Flow Backend  | {ports["knowledge-flow-backend"]} | http://localhost:{ports["knowledge-flow-backend"]}/knowledge-flow/v1/docs       |
        | Control Plane Backend   | {ports["control-plane-backend"]} | http://localhost:{ports["control-plane-backend"]}/control-plane/v1/docs         |
        | Frontend                | {ports["frontend"]} | http://localhost:{ports["frontend"]}                                     |
    """)


# ── Commands ─────────────────────────────────────────────────────────────────

_WORKTREE_COMMANDS = {"show-hidden-files", "hide-config-files", "patch-wt"}


class _GroupedGroup(click.Group):
    """click.Group that renders commands in two labelled sections in --help."""

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        global_cmds: list[tuple[str, str]] = []
        worktree_cmds: list[tuple[str, str]] = []

        for name in self.list_commands(ctx):
            cmd = self.commands.get(name)
            if cmd is None or cmd.hidden:
                continue
            help_text = cmd.get_short_help_str(limit=formatter.width or 80)
            (worktree_cmds if name in _WORKTREE_COMMANDS else global_cmds).append((name, help_text))

        if global_cmds:
            with formatter.section("Global commands"):
                formatter.write_dl(global_cmds)
        if worktree_cmds:
            with formatter.section("Worktree commands (run from inside a worktree)"):
                formatter.write_dl(worktree_cmds)


@click.group(cls=_GroupedGroup)
def cli():
    """Manage git worktrees for parallel Fred development."""



@cli.command()
@click.argument("branch", required=False, shell_complete=complete_git_branch)
@click.option("--from-issue", type=str, help="Create branch name from a GitHub issue number")
@click.option(
    "-p",
    "--provider",
    type=str,
    default=None,
    shell_complete=complete_provider,
    help="Configure a specific LLM provider in the worktree (e.g. mistral)",
)
@click.option(
    "-t",
    "--autorun-task",
    type=str,
    default=None,
    shell_complete=complete_vscode_task,
    help="VSCode task label to run automatically when the worktree folder is opened (e.g. 'All Services PROD')",
)
@click.option(
    "-f",
    "--from-branch",
    type=str,
    default=None,
    shell_complete=complete_git_branch,
    help="Source branch to create the new branch from (defaults to current HEAD)",
)
@click.option(
    "--claude/--no-claude",
    default=True,
    help="Open a new terminal with claude started in the worktree (default: on)",
)
@click.option(
    "--code/--no-code",
    default=False,
    help="Open the VSCode workspace (default: off)",
)
def create(
    branch: str | None,
    from_issue: str | None,
    provider: str | None,
    autorun_task: str | None,
    from_branch: str | None,
    claude: bool,
    code: bool,
):
    """Create a new worktree with full dev environment."""
    # Resolve branch name
    if from_issue and not branch:
        step(f"Fetching issue #{from_issue}...")
        branch = slugify_issue(from_issue)
        ok(f"Branch name: {click.style(branch, fg='yellow')}")

    if not branch:
        raise click.UsageError("Provide a branch name or --from-issue <num>")

    wt = worktree_dir(branch)
    if wt.exists():
        raise click.ClickException(f"Worktree already exists: {wt}")

    # Create worktree
    step(f"Creating worktree at {click.style(str(wt), fg='yellow')}...")
    os.chdir(FRED_ROOT)

    branch_exists_local = subprocess.run(
        ["git", "show-ref", "--verify", f"refs/heads/{branch}"], capture_output=True
    ).returncode == 0
    branch_exists_remote = subprocess.run(
        ["git", "show-ref", "--verify", f"refs/remotes/origin/{branch}"], capture_output=True
    ).returncode == 0

    git_env = {**os.environ, "GIT_PAGER": "cat", "GIT_TERMINAL_PROMPT": "0"}

    # Parse --from-branch: accept "remote/branch" or bare "branch" (defaults to origin)
    from_ref: str | None = None
    if from_branch:
        if "/" in from_branch:
            remote, remote_branch = from_branch.split("/", 1)
        else:
            remote, remote_branch = "origin", from_branch
        with Spinner(f"Fetching latest {click.style(from_branch, fg='yellow')}..."):
            subprocess.run(["git", "fetch", remote, remote_branch], env=git_env, capture_output=True)
        ok(f"Fetched {remote}/{remote_branch}")
        from_ref = f"{remote}/{remote_branch}"

    try:
        if branch_exists_local:
            run(["git", "worktree", "add", str(wt), branch], env=git_env)
        elif branch_exists_remote:
            run(
                ["git", "worktree", "add", "--track", "-b", branch, str(wt), f"origin/{branch}"],
                env=git_env,
            )
        else:
            cmd = ["git", "worktree", "add", "-b", branch, str(wt)]
            if from_ref:
                cmd.append(from_ref)
            run(cmd, env=git_env)
    except subprocess.CalledProcessError:
        raise click.ClickException(f"git failed to create worktree for branch '{branch}' — see error above")

    # Copy .env files
    step("Copying .env files...")
    for svc in PYTHON_SERVICES:
        relative_dir = service_dir(svc)
        src = FRED_ROOT / relative_dir / "config" / ".env"
        dst = wt / relative_dir / "config" / ".env"
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            info(f"{relative_dir}/config/.env")

    # Configure LLM provider
    if provider:
        make_target = f"use-{provider}"
        step(f"Configuring provider {click.style(provider, fg='magenta')} (make {make_target})...")
        # Check if the target exists in the worktree Makefile; if not, use the one from FRED_ROOT
        # so the target runs in the worktree directory (editing worktree files, not FRED_ROOT files)
        target_in_wt = subprocess.run(
            ["make", "--dry-run", make_target], cwd=wt, capture_output=True
        ).returncode == 0
        make_cmd = ["make", make_target] if target_in_wt else ["make", "-f", str(FRED_ROOT / "Makefile"), make_target]
        run(make_cmd, cwd=wt)

    # Allocate ports
    step("Allocating ports...")
    used_ports: set[int] = set()
    ports = {}
    for svc in ALL_SERVICES:
        ports[svc] = find_free_port(used_ports)
        info(f"{svc}: {click.style(str(ports[svc]), fg='cyan')}")

    # Write PORTS.md
    (wt / "PORTS.md").write_text(generate_ports_md(branch, ports))

    apply_patch_pipeline(wt, branch, ports, autorun_task)

    # Open editor / claude terminal
    if code:
        open_vscode(wt)
    if claude:
        open_claude_terminal(wt)

    # Summary
    w = 54
    bar = click.style("━" * w, fg="green", bold=True)
    click.echo()
    click.echo(bar)
    click.echo(click.style(f"  🌿 Worktree ready: {branch}", fg="green", bold=True))
    click.echo(bar)
    click.echo(f"  {click.style('Dir:', bold=True)}      {wt}")
    click.echo(f"  {click.style('Agents:', bold=True)}   " + click.style(f"http://localhost:{ports['fred-agents']}/agentic/v1/docs", fg="cyan"))
    click.echo(f"  {click.style('KF:', bold=True)}        " + click.style(f"http://localhost:{ports['knowledge-flow-backend']}/knowledge-flow/v1/docs", fg="cyan"))
    click.echo(f"  {click.style('CP:', bold=True)}        " + click.style(f"http://localhost:{ports['control-plane-backend']}/control-plane/v1/docs", fg="cyan"))
    click.echo(f"  {click.style('Frontend:', bold=True)} " + click.style(f"http://localhost:{ports['frontend']}", fg="cyan"))
    click.echo()
    click.echo(f"  {click.style('▶', fg='yellow')} Ctrl+Shift+P › Tasks: Run Task › " + click.style(f"All Services (wt: {branch})", fg="yellow"))
    click.echo(bar)


def remove_worktree_and_branch(branch: str, prune: bool) -> None:
    """Remove one worktree; offer to delete its branch if fully merged."""
    wt = worktree_dir(branch)
    os.chdir(FRED_ROOT)
    with Spinner(f"Removing worktree {click.style(branch, fg='yellow')}..."):
        try:
            run(["git", "worktree", "remove", "--force", str(wt)])
        except subprocess.CalledProcessError:
            # git worktree remove fails when directory has untracked files;
            # fall back to manual removal + prune
            shutil.rmtree(wt)
            run(["git", "worktree", "prune"])
    ok(f"Worktree removed: {wt}")

    # Delete the branch if fully merged
    result = subprocess.run(["git", "branch", "--merged"], capture_output=True, text=True)
    merged_branches = {
        line.strip().removeprefix("* ").strip()
        for line in result.stdout.splitlines()
        if line.strip()
    }
    if branch in merged_branches:
        if prune or click.confirm(f"Branch '{branch}' is fully merged. Delete it?", default=False):
            run(["git", "branch", "-d", branch])
            ok(f"Branch deleted: {click.style(branch, fg='yellow')}")


@cli.command()
@click.argument("branch", shell_complete=complete_worktree_branch)
@click.option("-p", "--prune", is_flag=True, help="Delete the branch without confirmation if fully merged")
def remove(branch: str, prune: bool):
    """Remove a worktree and optionally its branch."""
    wt = worktree_dir(branch)
    if not wt.exists():
        raise click.ClickException(f"Worktree not found: {wt}")

    remove_worktree_and_branch(branch, prune)


@cli.command()
@click.option("-p", "--prune", is_flag=True, help="Delete fully merged branches without confirmation")
def clean(prune: bool):
    """Interactively pick worktrees to remove (↑/↓ move, space toggles, enter confirms)."""
    dirs = existing_worktree_dirs()

    # Never offer the worktree we are currently inside — removing it would delete cwd
    cwd = Path.cwd().resolve()
    current = next((wt for wt in dirs if cwd == wt or cwd.is_relative_to(wt)), None)
    candidates = [wt for wt in dirs if wt != current]

    if not candidates:
        click.echo(click.style("No removable worktrees found.", fg="bright_black"))
        return

    click.echo(click.style("Select worktrees to remove:", bold=True))
    if current is not None:
        info(f"{current.name.removeprefix('fred-wt-')} is the current worktree — not listed")

    branches = [wt.name.removeprefix("fred-wt-") for wt in candidates]
    picked = multi_select(branches)
    if picked is None:
        click.echo(click.style("Aborted.", fg="bright_black"))
        return
    if not picked:
        click.echo(click.style("Nothing selected.", fg="bright_black"))
        return

    names = [branches[i] for i in picked]
    if not click.confirm(f"Remove {len(names)} worktree(s): {', '.join(names)}?", default=True):
        click.echo(click.style("Aborted.", fg="bright_black"))
        return

    for name in names:
        remove_worktree_and_branch(name, prune)


@cli.command(name="list")
def list_worktrees():
    """List all Fred worktrees."""
    dirs = existing_worktree_dirs()
    if not dirs:
        click.echo(click.style("No Fred worktrees found.", fg="bright_black"))
        return

    click.echo(click.style(f"  {len(dirs)} worktree(s)\n", fg="bright_black"))
    for wt in dirs:
        name = wt.name.removeprefix("fred-wt-")
        try:
            branch = run_quiet(["git", "branch", "--show-current"], cwd=wt).stdout.strip()
        except subprocess.CalledProcessError:
            branch = "???"

        click.echo(click.style("  🌿 ", fg="green") + click.style(name, bold=True, fg="green"))
        click.echo(f"    {click.style('Dir:', bold=True)}    {wt}")
        click.echo(f"    {click.style('Branch:', bold=True)} {click.style(branch, fg='yellow')}")

        ports_file = wt / "PORTS.md"
        if ports_file.exists():
            for match in re.findall(r"(http://localhost:\d+\S*)", ports_file.read_text()):
                click.echo("    " + click.style(match, fg="cyan"))
        click.echo()


@cli.command(name="open")
@click.argument("branch", shell_complete=complete_worktree_branch)
@click.option(
    "--claude/--no-claude",
    default=True,
    help="Open a new terminal with claude started in the worktree (default: on)",
)
@click.option(
    "--code/--no-code",
    default=False,
    help="Open the VSCode workspace (default: off)",
)
def open_worktree(branch: str, claude: bool, code: bool):
    """Open an existing worktree (claude terminal by default, VSCode with --code)."""
    wt = worktree_dir(branch)
    if not wt.exists():
        raise click.ClickException(f"Worktree not found: {wt}")

    if code:
        open_vscode(wt)
    if claude:
        open_claude_terminal(wt)


@cli.command(name="show-hidden-files")
def show_hidden_files():
    """Remove skip-worktree so patched config files appear in git status."""
    wt, branch = current_worktree()

    existing = worktree_skip_paths(wt)
    if not existing:
        ok("No skip-worktree files found — nothing to unhide")
        return

    run_quiet(["git", "update-index", "--no-skip-worktree", *existing], cwd=wt)
    ok(f"Unhidden {len(existing)} file(s) from git status ({branch})")
    for p in existing:
        info(p)


@cli.command(name="hide-config-files")
def hide_config_files_cmd():
    """Re-apply skip-worktree on patched config files so they are hidden from git status."""
    wt, branch = current_worktree()

    existing = worktree_skip_paths(wt)
    if not existing:
        ok("No config files to hide")
        return

    hide_config_files(wt)
    ok(f"Hidden {len(existing)} file(s) from git status ({branch})")
    for p in existing:
        info(p)


@cli.command(name="patch-wt")
@click.option("-t", "--autorun-task", type=str, default=None, shell_complete=complete_vscode_task,
              help="VSCode task to mark as run-on-folder-open")
def patch_wt(autorun_task: str | None):
    """Re-apply the full patch pipeline (ports, workspace, tasks, launch) for the current worktree.

    Useful after a stash pop or manual reset of config files.
    """
    wt, branch = current_worktree()

    step(f"Re-patching worktree {click.style(branch, fg='yellow')}...")
    ports = read_ports_md(wt)
    apply_patch_pipeline(wt, branch, ports, autorun_task)
    ok("Done")
