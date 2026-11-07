import pytest
from fred_sdk.contracts.sandbox import SandboxError, SandboxRequest, SandboxResult
from pydantic import ValidationError


def test_sandbox_request_rejects_runtime_arguments() -> None:
    with pytest.raises(ValidationError):
        SandboxRequest.model_validate({"code": "echo ready", "runtime": "runc"})


def test_sandbox_contract_bounds_source_and_output() -> None:
    with pytest.raises(ValidationError):
        SandboxRequest(code="x" * 16_385)
    with pytest.raises(ValidationError):
        SandboxResult(exit_code=0, stdout="x" * 16_385, stderr="")


def test_sandbox_error_does_not_echo_backend_detail() -> None:
    assert SandboxError("docker daemon at private-host:2375").code == "unavailable"
