import logging
import re
import yaml
from typing import List, Optional

from app.application_context import get_app_context
from app.core.stores.files.base_file_store import BaseFileStore
from app.features.template.structures import TemplateMetadata, TemplateSummary

logger = logging.getLogger(__name__)
NAMESPACE = "templates"


def _parse_template_with_front_matter(raw: str) -> tuple[dict, str]:
    match = re.match(r"^---\n(.*?)\n---\n(.*)", raw, re.DOTALL)
    if not match:
        raise ValueError("Missing or invalid front matter in template.")
    front_matter_raw, markdown = match.groups()
    metadata = yaml.safe_load(front_matter_raw)
    return metadata, markdown


class TemplateService:
    class NotFoundError(Exception): ...

    class ValidationError(Exception): ...

    def __init__(self):
        self.store: BaseFileStore = get_app_context().get_file_store()

    def _list_template_files(self) -> List[str]:
        # List all .md files under the NAMESPACE
        return [k for k in self.store.list(NAMESPACE) if k.endswith(".yaml")]

    def _load_metadata(self, key: str) -> TemplateMetadata:
        try:
            raw = self.store.get(NAMESPACE, key).decode("utf-8")
            meta, _ = _parse_template_with_front_matter(raw)
            version = meta.get("version")
            tid = meta.get("id")
            if not tid or not version:
                raise self.ValidationError(f"Missing 'id' or 'version' in: {key}")
            return TemplateMetadata(
                id=tid,
                family=meta.get("family", "reports"),
                version=version,
                name=meta.get("name"),
                description=meta.get("description"),
                format=meta.get("format", "markdown"),
                input_schema=meta.get("input_schema", {"type": "object", "properties": {}}),
                size_bytes=len(raw.encode("utf-8")),
                checksum=None,  # Optionally compute sha256 here
            )
        except Exception as e:
            raise self.NotFoundError(f"Failed to load template metadata from {key}: {e}")

    def list_templates(
        self,
        family: Optional[str] = None,
        tags: Optional[List[str]] = None,
        q: Optional[str] = None,
    ) -> List[TemplateSummary]:
        result = {}
        for key in self._list_template_files():
            try:
                meta = self._load_metadata(key)
                if family and meta.family != family:
                    continue
                if tags and not set(tags).issubset(set(meta.dict().get("tags", []))):
                    continue
                if q:
                    hay = " ".join([meta.id, meta.name or "", meta.description or ""]).lower()
                    if q.lower() not in hay:
                        continue
                summary = result.setdefault(
                    meta.id,
                    TemplateSummary(
                        id=meta.id,
                        family=meta.family,
                        name=meta.name,
                        description=meta.description,
                        versions=[],
                        tags=meta.dict().get("tags", []),
                    ),
                )
                summary.versions.append(meta.version)
            except Exception as e:
                logger.warning(f"Skipping template file '{key}' due to error: {e}")
        for s in result.values():
            s.versions.sort()
        return list(result.values())

    def get_versions(self, template_id: str) -> List[str]:
        versions = []
        for key in self._list_template_files():
            try:
                meta = self._load_metadata(key)
                if meta.id == template_id:
                    versions.append(meta.version)
            except Exception as e:
                logger.warning(f"Skipping template file '{key}' during version lookup: {e}")
        if not versions:
            raise self.NotFoundError(f"Template '{template_id}' not found.")
        return sorted(versions)

    def get_summary(self, template_id: str) -> TemplateSummary:
        for summary in self.list_templates():
            if summary.id == template_id:
                return summary
        raise self.NotFoundError(f"Template '{template_id}' not found.")

    def get_metadata(self, template_id: str, version: str) -> TemplateMetadata:
        for key in self._list_template_files():
            try:
                meta = self._load_metadata(key)
                if meta.id == template_id and meta.version == version:
                    return meta
            except Exception as e:
                logger.warning(f"Skipping template file '{key}' during metadata lookup: {e}")
        raise self.NotFoundError(f"Template '{template_id}' version '{version}' not found.")

    def get_source(self, template_id: str, version: str) -> str:
        for key in self._list_template_files():
            try:
                meta = self._load_metadata(key)
                if meta.id == template_id and meta.version == version:
                    raw = self.store.get(NAMESPACE, key).decode("utf-8")
                    _, markdown = _parse_template_with_front_matter(raw)
                    return markdown
            except Exception as e:
                logger.warning(f"Skipping template file '{key}' during markdown retrieval: {e}")
        raise self.NotFoundError(f"Markdown source not found for template '{template_id}' version '{version}'.")
