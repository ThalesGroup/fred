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

"""Durable, conversation-local external edit consolidation and publication."""

from __future__ import annotations

import asyncio
import difflib
import hashlib
import json
from collections import Counter
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Literal
from urllib.parse import quote

from fred_sdk.contracts.runtime import (
    ConversationScratchpadError,
    ConversationScratchpadFileNotFoundError,
    ConversationScratchpadStorageError,
)
from pydantic import BaseModel, Field, ValidationError

if TYPE_CHECKING:
    from fred_runtime.conversation_filesystem import ConversationTextNamespacePort

_STATE_PATH = ".changes/state.json"


class ConversationFilesystemPartialSaveError(ConversationScratchpadStorageError):
    """The working mutation succeeded but its durable recording failed."""

    MESSAGE = (
        "The file changed, but change history bookkeeping failed; retry to recover"
    )

    def __init__(self) -> None:
        super().__init__(self.MESSAGE)


class ChangePublication(BaseModel):
    """A sealed exchange's path-only publication receipt."""

    file_count: int = 0
    paths: tuple[str, ...] = ()


class _Group(BaseModel):
    path: str
    before: str | None
    after: str | None
    closed: bool = False


class _Intent(_Group):
    source: Literal["external", "agent"] = "external"


class _State(BaseModel):
    pending: list[_Group] = Field(default_factory=list)
    sealing: dict[str, list[_Group]] = Field(default_factory=dict)
    completed: dict[str, ChangePublication] = Field(default_factory=dict)
    intent: list[_Intent] = Field(default_factory=list)


class ConversationChanges:
    """Uses the existing internal namespace, quotas and erasure owner.

    Call mutation/seal operations under the working namespace lock. That lock
    serializes this process only; storage does not offer a distributed CAS.
    """

    def __init__(self, deep: ConversationTextNamespacePort) -> None:
        self._deep = deep

    async def _load(self) -> _State:
        try:
            raw = await self._deep.read_text(_STATE_PATH)
        except ConversationScratchpadFileNotFoundError:
            return _State()
        try:
            return await asyncio.to_thread(_State.model_validate_json, raw)
        except ValidationError:
            raise ConversationScratchpadStorageError(
                "External change bookkeeping is unreadable"
            ) from None

    async def _save(self, state: _State) -> None:
        await self._deep.write_text(
            _STATE_PATH, await asyncio.to_thread(state.model_dump_json)
        )

    async def recover(self, read: Callable[[str], Awaitable[str | None]]) -> None:
        state = await self._load()
        if not state.intent:
            return
        semaphore = asyncio.Semaphore(16)

        async def current(change: _Group) -> str | None:
            async with semaphore:
                return await read(change.path)

        values = await asyncio.gather(*(current(change) for change in state.intent))
        for intent, value in zip(state.intent, values, strict=True):
            if value == intent.after:
                _apply(state, intent)
            elif value != intent.before:
                raise ConversationScratchpadStorageError(
                    "External change recovery found an unresolved partial mutation"
                )
        state.intent = []
        await self._save(state)

    async def prepare(self, path: str, before: str | None, after: str | None) -> bool:
        if before == after:
            return False
        state = await self._load()
        state.intent = [_Intent(path=path, before=before, after=after)]
        await self._save(state)
        return True

    async def prepare_deletions(self, files: dict[str, str]) -> bool:
        if not files:
            return False
        state = await self._load()
        state.intent = [
            _Intent(path=path, before=content, after=None)
            for path, content in files.items()
        ]
        await self._save(state)
        return True

    async def prepare_agent(
        self,
        path: str,
        after: str | None,
        read: Callable[[str], Awaitable[str | None]],
        *,
        delete_tree: bool = False,
    ) -> bool:
        state = await self._load()
        if state.intent:
            await self.recover(read)
            state = await self._load()
        # The latest open external group's end is the known current baseline.
        # Ordinary full agent writes do not read their overwrite target.
        state.intent = [
            _Intent(path=group.path, before=group.after, after=after, source="agent")
            for group in state.pending
            if not group.closed
            and group.after != after
            and (
                group.path == path
                or (delete_tree and group.path.startswith(path + "/"))
            )
        ]
        if not state.intent:
            return False
        await self._save(state)
        return True

    async def finish(self) -> None:
        try:
            state = await self._load()
            if not state.intent:
                return
            for change in state.intent:
                _apply(state, change)
            state.intent = []
            await self._save(state)
        except ConversationScratchpadError as exc:
            raise ConversationFilesystemPartialSaveError() from exc

    async def seal(self, exchange_id: str) -> None:
        state = await self._load()
        if exchange_id in state.completed or exchange_id in state.sealing:
            return
        state.sealing[exchange_id] = state.pending
        state.pending = []
        await self._save(state)

    async def publish(self, exchange_id: str, lock: asyncio.Lock) -> ChangePublication:
        async with lock:
            state = await self._load()
            if exchange_id in state.completed:
                return state.completed[exchange_id]
            groups = state.sealing[exchange_id]
        artifacts = await asyncio.to_thread(_render, exchange_id, groups)
        # Each artifact consumes the same quota budget. Preserve quota-checked
        # write ordering and acknowledge only after every write succeeds.
        for path, content in artifacts.items():
            if await self._deep.exists(path):
                if await self._deep.read_text(path) != content:
                    raise ConversationScratchpadStorageError(
                        "Published change history differs from the sealed interval"
                    )
            else:
                await self._deep.write_text(path, content)
        receipt = ChangePublication(
            file_count=len({g.path for g in groups if g.before != g.after}),
            paths=tuple(f"/.deep/{path}" for path in artifacts),
        )
        async with lock:
            state = await self._load()
            state.completed[exchange_id] = receipt
            state.sealing.pop(exchange_id, None)
            await self._save(state)
        return receipt


