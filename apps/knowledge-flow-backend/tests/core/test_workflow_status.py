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
