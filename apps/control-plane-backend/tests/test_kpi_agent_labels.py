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

"""Agent labels in cross-team rankings: qualified by team, ids kept apart."""

from __future__ import annotations

from control_plane_backend.kpi.presets.team_names import build_agent_labels

TEAMS = {"team-swift": "Swiftpost", "team-lab": "Lab"}


def test_same_name_in_two_teams_is_told_apart_by_the_team() -> None:
    labels = build_agent_labels(
        {"id-aaaa1111": "Support", "id-bbbb2222": "Support"},
        {"id-aaaa1111": "team-swift", "id-bbbb2222": "team-lab"},
        TEAMS,
    )
    assert labels == {
        "id-aaaa1111": "Support - Swiftpost",
        "id-bbbb2222": "Support - Lab",
    }


def test_same_name_inside_one_team_keeps_an_id_suffix() -> None:
    labels = build_agent_labels(
        {"id-aaaa1111": "Support", "id-bbbb2222": "Support"},
        {"id-aaaa1111": "team-swift", "id-bbbb2222": "team-swift"},
        TEAMS,
    )
    assert labels == {
        "id-aaaa1111": "Support - Swiftpost (id-aaaa1)",
        "id-bbbb2222": "Support - Swiftpost (id-bbbb2)",
    }


def test_without_team_names_labels_stay_bare() -> None:
    labels = build_agent_labels(
        {"id-a": "Alpha", "id-b": "Beta"}, {"id-a": "team-swift"}, {}
    )
    assert labels == {"id-a": "Alpha", "id-b": "Beta"}


def test_unknown_team_falls_back_to_the_bare_name_and_collisions_still_split() -> None:
    labels = build_agent_labels(
        {"id-aaaa1111": "Support", "id-bbbb2222": "Support"}, {}, TEAMS
    )
    assert labels == {
        "id-aaaa1111": "Support (id-aaaa1)",
        "id-bbbb2222": "Support (id-bbbb2)",
    }
