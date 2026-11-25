# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Private file transcription endpoint on the worker that owns Whisper."""

import asyncio
import hmac
import logging
from contextlib import asynccontextmanager, suppress
from io import BytesIO

import av
from aiohttp import BodyPartReader, web

from knowledge_flow_worker.core.processors.input.audio_processor.audio_processor import AudioProcessor

logger = logging.getLogger(__name__)
MAX_BYTES = 8 * 1024 * 1024
MAX_SECONDS = 125  # The composer stops recording at 120 seconds.
FORMATS = {"audio/webm": "matroska", "audio/ogg": "ogg", "audio/mp4": "mov", "audio/wav": "wav"}


def create_app(secret: str) -> web.Application:
    app = web.Application(client_max_size=MAX_BYTES + 16384)
    expected = f"Bearer {secret}".encode()
    processor = AudioProcessor()
    slot = asyncio.Lock()

    async def handle(request: web.Request) -> web.Response:
        if not hmac.compare_digest(request.headers.get("Authorization", "").encode(), expected):
            raise web.HTTPUnauthorized()
        if slot.locked():
            raise web.HTTPTooManyRequests()
        async with slot:
            # The Control Plane sends only a model field followed by one file.
            try:
                async with asyncio.timeout(15):
                    parts = await request.multipart()
                    model = await parts.next()
                    if not isinstance(model, BodyPartReader) or model.name != "model" or await model.read_chunk(1024) != b"whisper" or not model.at_eof():
                        raise web.HTTPBadRequest()
                    file = await parts.next()
                    if not isinstance(file, BodyPartReader) or file.name != "file":
                        raise web.HTTPBadRequest()
                    media_type = file.headers.get("Content-Type", "")
                    if media_type not in FORMATS:
                        raise web.HTTPUnsupportedMediaType()
                    audio = bytearray()
                    while chunk := await file.read_chunk():
                        if len(audio) + len(chunk) > MAX_BYTES:
                            raise web.HTTPRequestEntityTooLarge(max_size=MAX_BYTES, actual_size=len(audio) + len(chunk))
                        audio.extend(chunk)
                    if not audio or await parts.next() is not None:
                        raise web.HTTPBadRequest()
            except TimeoutError as exc:
                raise web.HTTPRequestTimeout() from exc
            except ValueError as exc:
                raise web.HTTPBadRequest() from exc

            job = asyncio.create_task(asyncio.to_thread(processor.transcribe_file_to_text, BytesIO(audio), max_seconds=MAX_SECONDS, input_format=FORMATS[media_type]))
            try:
                transcript = await asyncio.shield(job)
                return web.json_response({"text": transcript["text"]})
            except asyncio.CancelledError:
                # Keep the Whisper slot until the native call actually finishes.
                with suppress(Exception):
                    await job
                raise
            except (av.FFmpegError, IndexError, ValueError) as exc:
                raise web.HTTPBadRequest() from exc
            except Exception as exc:
                logger.warning("Local Whisper transcription failed", exc_info=True)
                raise web.HTTPServiceUnavailable() from exc

    app.router.add_post("/v1/audio/transcriptions", handle)
    return app


@asynccontextmanager
async def serve(host: str, port: int, secret: str | None):
    if not secret:
        yield
        return
    runner = web.AppRunner(create_app(secret), access_log=None)
    await runner.setup()
    try:
        await web.TCPSite(runner, host, port).start()
        logger.info("Private Whisper dictation endpoint listening on %s:%s", host, port)
        yield
    finally:
        await runner.cleanup()
