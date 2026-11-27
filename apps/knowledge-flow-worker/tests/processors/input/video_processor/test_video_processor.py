# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

from base64 import b64decode
from fractions import Fraction
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import av
import numpy as np
import pytest
from PIL import Image

from knowledge_flow_worker.common.structures import ProcessingConfig
from knowledge_flow_worker.core.processors.input.common.image_describer import IMAGE_DESCRIPTION_UNAVAILABLE, VisionImageDescriber
from knowledge_flow_worker.core.processors.input.video_processor import scene_sampler, video_processor
from knowledge_flow_worker.core.processors.input.video_processor.scene_sampler import sample_scenes

FPS = 10


def write_video(path: Path, shots: list[tuple[int, int | np.ndarray]], gop: int = FPS) -> Path:
    """Shots of (seconds, grey level or picture), one codec keyframe every `gop` frames."""
    with av.open(str(path), "w") as container:
        stream = container.add_stream("mpeg4", rate=FPS)
        stream.width, stream.height, stream.pix_fmt = 64, 64, "yuv420p"
        stream.codec_context.gop_size = gop
        for seconds, picture in shots:
            image = np.full((64, 64, 3), picture, dtype=np.uint8) if isinstance(picture, int) else picture
            for _ in range(seconds * FPS):
                for packet in stream.encode(av.VideoFrame.from_ndarray(image, format="rgb24")):
                    container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return path


def partial(level: int, share: float) -> np.ndarray:
    """A black picture whose top `share` of rows has the given grey level."""
    image = np.zeros((64, 64, 3), dtype=np.uint8)
    image[: round(64 * share)] = level
    return image


def options(**overrides) -> ProcessingConfig.VideoSamplingConfig:
    return ProcessingConfig.VideoSamplingConfig(**{"min_scene_seconds": 3, "max_gap_seconds": 30, "max_scenes_per_minute": 2, **overrides})


def starts(scenes) -> list[int]:
    return [round(scene.start) for scene in scenes]


def test_cuts_start_scenes_and_a_still_shot_stays_one_scene(tmp_path: Path):
    video = write_video(tmp_path / "cuts.mp4", [(20, 0), (20, 255), (70, 0)])

    scenes = sample_scenes(video, 110, options(max_scenes_per_minute=3))

    # The black shot from 40 s is forced to split at 70 and 100 s, but nothing changed: one scene.
    assert starts(scenes) == [0, 20, 40]
    assert round(scenes[-1].end) == 110
    # A solid shot has one distinct frame, sent as a JPEG.
    assert all(scene.frame_count == 1 and scene.image and scene.image.startswith("data:image/jpeg;base64,") for scene in scenes)
    # At 2 per minute the white shot falls in the first 27.5 s slice and the black shot after it
    # is not new: one scene, whose image shows both shots.
    (only,) = sample_scenes(video, 110, options())
    assert only.frame_count == 2


def test_budget_keeps_the_most_novel_moment_of_each_slice(tmp_path: Path):
    video = write_video(tmp_path / "busy.mp4", [(5, 0), (5, 255), (5, 0), (5, partial(255, 0.5)), (5, 0), (5, 255)])

    assert starts(sample_scenes(video, 30, options())) == [0]  # 30 s at 2 per minute
    scenes = sample_scenes(video, 30, options(max_scenes_per_minute=8))
    # Slices of 7.5 s: back to black at 10 s is not new, the half picture at 15 s is, then white at 25 s.
    assert starts(scenes) == [0, 15, 25]
    # Two slices of 15 s: white at 25 s differs most from the black start.
    assert starts(sample_scenes(video, 30, options(max_scenes_per_minute=8, max_scenes=2))) == [0, 25]


def test_busy_passages_do_not_leave_the_rest_undescribed(tmp_path: Path):
    # Ten quick cuts in the first 40 s, then a static shot until 120 s.
    video = write_video(tmp_path / "busy-then-still.mp4", [*[(4, 255 * (number % 2)) for number in range(10)], (80, 128)])

    scenes = sample_scenes(video, 120, options())

    # One scene in each 30 s slice that brings something new; the still grey shot stays one scene.
    assert starts(scenes) == [0, 36, 70]


def test_quick_cuts_below_the_minimum_scene_do_not_start_scenes(tmp_path: Path):
    video = write_video(tmp_path / "flash.mp4", [(4, 0), (1, 255), (5, 0)])

    assert starts(sample_scenes(video, 10, options(max_scenes_per_minute=12, min_scene_seconds=6))) == [0]


def test_a_slide_shown_for_minutes_is_described_once(tmp_path: Path):
    slide = np.full((64, 64, 3), 255, dtype=np.uint8)
    next_slide = slide.copy()
    next_slide[8:24, 8:56] = 0
    video = write_video(tmp_path / "meeting.mp4", [(180, slide), (30, next_slide)])

    assert starts(sample_scenes(video, 210, options())) == [0, 180]


def test_a_slide_change_on_a_still_screen_starts_a_scene(tmp_path: Path):
    slide = np.full((64, 64, 3), 255, dtype=np.uint8)
    next_slide = slide.copy()
    next_slide[8:24, 8:56] = 0  # a new title line, about a fifth of the screen
    video = write_video(tmp_path / "slides.mp4", [(10, slide), (10, next_slide)])

    assert starts(sample_scenes(video, 20, options(max_scenes_per_minute=6))) == [0, 10]


