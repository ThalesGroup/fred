# Copyright Thales 2025
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

"""
Shared async session utilities for all SQLAlchemy ORM stores.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Return a session factory bound to *engine*."""
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def use_session(
    factory: async_sessionmaker[AsyncSession],
    session: AsyncSession | None = None,
) -> AsyncGenerator[AsyncSession, None]:
    """
    Yield *session* as-is when provided (caller owns the transaction).
    Otherwise open a new session with an auto-committed transaction.
    """
    if session is not None:
        yield session
    else:
        async with factory() as s:
            async with s.begin():
                yield s
