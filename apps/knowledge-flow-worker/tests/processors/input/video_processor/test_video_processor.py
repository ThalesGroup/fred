# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from types import SimpleNamespace

import av
import numpy as np
import pytest

from knowledge_flow_worker.common.structures import ProcessingConfig
from knowledge_flow_worker.core.processors.input.common.image_describer import VisionImageDescriber
from knowledge_flow_worker.core.processors.input.video_processor import video_processor
from knowledge_flow_worker.core.processors.input.video_processor.scene_sampler import sample_scenes

FPS = 10


def write_video(path: Path, shots: list[tuple[int, int]]) -> Path:
    """Solid-colour shots of (seconds, grey level), one codec keyframe per second."""
    with av.open(str(path), "w") as container:
        stream = container.add_stream("mpeg4", rate=FPS)
        stream.width, stream.height, stream.pix_fmt = 64, 64, "yuv420p"
        stream.codec_context.gop_size = FPS
        for seconds, level in shots:
            image = np.full((64, 64, 3), level, dtype=np.uint8)
            for _ in range(seconds * FPS):
                for packet in stream.encode(av.VideoFrame.from_ndarray(image, format="rgb24")):
                    container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return path


def options(**overrides) -> ProcessingConfig.VideoSamplingConfig:
    return ProcessingConfig.VideoSamplingConfig(**{"min_scene_seconds": 3, "max_gap_seconds": 30, "max_scenes_per_minute": 2, **overrides})


def starts(scenes) -> list[int]:
    return [round(scene.start) for scene in scenes]


def test_cuts_start_scenes_and_static_shots_get_one_every_max_gap(tmp_path: Path):
    video = write_video(tmp_path / "cuts.mp4", [(20, 0), (20, 255), (70, 0)])

    scenes = sample_scenes(video, 110, options(max_scenes_per_minute=3))

    assert starts(scenes) == [0, 20, 40, 70, 100]
    assert round(scenes[-1].end) == 110
    # A solid shot has one distinct frame, sent as a JPEG.
    assert all(len(scene.frames) == 1 and scene.frames[0].startswith("data:image/jpeg;base64,") for scene in scenes)
    # At 2 per minute the budget is 4: the weakest forced boundary goes first.
    assert starts(sample_scenes(video, 110, options())) == [0, 20, 40, 70]


def test_budget_keeps_the_strongest_changes(tmp_path: Path):
    video = write_video(tmp_path / "busy.mp4", [(5, 0), (5, 255), (5, 0), (5, 128), (5, 0), (5, 255)])

    assert starts(sample_scenes(video, 30, options())) == [0]  # 30 s at 2 per minute
    scenes = sample_scenes(video, 30, options(max_scenes_per_minute=8))
    assert starts(scenes) == [0, 5, 10, 25]  # the black/grey cuts are the weakest
    assert starts(sample_scenes(video, 30, options(max_scenes_per_minute=8, max_scenes=2))) == [0, 5]


def test_quick_cuts_below_the_minimum_scene_do_not_start_scenes(tmp_path: Path):
    video = write_video(tmp_path / "flash.mp4", [(4, 0), (1, 255), (5, 0)])

    assert starts(sample_scenes(video, 10, options(max_scenes_per_minute=12, min_scene_seconds=6))) == [0]


def test_budget_must_cover_forced_boundaries():
    with pytest.raises(ValueError, match="max_scenes_per_minute"):
        ProcessingConfig.VideoSamplingConfig(max_gap_seconds=30, max_scenes_per_minute=1)


class FakeVision(VisionImageDescriber):
    def __init__(self):
        super().__init__(model=None, system_prompt="")  # type: ignore[arg-type]
        self.calls: list[tuple[int, str]] = []

    def describe_images(self, images_base64: list[str], instruction: str) -> str:
        self.calls.append((len(images_base64), instruction))
        return f"Scene {len(self.calls)} on screen."


def use_profile(monkeypatch: pytest.MonkeyPatch, process_images: bool, describer) -> None:
    profile = ProcessingConfig.ProfileConfig(process_images=process_images, video=options())
    processing = SimpleNamespace(normalize_profile=lambda value: value, get_profile_config=lambda _: profile)
    monkeypatch.setattr(video_processor, "get_configuration", lambda: SimpleNamespace(processing=processing))
    monkeypatch.setattr(video_processor, "get_current_processing_profile", lambda: "rich")
    monkeypatch.setattr(video_processor, "build_image_describer", lambda **_: describer)


