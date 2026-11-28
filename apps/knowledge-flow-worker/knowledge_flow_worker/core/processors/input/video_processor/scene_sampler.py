# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Pick the few moments of a video worth showing to a vision model.

Codec keyframes are decoded first, so a one-hour video usually costs a few hundred
small frames rather than tens of thousands. Recordings with rare keyframes, such as
screen captures, are decoded in full instead. Either way at most one candidate per
second is kept. No model is involved here: the selection is deterministic and its
size is bounded by the profile budget.
"""

from __future__ import annotations

import base64
import math
import statistics
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import numpy as np

from knowledge_flow_worker.common.structures import ProcessingConfig

_COMPARE_SIZE = (96, 54)
# Grey levels (out of 255) a pixel must move by to count as changed; ignores compression noise.
_PIXEL_CHANGE = 26
# Candidates closer than this are skipped, so all-intra codecs (MJPEG, ProRes) stay cheap.
_CANDIDATE_SPACING_SECONDS = 1.0
# Above this median keyframe interval, keyframes alone would miss slide changes.
_SPARSE_KEYFRAME_SECONDS = 2.0
_CELL_MAX_SIDE = 640


@dataclass
class Scene:
    start: float
    end: float
    frame_count: int = 0
    image: str | None = None
    """One JPEG data URL holding the scene's frames, left to right then top to bottom."""


@dataclass
class _Candidate:
    time: float
    pts: int
    gray: np.ndarray
    score: float = 0.0


def sample_scenes(path: Path, duration: float, options: ProcessingConfig.VideoSamplingConfig) -> list[Scene]:
    """Scenes covering the whole video, each with up to `frames_per_scene` distinct frames."""
    candidates, keyframes_only = _read_candidates(path, duration)
    if not candidates:
        return []
    duration = max(duration, candidates[-1].time)
    boundaries = _choose_boundaries(candidates, duration, options)
    scenes: list[Scene] = []
    picks: dict[int, Scene] = {}
    for number, first in enumerate(boundaries):
        last = boundaries[number + 1] if number + 1 < len(boundaries) else len(candidates)
        end = candidates[last].time if last < len(candidates) else duration
        scene = Scene(start=candidates[first].time, end=end)
        scenes.append(scene)
        for index in _distinct_frames(candidates, first, last, options):
            picks[candidates[index].pts] = scene
    _attach_frames(path, picks, keyframes_only)
    return scenes


def _read_candidates(path: Path, duration: float) -> tuple[list[_Candidate], bool]:
    candidates, keyframe_times = _decode_candidates(path, keyframes_only=True)
    if keyframe_times is None:
        return [], True
    gaps = [later - earlier for earlier, later in zip(keyframe_times, keyframe_times[1:])]
    sparse = statistics.median(gaps) > _SPARSE_KEYFRAME_SECONDS if gaps else duration > _SPARSE_KEYFRAME_SECONDS
    if not sparse:
        return candidates, True
    candidates, _ = _decode_candidates(path, keyframes_only=False)
    return candidates, False


def _decode_candidates(path: Path, keyframes_only: bool) -> tuple[list[_Candidate], list[float] | None]:
    """Candidates one second apart at least, and every decoded frame time; None without a picture stream."""
    import av

    candidates: list[_Candidate] = []
    times: list[float] = []
    previous: np.ndarray | None = None
    with av.open(str(path)) as container:
        if not container.streams.video:
            return [], None
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        if keyframes_only:
            stream.codec_context.skip_frame = "NONKEY"
        origin = _origin(stream)
        for frame in container.decode(stream):
            if frame.time is None or frame.pts is None:
                continue
            time = float(frame.time) - origin
            times.append(time)
            if candidates and time - candidates[-1].time < _CANDIDATE_SPACING_SECONDS:
                continue
            gray = frame.reformat(width=_COMPARE_SIZE[0], height=_COMPARE_SIZE[1], format="gray").to_ndarray()
            score = 0.0 if previous is None else _changed_share(gray, previous)
            candidates.append(_Candidate(time=time, pts=frame.pts, gray=gray, score=score))
            previous = gray
    return candidates, times


