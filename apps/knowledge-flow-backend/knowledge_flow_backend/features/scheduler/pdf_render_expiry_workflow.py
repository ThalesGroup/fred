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

"""Temporal workflow (sandboxed) behind the nightly PDF render expiry Schedule.

Same import-light, plain-data convention as `workflow.py`: only stdlib and
temporalio here. All the work happens in the single `expire_pdf_renders`
activity, so the history stays a handful of events whatever the corpus size.
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn(name="ExpirePdfRendersWorkflow")
class ExpirePdfRendersWorkflow:
    @workflow.run
    async def run(self) -> dict:
        return await workflow.execute_activity(
            "expire_pdf_renders",
            start_to_close_timeout=timedelta(minutes=30),
            heartbeat_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