def fake_transcript(monkeypatch: pytest.MonkeyPatch) -> None:
    segments = [{"start": 2.0, "end": 6.0, "text": "Bonjour."}, {"start": 25.0, "end": 29.0, "text": "Deuxième plan."}]
    result = {"text": "", "lines": ["[00:00:02] Bonjour.", "[00:00:25] Deuxième plan."], "segments": segments, "language": "fr", "duration": 40.0}
    monkeypatch.setattr(video_processor.VideoProcessor, "_transcribe_document", lambda self, path: result)


def test_rich_profile_interleaves_scene_descriptions_with_the_transcript(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    video = write_video(tmp_path / "interview.mp4", [(20, 0), (20, 255)])
    vision = FakeVision()
    use_profile(monkeypatch, True, vision)
    fake_transcript(monkeypatch)

    result = video_processor.VideoProcessor().convert_file_to_markdown(video, tmp_path / "out", "doc-1")

    markdown = Path(result["md_file"]).read_text(encoding="utf-8")
    assert markdown == (
        "# Vidéo — interview.mp4\n\n**Langue détectée :** fr  \n**Durée :** 00:00:40\n\n"
        "## Scène 1 · 00:00:00 – 00:00:20\n\n**À l'écran :** Scene 1 on screen.\n\n**Transcription :**\n\n[00:00:02] Bonjour.\n\n"
        "## Scène 2 · 00:00:20 – 00:00:40\n\n**À l'écran :** Scene 2 on screen.\n\n**Transcription :**\n\n[00:00:25] Deuxième plan.\n"
    )
    assert [count for count, _ in vision.calls] == [1, 1]
    assert vision.calls[1][1].endswith("[00:00:25] Deuxième plan.")


@pytest.mark.parametrize(("process_images", "describer"), [(False, FakeVision()), (True, None)])
def test_without_image_description_the_video_keeps_its_transcript(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, process_images, describer):
    video = write_video(tmp_path / "talk.mp4", [(5, 0)])
    use_profile(monkeypatch, process_images, describer)
    fake_transcript(monkeypatch)

    result = video_processor.VideoProcessor().convert_file_to_markdown(video, tmp_path / "out", "doc-1")

    markdown = Path(result["md_file"]).read_text(encoding="utf-8")
    assert markdown.startswith("# Transcript — talk.mp4") and "Scène" not in markdown


def test_a_silent_video_is_described_without_a_transcript(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    video = write_video(tmp_path / "screen.mp4", [(10, 0)])
    use_profile(monkeypatch, True, FakeVision())
    monkeypatch.setattr(video_processor.VideoProcessor, "transcribe_file_to_text", lambda *_: pytest.fail("no sound track to transcribe"))

    result = video_processor.VideoProcessor().convert_file_to_markdown(video, tmp_path / "out", "doc-1")

    markdown = Path(result["md_file"]).read_text(encoding="utf-8")
    assert "## Scène 1 · 00:00:00 – 00:00:10\n\n**À l'écran :** Scene 1 on screen.\n" in markdown
    assert "(no speech in this scene)" not in markdown


def test_an_audio_only_container_keeps_the_transcript_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    audio = tmp_path / "voice.webm"
    with av.open(str(audio), "w") as container:
        stream = container.add_stream("libopus", rate=48000)
        frame = av.AudioFrame.from_ndarray(np.zeros((1, 960), dtype=np.float32), format="flt", layout="mono")
        frame.sample_rate = 48000
        for packet in [*stream.encode(frame), *stream.encode()]:
            container.mux(packet)
    vision = FakeVision()
    use_profile(monkeypatch, True, vision)
    fake_transcript(monkeypatch)

    result = video_processor.VideoProcessor().convert_file_to_markdown(audio, tmp_path / "out", "doc-1")

    assert Path(result["md_file"]).read_text(encoding="utf-8").startswith("# Transcript — voice.webm")
    assert not vision.calls
