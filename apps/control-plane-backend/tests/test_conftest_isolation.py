# Copyright Thales 2026
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

"""The offline suite owns its databases and leaves developer databases alone.

The schema fixture drops and recreates every table it is pointed at, so the
path it resolves is a safety property, not a convenience.
"""

from __future__ import annotations

import pathlib

import yaml

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_configured_database_is_project_owned(
    configured_database_path: pathlib.Path,
) -> None:
    assert configured_database_path.is_relative_to(_PROJECT_ROOT)
    assert not configured_database_path.is_relative_to(pathlib.Path.home() / ".fred")


def test_schema_fixture_created_the_configured_database(
    configured_database_path: pathlib.Path,
) -> None:
    assert configured_database_path.is_file()
    assert configured_database_path.stat().st_size > 0


def test_test_configuration_keeps_storage_out_of_the_home_directory() -> None:
    settings = yaml.safe_load(
        (_PROJECT_ROOT / "config" / "configuration_test.yaml").read_text()
    )
    storage = settings["storage"]

    for raw in (
        storage["postgres"]["sqlite_path"],
        storage["content_storage"]["root_path"],
    ):
        resolved = pathlib.Path(raw).expanduser().resolve()
        assert resolved.is_relative_to(_PROJECT_ROOT)
        assert not resolved.is_relative_to(pathlib.Path.home() / ".fred")


def test_opt_in_configuration_keeps_storage_under_the_run_root(
    isolated_run_root: pathlib.Path,
    isolated_config_path: pathlib.Path,
    isolated_database_path: pathlib.Path,
) -> None:
    settings = yaml.safe_load(isolated_config_path.read_text())
    storage = settings["storage"]

    configured_database = pathlib.Path(storage["postgres"]["sqlite_path"]).expanduser()
    configured_content = pathlib.Path(
        storage["content_storage"]["root_path"]
    ).expanduser()

    assert isolated_config_path.is_relative_to(isolated_run_root)
    assert configured_database == isolated_database_path
    assert configured_content.is_relative_to(isolated_run_root)


def test_developer_databases_are_untouched(
    pre_existing_databases: dict[pathlib.Path, tuple[int, int]],
) -> None:
    for database, recorded in pre_existing_databases.items():
        current = database.stat()
        assert (current.st_mtime_ns, current.st_size) == recorded
