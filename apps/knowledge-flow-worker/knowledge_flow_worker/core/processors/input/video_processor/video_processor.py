# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Video files: the spoken transcript plus a description of what each scene shows."""

import contextvars
import logging
import threading
from bisect import bisect_right
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from knowledge_flow_worker.application_context import get_configuration
from knowledge_flow_worker.common.processing_profile_context import get_current_processing_profile
from knowledge_flow_worker.core.processors.input.audio_processor.audio_processor import AudioProcessor, TranscriptSegment
from knowledge_flow_worker.core.processors.input.common.image_describer import IMAGE_DESCRIPTION_UNAVAILABLE, VIDEO_SCENE_DESCRIBE_PROMPT_V1, VisionImageDescriber, build_image_describer
from knowledge_flow_worker.core.processors.input.video_processor.scene_sampler import Scene, sample_scenes

logger = logging.getLogger(__name__)

# After this many failed descriptions in a row the model is treated as unusable for this video.
_MAX_FAILURES_IN_A_ROW = 3


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
        lines = [[f"[{self._format_timestamp(segment['start'])}] {segment['text']}" for segment in segments] for segments in spoken]
        descriptions = _describe_scenes(scenes, lines, describer, profile.video.parallel_descriptions)
        sections = [_scene_markdown(number, scene, lines[number - 1], descriptions[number - 1]) for number, scene in enumerate(scenes, start=1)]
        content = f"# Vidéo — {file_path.name}\n\n**Langue détectée :** {transcript['language']}  \n**Durée :** {self._format_timestamp(transcript['duration'])}\n\n" + "\n\n".join(sections) + "\n"
        md_path.write_text(content, encoding="utf-8")
        return {"doc_dir": str(output_dir), "md_file": str(md_path)}


def _describe_scenes(scenes: list[Scene], lines: list[list[str]], describer: VisionImageDescriber, parallel: int) -> list[str | None]:
    """One description per scene, None when the scene has no frame or the model failed."""
    lock = threading.Lock()
    state = {"in_a_row": 0, "failed": 0, "stopped": False}

    def describe(index: int) -> str | None:
        scene = scenes[index]
        if scene.image is None or state["stopped"]:
            return None
        excerpt = "\n".join(lines[index]) or "(no speech in this scene)"
        instruction = f"The {scene.frame_count} frame(s) of the scene, left to right then top to bottom, in order. Transcript of the scene:\n{excerpt}"
        description = describer.describe_images([scene.image], instruction)
        with lock:
            if description == IMAGE_DESCRIPTION_UNAVAILABLE:
                state["failed"] += 1
                state["in_a_row"] += 1
                state["stopped"] = state["stopped"] or state["in_a_row"] >= _MAX_FAILURES_IN_A_ROW
                return None
            state["in_a_row"] = 0
        return description

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        # Each task copies the context so its logs keep the document identifiers.
        futures = [pool.submit(contextvars.copy_context().run, describe, index) for index in range(len(scenes))]
        descriptions = [future.result() for future in futures]
    with_frames = sum(1 for scene in scenes if scene.image is not None)
    missing = with_frames - sum(1 for description in descriptions if description is not None)
    if state["stopped"]:
        logger.warning("Vision model failed %s time(s) in a row; %s of %s scene(s) keep their transcript only.", _MAX_FAILURES_IN_A_ROW, missing, with_frames)
    elif missing:
        logger.warning("Vision model failed for %s of %s scene(s); they keep their transcript only.", missing, with_frames)
    return descriptions


def _scene_markdown(number: int, scene: Scene, lines: list[str], description: str | None) -> str:
    heading = f"## Scène {number} · {AudioProcessor._format_timestamp(scene.start)} – {AudioProcessor._format_timestamp(scene.end)}"
    parts = [heading]
    if description is not None:
        parts.append(f"**À l'écran :** {description}")
    if lines:
        parts.append("**Transcription :**\n\n" + "  \n".join(lines))
    return "\n\n".join(parts)
