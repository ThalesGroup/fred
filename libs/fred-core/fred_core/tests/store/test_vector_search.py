# Copyright Thales 2026
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

from fred_core.store.vector_search import (
    DATASET_POINTER_CHUNK_KIND,
    DEFAULT_MIN_SOURCE_SCORE_RATIO,
    VectorSearchHit,
    select_citable_sources,
)


def _hit(uid: str, score: float, chunk_kind: str | None = None) -> VectorSearchHit:
    return VectorSearchHit(
        uid=uid, title=f"Doc {uid}", content="body", score=score, chunk_kind=chunk_kind
    )


def test_select_citable_sources_excludes_dataset_pointer_regardless_of_score():
    pointer = _hit("p1", score=0.9, chunk_kind=DATASET_POINTER_CHUNK_KIND)
    real = _hit("d1", score=0.5)

    result = select_citable_sources([pointer, real], min_score_ratio=0.1)

    assert [hit.uid for hit in result] == ["d1"]


def test_select_citable_sources_excludes_hits_below_relative_score_threshold():
    strong = _hit("d1", score=0.5)
    noise = _hit("d2", score=0.05)  # 10% of the top score

    result = select_citable_sources([strong, noise], min_score_ratio=0.5)

    assert [hit.uid for hit in result] == ["d1"]


def test_select_citable_sources_keeps_hit_exactly_at_the_ratio_threshold():
    strong = _hit("d1", score=1.0)
    boundary = _hit("d2", score=0.5)  # exactly 50% of the top score

    result = select_citable_sources([strong, boundary], min_score_ratio=0.5)

    assert {hit.uid for hit in result} == {"d1", "d2"}


def test_select_citable_sources_default_ratio_matches_the_shared_constant():
    strong = _hit("d1", score=1.0)
    just_below_default = _hit("d2", score=DEFAULT_MIN_SOURCE_SCORE_RATIO - 0.01)

    result = select_citable_sources([strong, just_below_default])

    assert [hit.uid for hit in result] == ["d1"]


def test_select_citable_sources_keeps_every_real_hit_when_scores_are_close():
    a = _hit("d1", score=0.6)
    b = _hit("d2", score=0.35)  # ~58% of the top score

    result = select_citable_sources([a, b], min_score_ratio=0.5)

    assert {hit.uid for hit in result} == {"d1", "d2"}


def test_select_citable_sources_empty_input_returns_empty_tuple():
    assert select_citable_sources([]) == ()


def test_select_citable_sources_all_pointers_returns_empty_tuple():
    pointers = [
        _hit("p1", score=0.9, chunk_kind=DATASET_POINTER_CHUNK_KIND),
        _hit("p2", score=0.8, chunk_kind=DATASET_POINTER_CHUNK_KIND),
    ]

    assert select_citable_sources(pointers) == ()
