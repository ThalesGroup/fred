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

import json
from pathlib import Path
from typing import List, Dict, Any

from knowledge_flow_app.core.stores.base_metadata_store import BaseMetadataStore



@staticmethod
def _match_nested(item: dict, filter_dict: dict) -> bool:
    """
    Recursively match nested filters inside a dictionary.
    """
    for key, value in filter_dict.items():
        if isinstance(value, dict):
            # Nested dict -> must go deeper
            sub_item = item.get(key, {})
            if not isinstance(sub_item, dict) or not _match_nested(sub_item, value):
                return False
        else:
            # Final key: compare
            if str(item.get(key)) != str(value):
                return False
    return True


class LocalMetadataStore(BaseMetadataStore):
    """
    A simple file-based metadata store implementation that persists metadata in a local JSON file.

    This class is primarily designed for local development or lightweight deployments where
    a full database is not required. It implements the BaseMetadataStore interface and stores
    a list of metadata records, each represented as a dictionary.

    Metadata is expected to include a unique 'document_uid' field to identify individual entries.

    Example metadata structure:
    {
        "document_uid": "abc123",
        "document_name": "example.md",
        "date_added": "2024-04-25"
    }

    Each method loads and saves the entire dataset from/to disk, so this implementation is not
    optimized for large-scale or concurrent usage.
    """

    def __init__(self, json_path: Path):
        """
        Initialize the store with the path to a JSON file.

        :param json_path: Path to the metadata file.
        """
        self.path = json_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]")  # Initialize empty list if file doesn't exist

    def _load(self) -> List[Dict[str, Any]]:
        """
        Load the full metadata list from the JSON file.

        :return: List of metadata dictionaries.
        """
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text())

    def _save(self, data: List[Dict[str, Any]]) -> None:
        """
        Save the full metadata list to the JSON file.

        :param data: List of metadata dictionaries to persist.
        """
        self.path.write_text(json.dumps(data, indent=2))

    def get_all_metadata(self, filters: dict) -> List[dict]:
        """
            Return all metadata entries matching the given (possibly nested) filters.
            The filters are applied recursively to the metadata dictionaries.
            :param filters: Dictionary of filters to apply.
        :return: List of metadata dictionaries that match the filters.
        """
        all_data = self._load()
        return [item for item in all_data if _match_nested(item, filters)]

    def get_metadata_by_uid(self, document_uid: str) -> dict:
        """
        Retrieve a single metadata entry by its unique document UID.

        :param document_uid: Unique identifier for the document.
        :return: The matching metadata dictionary, or None if not found.
        """
        all_data = self._load()
        return next((item for item in all_data if item.get("document_uid") == document_uid), None)

    def update_metadata_field(self, document_uid: str, field: str, value: Any) -> dict:
        """
        Update a single field in a metadata entry by its document UID.

        :param document_uid: The UID of the document to update.
        :param field: The field name to update.
        :param value: The new value to assign.
        :return: The updated metadata dictionary.
        :raises ValueError: If no matching document is found.
        """
        data = self._load()
        for item in data:
            if item.get("document_uid") == document_uid:
                item[field] = value
                self._save(data)
                return item
        raise ValueError(f"No document found with UID {document_uid}")

    def save_metadata(self, metadata: dict) -> None:
        """
        Add or replace a full metadata entry in the store.

        - If an entry with the same UID exists, it is overwritten.
        - If not, the metadata is added as a new entry.

        :param metadata: The full metadata dictionary.
        :raises ValueError: If 'document_uid' is missing.
        """
        document_uid = metadata.get("document_uid")
        if not document_uid:
            raise ValueError("Metadata must contain a 'document_uid' field.")

        data = self._load()
        for i, item in enumerate(data):
            if item.get("document_uid") == document_uid:
                data[i] = metadata  # Overwrite existing
                break
        else:
            data.append(metadata)  # Add new entry
        self._save(data)

    def delete_metadata(self, metadata: dict) -> None:
        """
        Delete a metadata entry from the store based on its 'document_uid'.

        :param metadata: The metadata dictionary to delete. Must include 'document_uid'.
        :raises ValueError: If 'document_uid' is missing or not found in the store.
        """
        document_uid = metadata.get("document_uid")
        if not document_uid:
            raise ValueError("Cannot delete metadata without 'document_uid'")

        data = self._load()
        original_len = len(data)
        data = [item for item in data if item.get("document_uid") != document_uid]

        if len(data) == original_len:
            raise ValueError(f"No document found with UID {document_uid}")

        self._save(data)
