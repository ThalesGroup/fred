from __future__ import annotations

from fred_core.common import coerce_bool, read_env_bool


def test_coerce_bool_supports_common_runtime_inputs() -> None:
    assert coerce_bool(True) is True
    assert coerce_bool(False) is False
    assert coerce_bool(1) is True
    assert coerce_bool(0) is False
    assert coerce_bool(" yes ") is True
    assert coerce_bool("off") is False
    assert coerce_bool("y") is True
    assert coerce_bool("n") is False
    assert coerce_bool("unexpected", default=False) is False
    assert coerce_bool("unexpected", default=True) is True


def test_read_env_bool_uses_env_value_or_default(monkeypatch) -> None:
    monkeypatch.delenv("FRED_TEST_FLAG", raising=False)
    assert read_env_bool("FRED_TEST_FLAG", default=True) is True

    monkeypatch.setenv("FRED_TEST_FLAG", "0")
    assert read_env_bool("FRED_TEST_FLAG", default=True) is False

    monkeypatch.setenv("FRED_TEST_FLAG", "unexpected")
    assert read_env_bool("FRED_TEST_FLAG", default=False) is False
