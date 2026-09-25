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

"""Processor-facing timing context, supplied by the execution boundary."""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from contextvars import ContextVar

from fred_core.kpi import Dims

TimerFactory = Callable[[str, Dims], AbstractContextManager]
_timer_factory: ContextVar[TimerFactory | None] = ContextVar("processing_timer_factory", default=None)


def processing_timer(name: str, dims: Dims) -> AbstractContextManager:
    factory = _timer_factory.get()
    return factory(name, dims) if factory is not None else nullcontext()


@contextmanager
def processing_metrics_scope(factory: TimerFactory) -> Iterator[None]:
    token = _timer_factory.set(factory)
    try:
        yield
    finally:
        _timer_factory.reset(token)
