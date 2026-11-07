# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Bounded CLI transport for Docker and kubectl; agent code is never a shell command."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str
    truncated: bool = False


class CommandTimeout(TimeoutError):
    pass


class CommandRunner(Protocol):
    async def run(
        self,
        args: Sequence[str],
        *,
        timeout: float,
        output_limit: int = 65_536,
        input_data: bytes | None = None,
    ) -> CommandResult: ...


class SubprocessRunner:
    async def run(
        self,
        args: Sequence[str],
        *,
        timeout: float,
        output_limit: int = 65_536,
        input_data: bytes | None = None,
    ) -> CommandResult:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE if input_data is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert process.stdout is not None and process.stderr is not None

        async def drain(stream: asyncio.StreamReader) -> tuple[bytes, bool]:
            chunks: list[bytes] = []
            kept = 0
            truncated = False
            while chunk := await stream.read(4096):
                remaining = max(0, output_limit - kept)
                if remaining:
                    chunks.append(chunk[:remaining])
                    kept += min(len(chunk), remaining)
                truncated |= len(chunk) > remaining
            return b"".join(chunks), truncated

        try:
            if input_data is not None:
                assert process.stdin is not None
                process.stdin.write(input_data)
                await process.stdin.drain()
                process.stdin.close()
            _, stdout, stderr = await asyncio.wait_for(
                asyncio.gather(
                    process.wait(),
                    drain(process.stdout),
                    drain(process.stderr),
                ),
                timeout=timeout,
            )
        except BaseException as exc:
            if process.returncode is None:
                process.kill()
            await process.wait()
            if isinstance(exc, asyncio.TimeoutError):
                raise CommandTimeout from exc
            raise
        stdout_bytes, stdout_truncated = stdout
        stderr_bytes, stderr_truncated = stderr
        assert process.returncode is not None
        return CommandResult(
            returncode=process.returncode,
            stdout=stdout_bytes.decode("utf-8", errors="replace"),
            stderr=stderr_bytes.decode("utf-8", errors="replace"),
            truncated=stdout_truncated or stderr_truncated,
        )