def test_all_intra_videos_keep_one_candidate_per_second(tmp_path: Path):
    video = write_video(tmp_path / "intra.mp4", [(6, 0), (6, 255)], gop=1)

    candidates, keyframes_only = scene_sampler._read_candidates(video, 12)

    assert keyframes_only and len(candidates) == 12
    assert starts(sample_scenes(video, 12, options(max_scenes_per_minute=10))) == [0, 6]


def test_rare_keyframes_decode_every_frame(tmp_path: Path):
    # One keyframe for the whole recording, like many screen captures.
    video = write_video(tmp_path / "screen.mp4", [(10, 255), (10, partial(0, 0.3))], gop=1000)

    candidates, keyframes_only = scene_sampler._read_candidates(video, 20)

    assert not keyframes_only and len(candidates) == 20
    scenes = sample_scenes(video, 20, options(max_scenes_per_minute=6))
    assert starts(scenes) == [0, 10] and all(scene.image for scene in scenes)


def test_frames_of_a_scene_share_one_image():
    frames = [Image.new("RGB", (160, 90), colour) for colour in ("red", "green", "blue")]

    sheet = scene_sampler._contact_sheet(frames)

    assert Image.open(BytesIO(b64decode(sheet.split(",", 1)[1]))).size == (320, 180)


def test_scene_times_start_at_the_beginning_of_the_picture_stream():
    assert scene_sampler._origin(SimpleNamespace(start_time=126000, time_base=Fraction(1, 90000))) == 1.4
    assert scene_sampler._origin(SimpleNamespace(start_time=None, time_base=Fraction(1, 90000))) == 0.0


def test_budget_must_cover_forced_boundaries():
    with pytest.raises(ValueError, match="max_scenes_per_minute"):
        ProcessingConfig.VideoSamplingConfig(max_gap_seconds=30, max_scenes_per_minute=1)


class FakeVision(VisionImageDescriber):
    def __init__(self, fails: bool = False):
        super().__init__(model=None, system_prompt="")  # type: ignore[arg-type]
        self.fails = fails
        self.calls: list[tuple[int, str]] = []

    def describe_images(self, images_base64: list[str], instruction: str) -> str:
        self.calls.append((len(images_base64), instruction))
        return IMAGE_DESCRIPTION_UNAVAILABLE if self.fails else f"Scene {len(self.calls)} on screen."


def use_profile(monkeypatch: pytest.MonkeyPatch, process_images: bool, describer, **video) -> None:
    profile = ProcessingConfig.ProfileConfig(process_images=process_images, video=options(parallel_descriptions=1, **video))
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
    assert vision.calls[1][1].startswith("The 1 frame(s)") and vision.calls[1][1].endswith("[00:00:25] Deuxième plan.")


def test_a_failing_vision_model_is_dropped_after_three_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    video = write_video(tmp_path / "long.mp4", [(10, 0), (10, 255)] * 3)
    vision = FakeVision(fails=True)
    use_profile(monkeypatch, True, vision, min_scene_seconds=1, max_gap_seconds=10, max_scenes_per_minute=6)
    fake_transcript(monkeypatch)

    result = video_processor.VideoProcessor().convert_file_to_markdown(video, tmp_path / "out", "doc-1")

    markdown = Path(result["md_file"]).read_text(encoding="utf-8")
    assert markdown.count("## Scène") == 6 and "À l'écran" not in markdown
    assert len(vision.calls) == 3
    assert "6 of 6 scene(s) keep their transcript only" in caplog.text


def test_each_transcript_line_of_a_scene_starts_a_new_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    video = write_video(tmp_path / "chat.mp4", [(10, 0)])
    use_profile(monkeypatch, True, FakeVision())
    segments = [{"start": 1.0, "end": 2.0, "text": "Un."}, {"start": 3.0, "end": 4.0, "text": "Deux."}]
    result = {"text": "", "lines": [], "segments": segments, "language": "fr", "duration": 10.0}
    monkeypatch.setattr(video_processor.VideoProcessor, "_transcribe_document", lambda self, path: result)

    output = video_processor.VideoProcessor().convert_file_to_markdown(video, tmp_path / "out", "doc-1")

    assert "**Transcription :**\n\n[00:00:01] Un.  \n[00:00:03] Deux.\n" in Path(output["md_file"]).read_text(encoding="utf-8")


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


def test_unreadable_frames_keep_the_transcript(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    video = write_video(tmp_path / "damaged.mp4", [(5, 0)])
    vision = FakeVision()
    use_profile(monkeypatch, True, vision)
    fake_transcript(monkeypatch)

    def broken(*_):
        raise av.InvalidDataError(1094995529, "Invalid data found when processing input")

    monkeypatch.setattr(video_processor, "sample_scenes", broken)

    result = video_processor.VideoProcessor().convert_file_to_markdown(video, tmp_path / "out", "doc-1")

    assert Path(result["md_file"]).read_text(encoding="utf-8").startswith("# Transcript — damaged.mp4")
    assert not vision.calls and "keeps its transcript only" in caplog.text


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
