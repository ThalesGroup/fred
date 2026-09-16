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

"""Text width measurement: one ruler for the capacity estimate, the overflow
control and the no-wrap box sizing."""

from __future__ import annotations

from fred_capability_ppt_filler import text_metrics


def test_a_wide_string_measures_wider_than_a_narrow_one_of_the_same_length():
    # What the per-character estimate could not see.
    assert text_metrics.width_em("WWWWW") > text_metrics.width_em("iiiii")


def test_width_grows_with_the_text_and_an_empty_string_is_zero():
    assert text_metrics.width_em("") == 0.0
    assert text_metrics.width_em("aa") > text_metrics.width_em("a")


def test_an_average_character_is_a_plausible_fraction_of_the_size():
    assert 0.3 < text_metrics.char_em() < 0.9


def test_without_a_font_the_conservative_estimate_stands_in(monkeypatch):
    monkeypatch.setattr(text_metrics, "_font", lambda *_args, **_kw: None)
    assert text_metrics.width_em("hello") == 5 * text_metrics.FALLBACK_CHAR_EM
    assert text_metrics.chars_per_line(100, 10, None, False) == int(
        100 / (10 * text_metrics.FALLBACK_CHAR_EM)
    )


def test_a_missing_font_file_never_raises(monkeypatch):
    monkeypatch.setattr(text_metrics, "_font_file", lambda *_args, **_kw: "/nope.ttf")
    assert text_metrics.width_em("hello", "Nothing Here Either") > 0


def test_a_family_name_is_not_read_as_fontconfig_syntax(monkeypatch):
    seen: list[list[str]] = []

    class _Done:
        stdout = "/usr/share/fonts/x.ttf"

    def fake_run(argv, **_kwargs):
        seen.append(argv)
        return _Done()

    monkeypatch.setattr(text_metrics.subprocess, "run", fake_run)
    text_metrics._font_file.cache_clear()
    try:
        text_metrics._font_file("Gotham-12", True)
    finally:
        text_metrics._font_file.cache_clear()
    assert seen[0][-1] == "Gotham\\-12:bold"