def _choose_boundaries(candidates: list[_Candidate], duration: float, options: ProcessingConfig.VideoSamplingConfig) -> list[int]:
    boundaries = [0]
    for index in range(1, len(candidates)):
        elapsed = candidates[index].time - candidates[boundaries[-1]].time
        if elapsed < options.min_scene_seconds:
            continue
        if candidates[index].score > options.scene_threshold or elapsed >= options.max_gap_seconds:
            boundaries.append(index)
    budget = max(1, math.ceil(duration / 60 * options.max_scenes_per_minute))
    if options.max_scenes is not None:
        budget = min(budget, options.max_scenes)
    if len(boundaries) <= budget:
        return _merge_unchanged(candidates, boundaries, options.scene_threshold)
    # Spread the budget over time: at most one new scene per equal slice, at the moment
    # that differs most from the current scene. Keeping only the strongest changes overall
    # would cluster them in busy passages and leave minutes of the video undescribed.
    slice_seconds = duration / budget
    kept = [0]
    for number in range(1, budget):
        low, high = number * slice_seconds, (number + 1) * slice_seconds
        start = candidates[kept[-1]]
        in_slice = [index for index in boundaries if low <= candidates[index].time < high and candidates[index].time - start.time >= options.min_scene_seconds]
        novelty = {index: _changed_share(candidates[index].gray, start.gray) for index in in_slice}
        best = max(novelty, key=lambda index: novelty[index], default=None)
        if best is not None and novelty[best] > options.scene_threshold:
            kept.append(best)
    return kept


def _merge_unchanged(candidates: list[_Candidate], boundaries: list[int], threshold: float) -> list[int]:
    """Drop boundaries whose picture matches the start of the current scene.

    A slide shown for minutes, or a static shot, then gets one description followed
    by everything said meanwhile, instead of the same picture described every
    `max_gap_seconds`. Slow changes still split: the comparison is with the scene start.
    """
    merged = boundaries[:1]
    for index in boundaries[1:]:
        if _changed_share(candidates[index].gray, candidates[merged[-1]].gray) > threshold:
            merged.append(index)
    return merged


def _changed_share(gray: np.ndarray, other: np.ndarray) -> float:
    """Share of pixels that changed: a slide change or a cut between similar shots still counts."""
    return float((np.abs(gray.astype(np.int16) - other.astype(np.int16)) > _PIXEL_CHANGE).mean())


def _distinct_frames(candidates: list[_Candidate], first: int, last: int, options: ProcessingConfig.VideoSamplingConfig) -> list[int]:
    indexes = range(first, last)
    middle = indexes[len(indexes) // 2]
    # The middle frame first, then the others from the start of the scene on.
    chosen = [middle]
    for index in indexes:
        if len(chosen) >= options.frames_per_scene:
            break
        if all(_changed_share(candidates[index].gray, candidates[other].gray) > options.scene_threshold for other in chosen):
            chosen.append(index)
    return sorted(chosen)


def _attach_frames(path: Path, picks: dict[int, Scene], keyframes_only: bool) -> None:
    import av

    frames: dict[int, list] = {}
    remaining = set(picks)
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        if keyframes_only:
            stream.codec_context.skip_frame = "NONKEY"
        for frame in container.decode(stream):
            if frame.pts not in remaining:
                continue
            remaining.discard(frame.pts)
            # Shrink at once: full-size frames of a long 1080p video would not fit in memory.
            image = frame.to_image().convert("RGB")
            image.thumbnail((_CELL_MAX_SIDE, _CELL_MAX_SIDE))
            frames.setdefault(id(picks[frame.pts]), []).append(image)
            if not remaining:
                break
    for scene in {id(scene): scene for scene in picks.values()}.values():
        images = frames.get(id(scene), [])
        scene.frame_count = len(images)
        scene.image = _contact_sheet(images) if images else None


def _origin(stream) -> float:
    """Start of the picture stream, so scene times share the transcript's zero."""
    if stream.start_time is None or stream.time_base is None:
        return 0.0
    return float(stream.start_time * stream.time_base)


def _contact_sheet(images: list) -> str:
    """One image for all frames: works with models that accept a single image per request."""
    from PIL import Image

    cells = images
    columns = 1 if len(cells) == 1 else 2 if len(cells) <= 4 else 3
    rows = math.ceil(len(cells) / columns)
    width, height = max(cell.width for cell in cells), max(cell.height for cell in cells)
    sheet = Image.new("RGB", (columns * width, rows * height), "black")
    for index, cell in enumerate(cells):
        sheet.paste(cell, ((index % columns) * width, (index // columns) * height))
    buffer = BytesIO()
    sheet.save(buffer, format="JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
