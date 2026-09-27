# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from fred_pod.common import (
    ConfigFiles,
    load_configuration_with_config_files,
    parse_yaml_mapping_file,
)


def test_parse_yaml_mapping_file_success(tmp_path) -> None:
    config_file = tmp_path / "configuration.yaml"
    config_file.write_text("app:\n  name: fred\n", encoding="utf-8")

    payload = parse_yaml_mapping_file(str(config_file))

    assert payload == {"app": {"name": "fred"}}


def test_parse_yaml_mapping_file_rejects_empty_file(tmp_path) -> None:
    config_file = tmp_path / "configuration.yaml"
    config_file.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="Configuration file is empty"):
        parse_yaml_mapping_file(str(config_file))


def test_parse_yaml_mapping_file_rejects_non_mapping(tmp_path) -> None:
    config_file = tmp_path / "configuration.yaml"
    config_file.write_text("- one\n- two\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Configuration file must be a mapping object"):
        parse_yaml_mapping_file(str(config_file))


def test_load_configuration_with_config_files_tracks_loaded_paths(
    tmp_path, monkeypatch
) -> None:
    env_file = tmp_path / ".env"
    config_file = tmp_path / "configuration.yaml"

    env_file.write_text("FRED_CORE_CONFIG_LOADER_TEST_KEY=from-env\n", encoding="utf-8")
    config_file.write_text("app:\n  name: fred\n", encoding="utf-8")

    monkeypatch.delenv("FRED_CORE_CONFIG_LOADER_TEST_KEY", raising=False)
    monkeypatch.delenv("ENV_FILE", raising=False)
    monkeypatch.delenv("CONFIG_FILE", raising=False)

    config_files = ConfigFiles(
        logger=logging.getLogger("fred_pod.tests.config_loader"),
        default_env_file=str(env_file),
        default_config_file=str(config_file),
    )

    def parser(path: str) -> dict:
        assert path == str(config_file)
        return parse_yaml_mapping_file(path)

    configuration = load_configuration_with_config_files(
        config_files,
        parser,
    )

    assert configuration == {"app": {"name": "fred"}}
    assert config_files.get_loaded_env_file_path() == str(env_file)
    assert config_files.get_loaded_config_file_path() == str(config_file)


def test_load_configuration_renders_banner_and_exits_on_error(
    tmp_path, monkeypatch, capsys
) -> None:
    config_file = tmp_path / "configuration.yaml"
    config_file.write_text("app:\n  name: fred\n", encoding="utf-8")

    monkeypatch.delenv("ENV_FILE", raising=False)
    monkeypatch.delenv("CONFIG_FILE", raising=False)

    config_files = ConfigFiles(
        logger=logging.getLogger("fred_pod.tests.config_loader"),
        default_config_file=str(config_file),
    )

    def failing_parser(_path: str) -> dict:
        raise ValueError("Set the OPENSEARCH_PASSWORD environment variable")

    with pytest.raises(SystemExit) as exc_info:
        load_configuration_with_config_files(config_files, failing_parser)

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "CONFIGURATION ERROR" in err
    assert "OPENSEARCH_PASSWORD" in err
    # An aborted load must not record the config as successfully loaded.
    assert config_files.get_loaded_config_file_path() is None


def _receiver_security(**delegation: object) -> SimpleNamespace:
    from fred_pod.security.delegation import DelegationConfig

    return SimpleNamespace(
        user=SimpleNamespace(realm_url="http://issuer/realm", client_id="app"),
        m2m=SimpleNamespace(realm_url="http://workload/realm", client_id="receiver"),
        delegation=DelegationConfig.model_validate(delegation),
    )


def _sidecar(tmp_path, issuer: str, audiences: list[str], delegation: object):
    import json

    path = tmp_path / "delegation.json"
    path.write_text(
        json.dumps({"issuer": issuer, "audiences": audiences, "delegation": delegation})
    )
    return path


