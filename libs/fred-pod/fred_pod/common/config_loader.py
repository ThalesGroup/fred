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

import sys
from typing import Callable, TypeVar

import yaml
from pydantic import ValidationError

from .config_files import ConfigFiles

TConfig = TypeVar("TConfig")


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
    except (ValidationError, ValueError) as exc:
        # Render the root cause in red and stop, rather than letting an opaque
        # traceback (or a deferred runtime 401) bury what is wrong.
        _render_config_error_banner(config_file, exc)
        raise SystemExit(1) from exc
    config_files.mark_config_loaded(config_file)
    return configuration


def get_config():
    raise NotImplementedError("This dependency have to be override by the backend")
