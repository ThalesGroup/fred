# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
import pytest
from fred_core.common import PostgresStoreConfig


@pytest.mark.parametrize("schema", ["runtime", "knowledge", "evaluation"])
def test_schema_wins_over_driver_settings_without_discarding_other_settings(schema):
    config = PostgresStoreConfig(
        schema=schema,
        connect_args={
            "server_settings": {"search_path": "public", "application_name": "fixture"}
        },
    )
    args = config.postgres_connect_args(asynchronous=True)
    assert args["server_settings"] == {
        "search_path": schema,
        "application_name": "fixture",
    }
    assert config.connect_args is not None
    assert config.connect_args["server_settings"]["search_path"] == "public"


@pytest.mark.parametrize("schema", [None, "public"])
def test_postgres_without_an_owning_schema_fails_closed(schema):
    with pytest.raises(ValueError, match="owning PostgreSQL schema"):
        PostgresStoreConfig(schema=schema).postgres_connect_args(asynchronous=True)


def test_schema_survives_configuration_round_trip():
    config = PostgresStoreConfig(schema="runtime")
    restored = PostgresStoreConfig.model_validate(config.model_dump())
    assert (
        restored.postgres_connect_args(asynchronous=True)["server_settings"][
            "search_path"
        ]
        == "runtime"
    )
