# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Deployment exports use effective YAML without loading service credentials."""

import json
import os
import subprocess
import sys


def test_rendered_configuration_export_requires_no_service_secrets(tmp_path):
    path = tmp_path / "worker.yaml"
    path.write_text("scheduler:\n  enabled: true\n  backend: temporal\n  temporal:\n    host: temporal:7233\n    namespace: default\n    task_queue: fixture-ingestion\n")
    command = [sys.executable, "-m", "knowledge_flow_backend.features.scheduler.export_contract", "--configuration", str(path)]
    result = subprocess.run(command, env={"PATH": os.environ["PATH"]}, capture_output=True, text=True, check=True)
    contract = json.loads(result.stdout)
    assert contract["workflow"] == "ProcessPush"
    assert set(contract["profiles"]) == {"fast", "medium", "rich"}
    assert contract["profiles"]["fast"]["extraction_task_queue"].startswith("fixture-ingestion")
    assert "secret" not in result.stdout.lower()
    path.write_text(path.read_text().replace("fixture-ingestion", "updated-ingestion"))
    updated = subprocess.run(command, env={"PATH": os.environ["PATH"]}, capture_output=True, text=True, check=True)
    assert json.loads(updated.stdout)["profiles"]["fast"]["extraction_task_queue"].startswith("updated-ingestion")