@pytest.mark.parametrize(
    "issuer,audience",
    [("http://other/realm", "fred-delegation"), ("http://issuer/realm", "other")],
)
def test_local_delegation_refuses_mismatched_receiver(
    tmp_path, monkeypatch, issuer, audience
):
    from fred_pod.common.config_loader import _load_local_delegation

    sidecar = _sidecar(tmp_path, issuer, [audience], {"accept_delegated_calls": True})
    monkeypatch.setenv("FRED_LOCAL_DELEGATION_FILE", str(sidecar))
    security = _receiver_security()
    original = security.delegation
    with pytest.raises(ValueError, match="issuer/audience"):
        _load_local_delegation(SimpleNamespace(security=security))
    assert security.delegation is original


@pytest.mark.parametrize("issuer", ["http://issuer/realm", "http://workload/realm/"])
@pytest.mark.parametrize(
    "switches",
    [
        {"act_for_people": True},
        {"accept_delegated_calls": True},
        {"act_for_people": True, "accept_delegated_calls": True},
    ],
    ids=["act_for_people", "accept_delegated_calls", "both"],
)
def test_local_delegation_switches_on_the_yaml_block_and_nothing_else(
    tmp_path, monkeypatch, issuer, switches
):
    from fred_pod.common.config_loader import _load_local_delegation

    sidecar = _sidecar(tmp_path, issuer, ["fred-delegation", "account"], switches)
    security = _receiver_security(service_accounts_only=True, user_clients=["app"])
    configuration = SimpleNamespace(security=security)
    monkeypatch.delenv("FRED_LOCAL_DELEGATION_FILE", raising=False)
    _load_local_delegation(configuration)
    assert not security.delegation.in_use
    original_m2m = security.m2m
    monkeypatch.setenv("FRED_LOCAL_DELEGATION_FILE", str(sidecar))
    _load_local_delegation(configuration)
    for switch in ("act_for_people", "accept_delegated_calls"):
        assert getattr(security.delegation, switch) is (switch in switches)
    assert security.delegation.service_accounts_only
    assert security.delegation.user_clients == ["app"]
    assert security.m2m is original_m2m


def test_local_delegation_keeps_a_switch_the_yaml_already_turns_on(
    tmp_path, monkeypatch
):
    from fred_pod.common.config_loader import _load_local_delegation

    sidecar = _sidecar(
        tmp_path,
        "http://issuer/realm",
        ["fred-delegation"],
        {"accept_delegated_calls": True},
    )
    security = _receiver_security(act_for_people=True)
    monkeypatch.setenv("FRED_LOCAL_DELEGATION_FILE", str(sidecar))
    _load_local_delegation(SimpleNamespace(security=security))
    assert security.delegation.act_for_people
    assert security.delegation.accept_delegated_calls


@pytest.mark.parametrize(
    "delegation",
    [
        {"enabled": True},
        {},
        {"accept_delegated_calls": False},
        {"act_for_people": True, "accept_delegated_calls": False},
        {"accept_delegated_calls": True, "service_accounts_only": True},
        {
            "accept_delegated_calls": True,
            "caller_policies": [{"client_id": "caller", "subject": "service-id"}],
        },
        ["accept_delegated_calls"],
    ],
    ids=[
        "single_switch",
        "empty",
        "switch_off",
        "one_switch_off",
        "another_setting",
        "caller_list",
        "not_an_object",
    ],
)
def test_local_delegation_file_carries_only_switches_turned_on(
    tmp_path, monkeypatch, delegation
):
    from fred_pod.common.config_loader import _load_local_delegation

    sidecar = _sidecar(tmp_path, "http://issuer/realm", ["fred-delegation"], delegation)
    monkeypatch.setenv("FRED_LOCAL_DELEGATION_FILE", str(sidecar))
    security = _receiver_security(service_accounts_only=True)
    original = security.delegation
    with pytest.raises(ValueError, match="expected only delegation switches turned on"):
        _load_local_delegation(SimpleNamespace(security=security))
    assert security.delegation is original


def test_missing_explicit_local_delegation_file_fails_closed(tmp_path, monkeypatch):
    from fred_pod.common.config_loader import _load_local_delegation

    monkeypatch.setenv("FRED_LOCAL_DELEGATION_FILE", str(tmp_path / "missing.json"))
    with pytest.raises(ValueError, match="Invalid local delegation file"):
        _load_local_delegation(SimpleNamespace(security=SimpleNamespace()))