def _apply(state: _State, change: _Intent) -> None:
    if change.source == "agent":
        group = _open_group(state, change.path)
        if group is not None:
            group.closed = True
    else:
        _record(state, change)


def _open_group(state: _State, path: str) -> _Group | None:
    return next(
        (
            group
            for group in reversed(state.pending)
            if group.path == path and not group.closed
        ),
        None,
    )


def _record(state: _State, change: _Group) -> None:
    group = _open_group(state, change.path)
    if group is None:
        state.pending.append(
            _Group(path=change.path, before=change.before, after=change.after)
        )
    else:
        group.after = change.after


def _render(exchange_id: str, groups: list[_Group]) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    counts = Counter(g.path for g in groups if g.before != g.after)
    names = _artifact_names(counts)
    indexes: Counter[str] = Counter()
    for group in groups:
        if group.before == group.after:
            continue
        indexes[group.path] += 1
        sequence = _sequence(indexes[group.path], counts[group.path])
        label = f"External change group {sequence}" if sequence else ""
        header_label = "\t" + label if label else ""
        path = "/" + group.path
        if not path.isprintable() or '"' in path:
            path = json.dumps(path, ensure_ascii=True)
        before_path = path if group.before is not None else "/dev/null"
        after_path = path if group.after is not None else "/dev/null"
        lines = list(
            difflib.unified_diff(
                _diff_lines(group.before),
                _diff_lines(group.after),
                fromfile=before_path,
                tofile=after_path,
                fromfiledate=label,
                tofiledate=label,
            )
        )
        content = (
            "".join(
                line
                if line.endswith("\n")
                else line + "\n\\ No newline at end of file\n"
                for line in lines
            )
            if lines
            else f"--- {before_path}{header_label}\n+++ {after_path}{header_label}\n"
        )
        suffix = f".{sequence}" if sequence else ""
        artifacts[f"changes/{exchange_id}/{names[group.path]}{suffix}.diff"] = content
    return artifacts


def _diff_lines(content: str | None) -> list[str]:
    # Unified patches count LF-delimited lines; CR and Unicode separators are
    # content bytes, not additional patch lines.
    if not content:
        return []
    parts = content.split("\n")
    return [part + "\n" for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def _artifact_names(counts: Counter[str]) -> dict[str, str]:
    names = {path: quote(path, safe="") for path in counts}
    for path, name in names.items():
        # quote() escapes literal !, so generated hash names have a reserved
        # separator that cannot collide with an ordinary escaped source name.
        if len(name) > 180:
            names[path] = _hashed_name(path, name)
    owners: dict[str, list[str]] = {}
    for path, count in counts.items():
        for index in range(1, count + 1):
            sequence = _sequence(index, count)
            suffix = f".{sequence}" if sequence else ""
            owners.setdefault(names[path] + suffix, []).append(path)
    colliding = {path for paths in owners.values() if len(paths) > 1 for path in paths}
    for path in colliding:
        names[path] = _hashed_name(path, quote(path, safe=""))
    return names


def _sequence(index: int, count: int) -> str:
    return f"{index:0{max(3, len(str(count)))}d}" if count > 1 else ""


def _hashed_name(path: str, escaped: str) -> str:
    return escaped[:100] + "!" + hashlib.sha256(path.encode()).hexdigest()
