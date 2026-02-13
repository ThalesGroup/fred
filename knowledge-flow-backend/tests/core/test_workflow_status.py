from knowledge_flow_backend.features.scheduler.workflow_status import (
    is_non_terminal_status,
    is_terminal_failure_status,
    normalize_workflow_status,
)


class _DummyEnumValue:
    def __init__(self, name: str):
        self.name = name


def test_normalize_workflow_status_from_enum_like_value():
    assert normalize_workflow_status(_DummyEnumValue("running")) == "RUNNING"


def test_normalize_workflow_status_from_string_variants():
    assert normalize_workflow_status("WorkflowExecutionStatus.FAILED") == "FAILED"
    assert normalize_workflow_status("canceled") == "CANCELED"
    assert normalize_workflow_status(" ") is None


def test_status_classifiers():
    assert is_non_terminal_status("RUNNING")
    assert is_non_terminal_status("CONTINUED_AS_NEW")
    assert not is_non_terminal_status("FAILED")

    assert is_terminal_failure_status("FAILED")
    assert is_terminal_failure_status("TIMED_OUT")
    assert not is_terminal_failure_status("COMPLETED")
