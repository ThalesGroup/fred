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

import logging
import os
import threading
from io import BytesIO
from itertools import chain
from pathlib import Path
from typing import Any, BinaryIO, TypedDict

import numpy as np
from numpy.typing import NDArray

from knowledge_flow_worker.core.processors.input.common.base_input_processor import BaseMarkdownProcessor

logger = logging.getLogger(__name__)

SUPPORTED_AUDIO = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}
SUPPORTED_VIDEO = {".mp4", ".mkv", ".avi", ".mov", ".webm"}
SUPPORTED_EXTENSIONS = SUPPORTED_AUDIO | SUPPORTED_VIDEO
SUPPORTED_CONTENT_TYPES = {
    "audio/aac",
    "audio/flac",
    "audio/mp4",
    "audio/mpeg",
    "audio/ogg",
    "audio/wav",
    "audio/webm",
    "audio/x-m4a",
    "audio/x-wav",
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/x-matroska",
    "video/x-msvideo",
}


# One Whisper model per (size, device) for the whole process: ingestion processors and
# the dictation endpoint each hold their own AudioProcessor instance.
_MODELS: dict[tuple[str, str], Any] = {}
_MODELS_LOCK = threading.Lock()


class TranscriptSegment(TypedDict):
    start: float
    end: float
    text: str


class AudioTranscriptionResult(TypedDict):
    text: str
    lines: list[str]
    segments: list[TranscriptSegment]
    language: str
    duration: float


class AudioProcessor(BaseMarkdownProcessor):
    description = "Transcribes audio and video files to Markdown using faster-whisper."

    def _get_audio_config(self) -> dict:
        try:
            from knowledge_flow_worker.application_context import get_configuration

            cfg = get_configuration()
            extras = getattr(cfg, "model_extra", None) or {}
            return extras.get("audio_model", {}) or {}
        except Exception:
            return {}

    def _get_model(self):
        audio_cfg = self._get_audio_config()
        # WHISPER_MODEL_SIZE is set by the prod image, which bakes exactly that
        # model into the Hugging Face hub cache at build time (#2406). Reading it
        # here keeps the baked model and the requested one in sync by construction.
        model_size = audio_cfg.get("whisper_model_size") or os.getenv("WHISPER_MODEL_SIZE") or "base"
        device = audio_cfg.get("device", "cpu")
        with _MODELS_LOCK:
            model = _MODELS.get((model_size, device))
            if model is None:
                model = _MODELS[(model_size, device)] = self._load_model(model_size, device)
        return model

    @staticmethod
    def _load_model(model_size: str, device: str):
        from faster_whisper import WhisperModel

        try:
            # Offline-first (#2406): never touch the network when the model is
            # already present in the local cache.
            return WhisperModel(model_size, device=device, compute_type="int8", local_files_only=True)
        except Exception:
            # Not necessarily a cache miss (a bad device or a corrupt snapshot lands
            # here too), so log the real cause instead of asserting one.
            logger.info(
                "Whisper model '%s' could not be loaded from the local cache; retrying with a Hugging Face hub download.",
                model_size,
                exc_info=True,
            )
            return WhisperModel(model_size, device=device, compute_type="int8")

    def check_file_validity(self, file_path: Path) -> bool:
        if not file_path.exists():
            return False
        if file_path.stat().st_size == 0:
            return False
        return file_path.suffix.lower() in SUPPORTED_EXTENSIONS

    @staticmethod
    def _probe(file_path: Path) -> tuple[float | None, bool]:
        """Container duration in seconds, and whether the file has a sound track."""
        import av

        try:
            with av.open(str(file_path)) as container:
                duration = float(container.duration) / 1_000_000 if container.duration else None
                return duration, bool(container.streams.audio)
        except Exception:
            logger.debug("Could not probe %s", file_path, exc_info=True)  # nosec B110
            return None, True

    def extract_file_metadata(self, file_path: Path) -> dict:
        duration, _ = self._probe(file_path)
        # duration_seconds n'est pas dans la whitelist de _apply_enrichment → passer via extras
        return {
            "file_size_bytes": file_path.stat().st_size,
            "suffix": file_path.suffix.lower(),
            "extras": {
                "duration_seconds": duration,
            },
        }

    def convert_file_to_markdown(self, file_path: Path, output_dir: Path, document_uid: str | None) -> dict:
        output_dir.mkdir(parents=True, exist_ok=True)
        transcript = self._transcribe_document(file_path)
        md_path = output_dir / "output.md"
        md_path.write_text(self._transcript_markdown(file_path.name, transcript), encoding="utf-8")
        return {"doc_dir": str(output_dir), "md_file": str(md_path)}

    def _transcribe_document(self, file_path: Path) -> AudioTranscriptionResult:
        duration, has_sound = self._probe(file_path)
        if not has_sound:  # A silent screen recording is still a valid video.
            return {"text": "", "lines": [], "segments": [], "language": "-", "duration": duration or 0.0}
        return self.transcribe_file_to_text(file_path)

    @staticmethod
    def _transcript_markdown(name: str, transcript: AudioTranscriptionResult) -> str:
        return f"# Transcript — {name}\n\n**Langue détectée :** {transcript['language']}  \n**Durée :** {float(transcript['duration']):.1f}s\n\n## Contenu\n\n" + "\n".join(transcript["lines"]) + "\n"

    def transcribe_file_to_text(self, source: Path | BinaryIO, language: str | None = None, *, max_seconds: int | None = None, input_format: str | None = None) -> AudioTranscriptionResult:
        """Transcribe a document or a recorded clip through the same local model."""
        samples = self._decode_audio(source, max_seconds, input_format)
        # The VAD drops silent stretches, where Whisper otherwise invents text.
        segments, info = self._get_model().transcribe(samples, beam_size=5, language=language, vad_filter=True)
        lines: list[str] = []
        kept: list[TranscriptSegment] = []
        for segment in segments:
            text = segment.text.strip()
            if not text:
                continue
            kept.append({"start": float(segment.start), "end": float(segment.end), "text": text})
            timestamp = self._format_timestamp(segment.start)
            lines.append(f"[{timestamp}] {text}")
        return {
            "text": " ".join(item["text"] for item in kept),
            "lines": lines,
            "segments": kept,
            "language": info.language,
            "duration": float(info.duration or 0.0),
        }

    @staticmethod
    def _decode_audio(source: Path | BinaryIO, max_seconds: int | None, input_format: str | None) -> NDArray[np.float32]:
        import av

        # Whisper accepts a mono, 16 kHz float waveform directly. Enforce the
        # dictation limit on decoded samples even if the container has no duration.
        with av.open(str(source) if isinstance(source, Path) else source, mode="r", format=input_format) as container:
            resampler = av.AudioResampler(format="flt", layout="mono", rate=16000)
            buffer = BytesIO()
            samples = 0
            for frame in chain(container.decode(audio=0), (None,)):
                for resampled in resampler.resample(frame):
                    samples += resampled.samples
                    if max_seconds is not None and samples > max_seconds * 16000:
                        raise ValueError("Recording exceeds the dictation duration limit.")
                    buffer.write(resampled.to_ndarray().tobytes())
        if not samples:
            raise ValueError("The file contains no audio samples.")
        return np.frombuffer(buffer.getbuffer(), dtype=np.float32)

    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
