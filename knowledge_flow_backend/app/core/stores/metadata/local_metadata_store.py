# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

import json
from pathlib import Path
from typing import List, Any

from app.core.stores.metadata.base_metadata_store import BaseMetadataStore
from app.common.structures import DocumentMetadata


class LocalMetadataStore(BaseMetadataStore):
    """
    File-based metadata store for development. Stores a list of DocumentMetadata entries in a JSON file.
    """

    def __init__(self, json_path: Path):
        self.path = json_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]")  # Start with an empty list

    def _load(self) -> List[DocumentMetadata]:
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text())
        return [DocumentMetadata(**item) for item in raw]

    def _save(self, metadata_list: List[DocumentMetadata]) -> None:
        json_list = [item.model_dump(mode="json") for item in metadata_list]
        self.path.write_text(json.dumps(json_list, indent=2))

    def _match_nested(self, item: dict, filter_dict: dict) -> bool:
        for key, value in filter_dict.items():
            if isinstance(value, dict):
                sub_item = item.get(key, {})
                if not isinstance(sub_item, dict) or not self._match_nested(sub_item, value):
                    return False
            else:
                if str(item.get(key)) != str(value):
                    return False
        return True

    def get_all_metadata(self, filters: dict) -> List[DocumentMetadata]:
        all_data = self._load()
        return [
            md for md in all_data
            if self._match_nested(md.model_dump(mode="json"), filters)
        ]

    def get_metadata_by_uid(self, document_uid: str) -> DocumentMetadata:
        for md in self._load():
            if md.document_uid == document_uid:
                return md
        return None

    def update_metadata_field(self, document_uid: str, field: str, value: Any) -> DocumentMetadata:
        data = self._load()
        for i, md in enumerate(data):
            if md.document_uid == document_uid:
                setattr(md, field, value)
                self._save(data)
                return md
        raise ValueError(f"No document found with UID {document_uid}")

    def save_metadata(self, metadata: DocumentMetadata) -> None:
        if not metadata.document_uid:
            raise ValueError("Metadata must contain a 'document_uid'")
        data = self._load()
        for i, md in enumerate(data):
            if md.document_uid == metadata.document_uid:
                data[i] = metadata  # Overwrite
                break
        else:
            data.append(metadata)
        self._save(data)

    def delete_metadata(self, metadata: DocumentMetadata) -> None:
        uid = metadata.document_uid
        data = self._load()
        new_data = [md for md in data if md.document_uid != uid]
        if len(new_data) == len(data):
            raise ValueError(f"No document found with UID {uid}")
        self._save(new_data)

    def clear(self) -> None:
        self._save([])
