# app/tests/test_utils/fake_processors.py

from pathlib import Path
import pandas as pd

from app.core.processors.input.common.base_input_processor import BaseMarkdownProcessor, BaseTabularProcessor


class TestMarkdownProcessor(BaseMarkdownProcessor):
    def check_file_validity(self, file_path: Path) -> bool:
        return True

    def extract_file_metadata(self, file_path: Path) -> dict:
        return {"title": "test-markdown"}

    def convert_file_to_markdown(self, file_path: Path, output_dir: Path) -> dict:
        output_path = output_dir / "file.md"
        output_path.write_text("# Test Markdown Content")
        return {"markdown_path": str(output_path)}


class TestTabularProcessor(BaseTabularProcessor):
    def check_file_validity(self, file_path: Path) -> bool:
        return True

    def extract_file_metadata(self, file_path: Path) -> dict:
        return {"title": "test-tabular"}

    def convert_file_to_table(self, file_path: Path) -> pd.DataFrame:
        return pd.DataFrame({"col1": [1, 2], "col2": ["A", "B"]})
