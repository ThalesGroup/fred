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

import json
import logging
import os
import sys
from pathlib import Path
from typing import Callable, TypeVar

import yaml
from pydantic import ValidationError

from fred_pod.security.delegation import DelegationConfig

from .config_files import ConfigFiles
from .structures import PostgresStoreConfig, default_postgres_store_config

TConfig = TypeVar("TConfig")

logger = logging.getLogger(__name__)


def _render_config_error_banner(config_file: str, error: Exception) -> None:
    """Print a loud, unmissable configuration-error banner to stderr.

    A misconfigured service must not start silently and fail later with an
    opaque error inside a request handler. We surface the root cause in red at
    startup. Colours are emitted only on a TTY so log files stay clean.
    """
    use_colour = sys.stderr.isatty()
    red = "\033[1;31m" if use_colour else ""
    reset = "\033[0m" if use_colour else ""
    bar = "=" * 78

    if isinstance(error, ValidationError):
        details = "\n".join(
            f"  - {' -> '.join(str(p) for p in err['loc']) or '(root)'}: {err['msg']}"
            for err in error.errors()
        )
    else:
        details = f"  - {error}"

    print(
        f"\n{red}{bar}\n"
        f"  CONFIGURATION ERROR — refusing to start\n"
        f"  file: {config_file}\n"
        f"{bar}{reset}\n"
        f"{details}\n"
        f"{red}{bar}{reset}\n",
        file=sys.stderr,
        flush=True,
    )


def parse_yaml_mapping_file(config_file: str) -> dict:
    """Load a YAML file and ensure it is a non-empty mapping."""
    with open(config_file, encoding="utf-8") as file:
        payload = yaml.safe_load(file)
    if payload is None:
        raise ValueError(f"Configuration file is empty: {config_file}")
    if not isinstance(payload, dict):
        raise ValueError(f"Configuration file must be a mapping object: {config_file}")
    return payload


_DELEGATION_SWITCHES = frozenset({"act_for_people", "accept_delegated_calls"})


def _load_local_delegation(configuration: object) -> None:
    """Only local make targets opt in; production YAML remains authoritative."""
    path = os.getenv("FRED_LOCAL_DELEGATION_FILE")
    security = getattr(configuration, "security", None)
    if not path or security is None:
        return
    try:
        payload = json.loads(Path(path).read_text())
        # The file only switches directions on; every other setting stays the YAML's.
        switches = payload["delegation"]
        if (
            not isinstance(switches, dict)
            or not switches
            or not switches.keys() <= _DELEGATION_SWITCHES
            or any(value is not True for value in switches.values())
        ):
            raise ValueError("expected only delegation switches turned on")
        policy = DelegationConfig.model_validate(
            {**security.delegation.model_dump(), **switches}
        )
        audiences = payload["audiences"]
        audiences = [audiences] if isinstance(audiences, str) else audiences
        issuers = {
            str(security.user.realm_url).rstrip("/"),
            str(security.m2m.realm_url).rstrip("/"),
        }
        if (
            payload["issuer"].rstrip("/") not in issuers
            or policy.audience not in audiences
        ):
            raise ValueError("issuer/audience differs from the selected configuration")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError(
            f"Invalid local delegation file {path}; rerun scripts/populate_local_delegation.py: {exc}"
        ) from exc
    security.delegation = policy
    logger.info("[CONFIG] Loaded local delegation from: %s", path)


def load_configuration_with_config_files(
    config_files: ConfigFiles,
    parser: Callable[[str], TConfig],
    dotenv_path: str | None = None,
) -> TConfig:
    """Load env + config path using ConfigFiles and parse via callback."""
    config_files.load_environment(dotenv_path)
    config_file = config_files.resolve_config_file_path()
    try:
        configuration = parser(config_file)
        _load_local_delegation(configuration)
    except (ValidationError, ValueError) as exc:
        # Render the root cause in red and stop, rather than letting an opaque
        # traceback (or a deferred runtime 401) bury what is wrong.
        _render_config_error_banner(config_file, exc)
        raise SystemExit(1) from exc
    config_files.mark_config_loaded(config_file)
    return configuration


# Own `ConfigFiles`: the caller below is a component that never loads the
# backend's full configuration model, so it cannot share that loader's instance.
# The distinct prefix keeps the second pair of [CONFIG] lines traceable.
_postgres_config_files = ConfigFiles(logger=logger, log_prefix="[CONFIG][postgres]")


def _parse_postgres_config(config_file: str) -> PostgresStoreConfig:
    payload = parse_yaml_mapping_file(config_file)
    storage = payload.get("storage") or {}
    section = storage.get("postgres")
    if section is None:
        # No section at all: the backends' storage model defaults this field
        # rather than leaving it empty, so a config without `storage:` must
        # still yield the SQLite file here — not an unusable all-None config.
        return default_postgres_store_config()
    return PostgresStoreConfig.model_validate(section)


def load_postgres_config() -> PostgresStoreConfig:
    """Read `storage.postgres` alone from the component's YAML config file.

    For code that owns a table but not the configuration model around it — a
    capability package needs the database its tables live in and nothing else,
    so requiring the whole backend's config model would drag that backend in as
    a dependency. Same `ENV_FILE`/`CONFIG_FILE` selection and the same
    `storage.postgres` path every backend config already uses.
    """

    return load_configuration_with_config_files(
        _postgres_config_files, _parse_postgres_config
    )


def get_config():
    raise NotImplementedError("This dependency have to be override by the backend")
