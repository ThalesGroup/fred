# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Offline artifacts for processor and DuckDB engine tests only."""

import shutil
from pathlib import Path

from knowledge_flow_worker.core.processors.input.common.base_input_processor import StoredObjectInfo


class TestArtifactStore:
    __test__ = False

    def __init__(self, root: Path):
        self.object_root = root
        root.mkdir(parents=True, exist_ok=True)

    def clear(self):
        shutil.rmtree(self.object_root)
        self.object_root.mkdir()

    def put_file(self, key: str, file_path: Path, *, content_type: str):
        target = self.object_root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file_path, target)
        return StoredObjectInfo(key=key, size=target.stat().st_size, file_name=target.name, content_type=content_type)

    def list_objects(self, prefix: str):
        return [
            StoredObjectInfo(key=path.relative_to(self.object_root).as_posix(), size=path.stat().st_size, file_name=path.name)
            for path in sorted(self.object_root.rglob("*"))
            if path.is_file() and path.relative_to(self.object_root).as_posix().startswith(prefix)
        ]

    def save_output(self, document_uid: str, output_dir: Path):
        shutil.copytree(output_dir, self.object_root / document_uid / "output", dirs_exist_ok=True)

    def get_output_artifact(self, key: str):
        return (self.object_root / key).read_bytes()
