from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from knowledge_flow_backend.main import _require_delegation_standing


class _Context:
    def __init__(self, rebac: Any = None, *, error: Exception | None = None) -> None:
        self.rebac = rebac
        self.error = error

    def get_rebac_engine(self) -> Any:
        if self.error is not None:
            raise self.error
        return self.rebac


@pytest.mark.asyncio
async def test_delegation_startup_validates_model_and_readiness() -> None:
    rebac = SimpleNamespace(
        enforces_standing=True,
        validate_standing_model=AsyncMock(),
        is_standing_seed_ready=AsyncMock(return_value=True),
    )
    context = _Context(rebac)

    await _require_delegation_standing(context, enabled=True)

    rebac.validate_standing_model.assert_awaited_once_with()
    rebac.is_standing_seed_ready.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_delegation_startup_requires_ready_standing() -> None:
    rebac = SimpleNamespace(
        enforces_standing=True,
        validate_standing_model=AsyncMock(),
        is_standing_seed_ready=AsyncMock(return_value=False),
    )
    context = _Context(rebac)

    with pytest.raises(ValueError, match="not ready"):
        await _require_delegation_standing(context, enabled=True)


@pytest.mark.asyncio
async def test_disabled_delegation_does_not_require_rebac() -> None:
    context = _Context(error=AssertionError("must not resolve ReBAC"))

    await _require_delegation_standing(context, enabled=False)
