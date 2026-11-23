# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Terminal access to the same global skill administration API as the UI."""

from control_plane_backend.cli.client import ControlPlaneApiClient


def run_platform_skills_command(args: list[str], client: ControlPlaneApiClient) -> None:
    """Inspect skills, or run `/platform-skills <name> on|off` to change one."""
    if not args:
        print(client.get_platform_skills().model_dump_json(indent=2))
        return
    if len(args) != 2 or args[1] not in {"on", "off"}:
        raise ValueError("Usage: /platform-skills [<name> on|off]")
    print(client.set_platform_skill_enabled(args[0], args[1] == "on").model_dump_json())
