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

from datetime import timedelta

from knowledge_flow_backend.features.scheduler.temporal_scheduler import _rpc_timeout


def test_rpc_timeout_converts_seconds_to_timedelta() -> None:
    # Used to bound client.start_workflow(...) so a stuck Temporal frontend
    # fails that single call instead of hanging the upload HTTP stream forever.
    assert _rpc_timeout(10) == timedelta(seconds=10)


def test_rpc_timeout_returns_none_when_unset() -> None:
    assert _rpc_timeout(None) is None


def test_rpc_timeout_returns_none_for_zero() -> None:
    # 0 means "no deadline" here, same as None — never an instant-timeout footgun.
    assert _rpc_timeout(0) is None
