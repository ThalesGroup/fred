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

from pathlib import Path
import librosa
import whisper

from app.core.processors.input.common.base_input_processor import BaseMarkdownProcessor


class AudioTranscriptionProcessor(BaseMarkdownProcessor):
    def __init__(self, model_size="base"):
        # model_size: "tiny", "base", "small", "medium", "large"
        self.model = whisper.load_model(model_size)

    def check_file_validity(self, file_path: Path) -> bool:
        return file_path.exists() and file_path.suffix.lower() in [".mp3"] # @TODO add support for ".wav", ".flac", ".ogg", ".m4a"]

    def extract_file_metadata(self, file_path: Path) -> dict:
        y, sr = librosa.load(file_path, sr=None, mono=True)
        duration = librosa.get_duration(y=y, sr=sr)

        return {
            "document_name": file_path.name,
            "duration_seconds": duration,
            "sample_rate": sr,
            "channels": 1,
            "suffix": file_path.suffix,
            "size_bytes": file_path.stat().st_size,
        }

    def convert_file_to_markdown(self, file_path: Path, output_dir: Path, document_uid: str | None) -> dict:
        """
        Transcrit un fichier audio en Markdown, sauvegarde et nettoie le répertoire de sortie.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / "output.md"

        result = self.model.transcribe(str(file_path))
        transcription_text = result["text"]

        markdown_text = f"# Transcription of {file_path.name}\n\n{transcription_text}"
        md_path.write_text(markdown_text, encoding="utf-8")

        if document_uid:
            md_content = md_path.read_text(encoding="utf-8")
            md_content = md_content.replace(str(output_dir), f"knowledge-flow/v1/markdown/{document_uid}")
            md_path.write_text(md_content, encoding="utf-8")

        return {
            "doc_dir": str(output_dir),
            "md_file": str(md_path)
        }
