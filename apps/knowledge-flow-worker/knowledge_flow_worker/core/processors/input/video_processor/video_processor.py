# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Video files: the spoken transcript plus a description of what each scene shows."""

import logging
from bisect import bisect_right
from pathlib import Path

from knowledge_flow_worker.application_context import get_configuration
from knowledge_flow_worker.common.processing_profile_context import get_current_processing_profile
from knowledge_flow_worker.core.processors.input.audio_processor.audio_processor import AudioProcessor, TranscriptSegment
from knowledge_flow_worker.core.processors.input.common.image_describer import IMAGE_DESCRIPTION_UNAVAILABLE, VIDEO_SCENE_DESCRIBE_PROMPT_V1, VisionImageDescriber, build_image_describer
from knowledge_flow_worker.core.processors.input.video_processor.scene_sampler import Scene, sample_scenes

logger = logging.getLogger(__name__)


class VideoProcessor(AudioProcessor):
    description = "Transcribes videos and, when the profile describes images, adds what each scene shows."

    def convert_file_to_markdown(self, file_path: Path, output_dir: Path, document_uid: str | None) -> dict:
        processing = get_configuration().processing
        profile = processing.get_profile_config(processing.normalize_profile(get_current_processing_profile()))
        describer = build_image_describer(system_prompt=VIDEO_SCENE_DESCRIBE_PROMPT_V1) if profile.process_images else None
        if not isinstance(describer, VisionImageDescriber):
            if profile.process_images:
                logger.info("No vision model admitted while process_images is enabled; the video keeps its transcript only.")
            return super().convert_file_to_markdown(file_path, output_dir, document_uid)

        output_dir.mkdir(parents=True, exist_ok=True)
        transcript = self._transcribe_document(file_path)
        scenes = sample_scenes(file_path, transcript["duration"], profile.video)
        logger.info("Describing %s scene(s) of a %.0fs video", len(scenes), transcript["duration"])
        md_path = output_dir / "output.md"
        if not scenes:  # No picture stream, such as an audio-only WebM.
            md_path.write_text(self._transcript_markdown(file_path.name, transcript), encoding="utf-8")
            return {"doc_dir": str(output_dir), "md_file": str(md_path)}
        # A segment belongs to the scene in which it starts, so no sentence is cut or repeated.
        spoken: list[list[TranscriptSegment]] = [[] for _ in scenes]
        starts = [scene.start for scene in scenes]
        for segment in transcript["segments"]:
            spoken[max(0, bisect_right(starts, segment["start"]) - 1)].append(segment)
        sections = [_scene_markdown(number, scene, spoken[number - 1], describer) for number, scene in enumerate(scenes, start=1)]
        content = f"# Vidéo — {file_path.name}\n\n**Langue détectée :** {transcript['language']}  \n**Durée :** {self._format_timestamp(transcript['duration'])}\n\n" + "\n\n".join(sections) + "\n"
        md_path.write_text(content, encoding="utf-8")
        return {"doc_dir": str(output_dir), "md_file": str(md_path)}


def _scene_markdown(number: int, scene: Scene, spoken: list[TranscriptSegment], describer: VisionImageDescriber) -> str:
    lines = [f"[{AudioProcessor._format_timestamp(segment['start'])}] {segment['text']}" for segment in spoken]
    heading = f"## Scène {number} · {AudioProcessor._format_timestamp(scene.start)} – {AudioProcessor._format_timestamp(scene.end)}"
    parts = [heading]
    if scene.frames:
        excerpt = "\n".join(lines) or "(no speech in this scene)"
        description = describer.describe_images(scene.frames, f"Frames of the scene, in order. Transcript of the scene:\n{excerpt}")
        if description != IMAGE_DESCRIPTION_UNAVAILABLE:
            parts.append(f"**À l'écran :** {description}")
    if lines:
        parts.append("\n".join(lines))
    return "\n\n".join(parts)
