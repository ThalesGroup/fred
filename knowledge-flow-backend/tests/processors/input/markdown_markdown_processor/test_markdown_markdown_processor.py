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

# tests/test_sample_markdown_processor.py

import tempfile
from pathlib import Path

from knowledge_flow_backend.core.processors.input.markdown_markdown_processor.markdown_markdown_processor import MarkdownMarkdownProcessor
from knowledge_flow_backend.core.processors.input.text_markdown_processor.text_markdown_processor import TextMarkdownProcessor


def test_sample_markdown_processor_end_to_end():
    processor = TextMarkdownProcessor()
    test_content = """# Sample Markdown Document

This is a **bold** statement, and _this_ is italic.

## List Example

- Item 1
- Item 2
  - Subitem

## Code Block

```python
def hello_world():
    print("Hello, Markdown!")
```
> This is a blockquote.

"""

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        input_file = temp_path / "sample.md"
        output_dir = temp_path / "output"

        input_file.write_text(test_content, encoding="utf-8")

        # Check file validity
        assert processor.check_file_validity(input_file)

        # Metadata
        metadata = processor.process_metadata(input_file, [], "uploads")
        assert metadata.document_name == "sample.md"
        assert metadata.document_uid
        output_dir.mkdir(parents=True, exist_ok=True)  # Ensure output_dir exists
        # Convert to markdown
        result = processor.convert_file_to_markdown(input_file, output_dir, metadata.document_uid)
        output_file_path = Path(result["md_file"])
        assert output_file_path.exists()
        content_written = output_file_path.read_text(encoding="utf-8")
        assert "# Sample Markdown Document" in content_written
        assert "```python" in content_written
        assert "> This is a blockquote." in content_written


def test_markdown_markdown_processor_non_utf8():
    """Regression for #1898: a non-UTF-8 (Windows-1252) .md file must not crash ingestion."""
    processor = MarkdownMarkdownProcessor()
    # "é" / "à" encode to bytes 0xe9 / 0xe0 which are invalid UTF-8.
    test_content = "# Réunion\n\nDétails du café à Paris."

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        input_file = temp_path / "note.md"
        output_dir = temp_path / "output"

        input_file.write_bytes(test_content.encode("cp1252"))
        output_dir.mkdir(parents=True, exist_ok=True)

        result = processor.convert_file_to_markdown(input_file, output_dir, "uid")

        content_written = Path(result["md_file"]).read_text(encoding="utf-8")
        assert "# Réunion" in content_written
        assert "café à Paris" in content_written
