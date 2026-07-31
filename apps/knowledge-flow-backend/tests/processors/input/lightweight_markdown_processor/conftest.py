# Copyright Thales 2025
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

"""Shared fixtures for the lite PDF processors' fitz.Document lifecycle regression tests."""

from pathlib import Path

import fitz
import pytest


@pytest.fixture
def sample_pdf_file() -> Path:
    return Path(__file__).parent.parent / "pdf_markdown_processor" / "assets" / "sample.pdf"


class FitzOpenSpy:
    """Wraps the real `fitz.open` so tests can assert every Document it returns
    gets closed. Assigning to `fitz.open` (not just `PyMuPdfExtractor`'s local
    binding) works because every `import fitz` shares the same module object."""

    def __init__(self) -> None:
        self.opened: list[fitz.Document] = []
        self._real_open = fitz.open

    def __call__(self, *args, **kwargs) -> fitz.Document:
        doc = self._real_open(*args, **kwargs)
        self.opened.append(doc)
        return doc


@pytest.fixture
def fitz_open_spy(monkeypatch: pytest.MonkeyPatch) -> FitzOpenSpy:
    spy = FitzOpenSpy()
    monkeypatch.setattr(fitz, "open", spy)
    return spy
