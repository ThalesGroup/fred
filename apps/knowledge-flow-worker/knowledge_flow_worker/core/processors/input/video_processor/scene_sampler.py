# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Pick the few moments of a video worth showing to a vision model.

Only codec keyframes are decoded, so a one-hour video costs a few hundred small
frames rather than tens of thousands. No model is involved here: the selection is
deterministic and its size is bounded by the profile budget.
"""

from __future__ import annotations

import base64
import math
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

import numpy as np

from knowledge_flow_worker.common.structures import ProcessingConfig

_COMPARE_SIZE = (64, 36)
_FRAME_MAX_SIDE = 768
# dHash bits that may differ before two frames count as distinct (out of 64).
_DISTINCT_HASH_BITS = 6


@dataclass
class Scene:
    start: float
    end: float
    frames: list[str] = field(default_factory=list)
    """JPEG data URLs, in chronological order."""


@dataclass
class _Candidate:
    time: float
    gray: np.ndarray
    hash: int
    score: float = 0.0


def sample_scenes(path: Path, duration: float, options: ProcessingConfig.VideoSamplingConfig) -> list[Scene]:
    """Scenes covering the whole video, each with up to `frames_per_scene` distinct frames."""
    candidates = _read_candidates(path)
    if not candidates:
        return []
    duration = max(duration, candidates[-1].time)
    for previous, current in zip(candidates, candidates[1:]):
        current.score = float(np.abs(current.gray - previous.gray).mean())
    boundaries = _choose_boundaries(candidates, duration, options)
    scenes: list[Scene] = []
    picks: dict[int, Scene] = {}
    for number, first in enumerate(boundaries):
        last = boundaries[number + 1] if number + 1 < len(boundaries) else len(candidates)
        end = candidates[last].time if last < len(candidates) else duration
        scene = Scene(start=candidates[first].time, end=end)
        scenes.append(scene)
        for index in _distinct_frames(candidates, first, last, options.frames_per_scene):
            picks[index] = scene
    _attach_frames(path, picks)
    return scenes


def _read_candidates(path: Path) -> list[_Candidate]:
    import av

    candidates: list[_Candidate] = []
    with av.open(str(path)) as container:
        if not container.streams.video:
            return []
        stream = container.streams.video[0]
        stream.codec_context.skip_frame = "NONKEY"
        for frame in container.decode(stream):
            if frame.time is None:
                continue
            gray = frame.reformat(width=_COMPARE_SIZE[0], height=_COMPARE_SIZE[1], format="gray").to_ndarray().astype(np.float32) / 255.0
            candidates.append(_Candidate(time=float(frame.time), gray=gray, hash=_dhash(gray)))
    return candidates


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
        return boundaries
    # Keep the strongest changes; forced boundaries in static shots score low and go first.
    strongest = sorted(boundaries[1:], key=lambda index: candidates[index].score, reverse=True)[: budget - 1]
    return [0, *sorted(strongest)]


def _distinct_frames(candidates: list[_Candidate], first: int, last: int, limit: int) -> list[int]:
    indexes = range(first, last)
    middle = indexes[len(indexes) // 2]
    # The middle frame first, then the others from the start of the scene on.
    chosen = [middle]
    for index in indexes:
        if len(chosen) >= limit:
            break
        if all(bin(candidates[index].hash ^ candidates[other].hash).count("1") > _DISTINCT_HASH_BITS for other in chosen):
            chosen.append(index)
    return sorted(chosen)


def _attach_frames(path: Path, picks: dict[int, Scene]) -> None:
    import av

    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        stream.codec_context.skip_frame = "NONKEY"
        index = 0
        for frame in container.decode(stream):
            if frame.time is None:
                continue
            scene = picks.get(index)
            if scene is not None:
                scene.frames.append(_data_url(frame.to_image()))
            index += 1


def _dhash(gray: np.ndarray) -> int:
    rows = np.linspace(0, gray.shape[0] - 1, 8).astype(int)
    cols = np.linspace(0, gray.shape[1] - 1, 9).astype(int)
    small = gray[np.ix_(rows, cols)]
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    return int("".join("1" if bit else "0" for bit in bits), 2)


def _data_url(image) -> str:
    image = image.convert("RGB")
    image.thumbnail((_FRAME_MAX_SIDE, _FRAME_MAX_SIDE))
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
