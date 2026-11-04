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

"""Helpers for the background analysis tests: wait for jobs, age a row."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from fred_capability_ppt_filler.builder import analysis_job
from fred_capability_ppt_filler.builder.analysis_job import AnalysisRow
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def drain() -> None:
    """Wait for every background analysis this process started."""
    while analysis_job._running:
        await asyncio.gather(*list(analysis_job._running), return_exceptions=True)


async def age_row(
    maker: async_sessionmaker[AsyncSession], instance_id: str, **values: object
) -> None:
    """Expire the row's lease (the job died) and apply ``values``."""
    expired = datetime.now(timezone.utc) - timedelta(minutes=5)
    async with maker() as session:
        async with session.begin():
            await session.execute(
                update(AnalysisRow)
                .where(AnalysisRow.agent_instance_id == instance_id)
                .values(lease_until=expired, **values)
            )
