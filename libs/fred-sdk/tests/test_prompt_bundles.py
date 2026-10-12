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

from pathlib import Path

import pytest
from fred_sdk import load_agent_prompt_markdown, load_packaged_markdown
from fred_sdk.resources import packaged


@pytest.mark.parametrize("subdir", [("prompts",), ("nested", "prompts")])
def test_agent_prompt_loader_returns_raw_resource_without_appended_instructions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, subdir: tuple[str, ...]
) -> None:
    folder = tmp_path.joinpath(*subdir)
    folder.mkdir(parents=True)
    content = "# Agent prompt\n\nReply in the requested language.\n"
    (folder / "system.md").write_text(content)
    monkeypatch.setattr(packaged, "files", lambda package: tmp_path)
    assert (
        load_packaged_markdown(package="fixture", path_parts=(*subdir, "system.md"))
        == content
    )
    assert (
        load_agent_prompt_markdown(
            package="fixture", file_name="system.md", prompts_subdir=subdir
        )
        == content
    )


def test_missing_agent_prompt_fails_clearly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(packaged, "files", lambda package: tmp_path)
    with pytest.raises(RuntimeError, match="Missing packaged Markdown resource"):
        load_agent_prompt_markdown(package="fixture", file_name="missing.md")
