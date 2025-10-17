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

import base64
import hashlib
import hmac
import time
from pathlib import Path
from typing import List

import requests

from app.common.structures import SpherePullSource
from app.core.stores.catalog.base_catalog_store import PullFileEntry
from app.core.stores.content.base_content_loader import BaseContentLoader


class SphereContentLoader(BaseContentLoader):
    def __init__(self, source: SpherePullSource, source_tag: str):
        super().__init__(source, source_tag)

        # Extract required config values from source (validated Pydantic model)
        self.base_url = source.base_url
        self.username = source.username
        self.password = source.password
        self.api_key = source.apikey
        self.parent_node_id = source.parent_node_id
        self.verify_ssl = source.verify_ssl

        self.session = requests.Session()
        if self.username is not None and self.password is not None:
            self.session.auth = (self.username, self.password)
        self.session.verify = self.verify_ssl

    def _generate_signature(self, method: str, url: str, timestamp: str) -> str:
        string_to_sign = f"{method.upper()}{url}{timestamp}{self.api_key}"
        signature = hmac.new(self.password.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256).digest()
        return base64.b64encode(signature).decode("utf-8")

    def _get_headers(self, method: str, url: str) -> dict:
        timestamp = str(int(time.time()))
        return {
            "apikey": self.api_key,
            "username": self.username,
            "content-type": "application/json",
            "X-Apim-Hash-Algorithm": "HMAC-SH512",
            "X-Timestamp": timestamp,
            "X-Signature": self._generate_signature(method, url, timestamp),
            "User-Agent": "FredSphereScanner",
        }

    def scan(self) -> List[PullFileEntry]:
        children_url = f"{self.base_url}/nodes/{self.parent_node_id}/nodes"
        headers = self._get_headers("GET", children_url)

        response = self.session.get(children_url, headers=headers)
        response.raise_for_status()

        entries = []
        for item in response.json():
            if "data" not in item or "properties" not in item["data"]:
                continue

            props = item["data"]["properties"]
            node_id = str(props.get("id"))
            name = props.get("name", "unknown")
            size = props.get("size", 0)
            modified = props.get("modified") or time.time()

            # Hash based on node ID and name (deterministic)
            hash_id = hashlib.sha256(f"{node_id}:{name}".encode()).hexdigest()

            entries.append(
                PullFileEntry(
                    path=name,
                    size=size,
                    modified_time=modified,
                    hash=hash_id,
                )
            )

        return entries

    def fetch_by_relative_path(self, relative_path: str, destination_dir: Path) -> Path:
        destination_dir.mkdir(parents=True, exist_ok=True)
        local_path = destination_dir / relative_path
        local_path.parent.mkdir(parents=True, exist_ok=True)

        download_url = f"{self.base_url}/nodes/{self.parent_node_id}/children/{relative_path}/content"
        headers = self._get_headers("GET", download_url)

        response = self.session.get(download_url, headers=headers, stream=True)
        response.raise_for_status()

        with open(local_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        return local_path
