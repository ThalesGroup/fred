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

import requests
from typing import Any, Dict, List, Optional, Sequence, Iterable
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pydantic import TypeAdapter
from app.common.resources.structures import Resource, ResourceKind

_RESOURCES = TypeAdapter(List[Resource])


def _session_with_retries() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=0.3,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


class ResourceClient:
    def __init__(
        self,
        base_url: str,
        timeout_s: int = 10,
        session: Optional[requests.Session] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.session = session or _session_with_retries()

    def list_resources(
        self,
        *,
        kind: Optional[ResourceKind] = None,
        tags: Sequence[str] = [],
        payload_overrides: Optional[Dict[str, Any]] = None,
    ) -> List[Resource]:
        """
        Fetch resources from the API, filtered by kind and tags.

        NOTE: tags are mandatory. An empty list will raise a ValueError.
        """
        if not tags:
            raise ValueError("tags must be provided and cannot be empty")

        payload: Dict[str, Any] = {}
        if kind:
            payload["kind"] = kind.value if isinstance(kind, ResourceKind) else kind
        if tags:
            payload["tags"] = list(tags)
        if payload_overrides:
            payload.update(payload_overrides)

        r = self.session.get(
            f"{self.base_url}/resources", params=payload, timeout=self.timeout_s
        )
        r.raise_for_status()
        raw = r.json()
        if not isinstance(raw, Iterable):
            return []
        return _RESOURCES.validate_python(raw)
