"""
Scenario-driven integration tests for the fred-agents pod.

Why this module exists:
- each YAML file in tests/scenarios/ is a named contract for one agent
- pytest discovers and runs them automatically when the pod is up
- the runner itself lives in fred_runtime.client so it is shared with the
  `fred-agent-chat --scenario` CLI

How to run:
    # all scenarios (pod must be running)
    pytest tests/test_scenarios.py -m integration -s

    # one scenario by name
    pytest tests/test_scenarios.py -m integration -s -k sentinel_checkpointing

    # explicit pod URL
    pytest tests/test_scenarios.py -m integration -s \
        --pod-url http://127.0.0.1:8010/fred/agents/v2

Note: pass `-s` so pause steps (e.g. pod-restart prompts) reach your terminal.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fred_runtime.client import AgentPodClient, run_scenario_file

pytestmark = pytest.mark.integration

_SCENARIOS_DIR = Path(__file__).parent / "scenarios"


@pytest.mark.parametrize(
    "scenario_path",
    sorted(_SCENARIOS_DIR.glob("*.yaml")),
    ids=lambda p: p.stem,
)
def test_scenario(scenario_path: Path, pod_client: AgentPodClient) -> None:
    """
    Run one scenario file against the configured pod.

    Why this test exists:
    - placing the logic in fred_runtime.client means the same contract can be
      run with `fred-agent-chat --scenario FILE` or via pytest
    - adding a new scenario requires only a new YAML file, no Python changes
    """
    run_scenario_file(scenario_path, client=pod_client)
