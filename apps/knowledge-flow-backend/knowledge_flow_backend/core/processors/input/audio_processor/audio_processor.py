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
import tempfile
from pathlib import Path

from knowledge_flow_backend.core.processors.input.common.base_input_processor import BaseMarkdownProcessor

logger = logging.getLogger(__name__)

SUPPORTED_AUDIO = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}
SUPPORTED_VIDEO = {".mp4", ".mkv", ".avi", ".mov", ".webm"}
SUPPORTED_EXTENSIONS = SUPPORTED_AUDIO | SUPPORTED_VIDEO


class AudioProcessor(BaseMarkdownProcessor):
    description = "Transcribes audio and video files to Markdown using faster-whisper."

    def __init__(self):
        self._model = None  # lazy init

    def _get_audio_config(self) -> dict:
        try:
            from knowledge_flow_backend.application_context import get_configuration

            cfg = get_configuration()
            extras = getattr(cfg, "model_extra", None) or {}
            return extras.get("audio_model", {}) or {}
        except Exception:
            return {}

    def _get_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            audio_cfg = self._get_audio_config()
            model_size = audio_cfg.get("whisper_model_size", "base")
            device = audio_cfg.get("device", "cpu")
            self._model = WhisperModel(model_size, device=device, compute_type="int8")
        return self._model

    def check_file_validity(self, file_path: Path) -> bool:
        if not file_path.exists():
            return False
        if file_path.stat().st_size == 0:
            return False
        return file_path.suffix.lower() in SUPPORTED_EXTENSIONS

    def extract_file_metadata(self, file_path: Path) -> dict:
        import av

        duration = None
        try:
            with av.open(str(file_path)) as container:
                duration = float(container.duration) / 1_000_000 if container.duration else None
        except Exception:
            pass
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
        suffix = file_path.suffix.lower()

        if suffix in SUPPORTED_VIDEO:
            audio_path = self._extract_audio_from_video(file_path)
            transcribe_path = audio_path
        else:
            transcribe_path = file_path
            audio_path = None

        try:
            segments, info = self._get_model().transcribe(str(transcribe_path), beam_size=5)
            language = info.language
            duration = info.duration

            lines = []
            for seg in segments:
                ts = self._format_timestamp(seg.start)
                lines.append(f"[{ts}] {seg.text.strip()}")

            content = f"# Transcript — {file_path.name}\n\n**Langue détectée :** {language}  \n**Durée :** {duration:.1f}s\n\n## Contenu\n\n" + "\n".join(lines) + "\n"
            md_path = output_dir / "output.md"
            md_path.write_text(content, encoding="utf-8")
            return {"doc_dir": str(output_dir), "md_file": str(md_path)}
        finally:
            if audio_path and audio_path != file_path:
                try:
                    audio_path.unlink()
                except Exception:
                    pass

    def _extract_audio_from_video(self, video_path: Path) -> Path:
        import av

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        out_path = Path(tmp.name)

        with av.open(str(video_path)) as in_container:
            with av.open(str(out_path), mode="w", format="wav") as out_container:
                out_stream = out_container.add_stream("pcm_s16le", rate=16000, layout="mono")
                resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
                for frame in in_container.decode(audio=0):
                    for resampled in resampler.resample(frame):
                        resampled.pts = None
                        for packet in out_stream.encode(resampled):
                            out_container.mux(packet)
                # flush resampler
                for resampled in resampler.resample(None):
                    resampled.pts = None
                    for packet in out_stream.encode(resampled):
                        out_container.mux(packet)
                for packet in out_stream.encode(None):
                    out_container.mux(packet)
        return out_path

    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
