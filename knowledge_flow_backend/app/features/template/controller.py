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

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from fred_core import KeycloakUser, get_current_user

from app.common.utils import log_exception
from app.features.template.service import TemplateService
from app.features.template.structures import TemplateContent, TemplateMetadata, TemplateSummary

logger = logging.getLogger(__name__)


def _http_500(e: Exception) -> HTTPException:
    logger.exception("Templates controller error", exc_info=e)
    return HTTPException(status_code=500, detail="Internal server error")


class TemplateController:
    """
    Minimal controller for MCP-style template discovery + instantiation.

    Storage, content bytes, schema, and rendering are handled by TemplateService:
      - list_templates(family?, tags?, q?) -> List[TemplateSummary]
      - get_versions(template_id) -> List[str]
      - get_metadata(template_id, version) -> TemplateMetadata
      - instantiate(template_id, version, input_inline, target_format?) -> InstantiateResponse

    Exposed as REST (and registrable as MCP tools via operation_id):

      GET  /templates                       -> templates_list
      GET  /templates/{template_id}         -> templates_get_versions
      GET  /templates/{template_id}/{ver}   -> templates_get
      POST /templates/instantiate           -> templates_instantiate
    """

    def __init__(self, router: APIRouter):
        self.service = TemplateService()

        @router.get(
            "/templates",
            tags=["Templates"],
            summary="List templates (MCP discovery)",
            response_model=List[TemplateSummary],
            operation_id="templates_list",
        )
        def list_templates(
            family: Optional[str] = Query(None, description="Filter by family, e.g. 'reports'"),
            tags: Optional[str] = Query(None, description="Comma-separated tags"),
            q: Optional[str] = Query(None, description="Free-text search on name/description"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            try:
                tag_list = [t.strip() for t in tags.split(",")] if tags else None
                return self.service.list_templates(family=family, tags=tag_list, q=q)
            except Exception as e:
                log_exception(e)
                raise _http_500(e)

        @router.get(
            "/templates/{template_id}",
            tags=["Templates"],
            summary="Get template versions",
            response_model=TemplateSummary,
            operation_id="templates_get_versions",
        )
        def get_template_versions(
            template_id: str,
            user: KeycloakUser = Depends(get_current_user),
        ):
            try:
                versions = self.service.get_versions(template_id)
                # We also want the family/name/description: ask service for a summary or derive from first metadata
                base = self.service.get_summary(template_id)  # keep this method in TemplateService
                return TemplateSummary(
                    id=template_id,
                    family=base.family,
                    name=base.name,
                    description=base.description,
                    tags=base.tags or [],
                    versions=versions,
                )
            except self.service.NotFoundError:  # define these on your service
                raise HTTPException(status_code=404, detail="Template not found")
            except Exception as e:
                log_exception(e)
                raise _http_500(e)

        @router.get(
            "/templates/{template_id}/{version}",
            tags=["Templates"],
            summary="Get template metadata for a version",
            response_model=TemplateMetadata,
            operation_id="templates_get",
        )
        def get_template(
            template_id: str,
            version: str,
            user: KeycloakUser = Depends(get_current_user),
        ):
            try:
                return self.service.get_metadata(template_id, version)
            except self.service.NotFoundError:
                raise HTTPException(status_code=404, detail="Template/version not found")
            except Exception as e:
                log_exception(e)
                raise _http_500(e)

        @router.get(
            "/templates/{template_id}/{version}/content",
            tags=["Templates"],
            summary="Get template raw content",
            response_model=TemplateContent,
            operation_id="templates_get_content",
        )
        def get_template_content(
            template_id: str,
            version: str,
            user: KeycloakUser = Depends(get_current_user),
        ):
            try:
                meta = self.service.get_metadata(template_id, version)
                content = self.service.get_source(template_id, version)  # add this to your service
                return TemplateContent(
                    id=template_id,
                    version=version,
                    mime="text/markdown" if meta.format == "markdown" else "text/html",
                    body=content,
                )
            except self.service.NotFoundError:
                raise HTTPException(status_code=404, detail="Template/version not found")
            except Exception as e:
                log_exception(e)
                raise _http_500(e)
