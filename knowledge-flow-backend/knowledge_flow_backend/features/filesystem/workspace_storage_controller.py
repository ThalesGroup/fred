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

"""
HTTP controller exposing **three** explicit storage scopes backed by UserStorage:
- User exchange:          /storage/user/...
- Agent configuration:    /storage/agent-config/{agent_id}/...
- Agent per-user notes:   /storage/agent-user/{agent_id}/{target_user_id}/...

All endpoints remain bearer-protected (Resource.FILES). No anonymous links.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Request, Response, UploadFile
from fred_core import Action, KeycloakUser, Resource, authorize_or_raise, get_current_user

from knowledge_flow_backend.features.filesystem.workspace_storage_service import (
    WorkspaceStorageService,
)

logger = logging.getLogger(__name__)


class WorkspaceStorageController:
    """
    Single controller exposing three clear scopes while reusing the same service.
    """

    @staticmethod
    def _build_download_url(request: Request, suffix: str) -> str:
        """
        Compose a full download URL for the given path suffix (e.g. 'storage/user/foo.txt')
        based on the incoming request host + API prefix.
        """
        base = str(request.base_url).rstrip("/")
        segments = [p for p in request.url.path.split("/") if p]
        # Expect path like knowledge-flow/v1/...
        api_prefix = "/".join(segments[:2]) if len(segments) >= 2 else ""
        prefix = f"{base}/{api_prefix}".rstrip("/")
        return f"{prefix}/{suffix.lstrip('/')}"

    @staticmethod
    def _meta_to_dict(meta):
        """
        Normalize FilesystemResourceInfoResult (dataclass) or dict-like meta to a serializable dict.
        """
        if meta is None:
            return {}
        try:
            d = asdict(meta)
            if "type" in d and hasattr(d["type"], "value"):
                d["type"] = d["type"].value
            return d
        except Exception:
            try:
                return dict(meta)
            except Exception:
                # Last resort: capture known fields
                return {
                    "path": getattr(meta, "path", None),
                    "size": getattr(meta, "size", None),
                    "type": getattr(meta, "type", None),
                    "modified": getattr(meta, "modified", None),
                }

    @staticmethod
    def _filter_files_only(items):
        def is_dir(item):
            # Accept either dicts or FilesystemResourceInfoResult
            t = getattr(item, "type", None)
            if t is None and hasattr(item, "get"):
                t = item.get("type")
            if t is None:
                return False
            t_str = str(t).lower()
            return "directory" in t_str

        return [item for item in items if not is_dir(item)]

    def __init__(self, router: APIRouter):
        self.service = WorkspaceStorageService()
        self._register_routes(router)

    # ------------------------------------------------------------------ #
    # 1) USER EXCHANGE: /user-storage/user/...
    # ------------------------------------------------------------------ #
    def _register_routes(self, router: APIRouter) -> None:
        @router.post(
            "/storage/user/upload",
            tags=["User Storage"],
            summary="Upload or replace a user-scoped file (per end-user)",
        )
        async def upload_user_file(
            request: Request,
            file: UploadFile = File(..., description="Binary payload"),
            key: Optional[str] = Body(None, embed=True, description="Logical path inside the user's space"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.CREATE, Resource.FILES)
            try:
                logical_key = key or (file.filename or "file")
                meta = await self.service.put_user_file(user, logical_key, file)
                download_url = self._build_download_url(request, f"storage/user/{logical_key}")
                meta_dict = self._meta_to_dict(meta)
                return {**meta_dict, "download_url": download_url}
            except ValueError as e:
                raise HTTPException(400, str(e))
            except Exception:
                logger.exception("User storage upload failed")
                raise HTTPException(500, "Internal server error")

        @router.get(
            "/storage/user",
            tags=["User Storage"],
            summary="List files in the user's storage",
        )
        async def list_user_files(
            prefix: str = "",
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.FILES)
            try:
                return await self.service.list_user_files(user, prefix)
            except Exception:
                logger.exception("User storage list failed")
                raise HTTPException(500, "Internal server error")

        @router.get(
            "/storage/user/{key:path}",
            tags=["User Storage"],
            summary="Download a file from the user's storage",
        )
        async def download_user_file(
            key: str,
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.FILES)
            try:
                data = await self.service.read_user_file(user, key)
                return Response(content=data, media_type=self.service.guess_content_type(key))
            except FileNotFoundError:
                raise HTTPException(404, "File not found")
            except ValueError as e:
                raise HTTPException(400, str(e))
            except Exception:
                logger.exception("User storage download failed")
                raise HTTPException(500, "Internal server error")

        @router.delete(
            "/storage/user/{key:path}",
            tags=["User Storage"],
            summary="Delete a file from the user's storage",
        )
        async def delete_user_file(
            key: str,
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.DELETE, Resource.FILES)
            try:
                await self.service.delete_user_file(user, key)
                return {"ok": True, "key": key}
            except FileNotFoundError:
                raise HTTPException(404, "File not found")
            except ValueError as e:
                raise HTTPException(400, str(e))
            except Exception:
                logger.exception("User storage delete failed")
                raise HTTPException(500, "Internal server error")

        # ------------------------------------------------------------------ #
        # 2) AGENT CONFIG: /user-storage/agent-config/{agent_id}/...
        # Admin/service accounts write, agents read.
        # ------------------------------------------------------------------ #
        @router.post(
            "/storage/agent-config/{agent_id}/upload",
            tags=["User Storage"],
            summary="Upload or replace an agent-scoped config file (admin/service accounts)",
        )
        async def upload_agent_config_file(
            request: Request,
            agent_id: str,
            file: UploadFile = File(..., description="Binary payload"),
            key: Optional[str] = Form(None, description="Logical path inside the agent's config space"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.CREATE, Resource.FILES)
            try:
                logical_key = key or (file.filename or "file")
                meta = await self.service.put_agent_config_file(user, agent_id, logical_key, file)
                download_url = self._build_download_url(request, f"storage/agent-config/{agent_id}/{logical_key}")
                meta_dict = self._meta_to_dict(meta)
                return {**meta_dict, "download_url": download_url}
            except ValueError as e:
                raise HTTPException(400, str(e))
            except Exception:
                logger.exception("Agent config upload failed")
                raise HTTPException(500, "Internal server error")

        @router.get(
            "/storage/agent-config/{agent_id}",
            tags=["User Storage"],
            summary="List files in an agent's config storage",
        )
        async def list_agent_config_files(
            agent_id: str,
            prefix: str = "",
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.FILES)
            try:
                items = await self.service.list_agent_config_files(user, agent_id, prefix)
                return self._filter_files_only(items)
            except Exception:
                logger.exception("Agent config list failed")
                raise HTTPException(500, "Internal server error")

        @router.get(
            "/storage/agent-config/{agent_id}/{key:path}",
            tags=["User Storage"],
            summary="Download a file from an agent's config storage",
        )
        async def download_agent_config_file(
            agent_id: str,
            key: str,
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.FILES)
            try:
                data = await self.service.read_agent_config_file(user, agent_id, key)
                return Response(content=data, media_type=self.service.guess_content_type(key))
            except FileNotFoundError:
                raise HTTPException(404, "File not found")
            except ValueError as e:
                raise HTTPException(400, str(e))
            except Exception:
                logger.exception("Agent config download failed")
                raise HTTPException(500, "Internal server error")

        @router.delete(
            "/storage/agent-config/{agent_id}/{key:path}",
            tags=["User Storage"],
            summary="Delete a file from an agent's config storage",
        )
        async def delete_agent_config_file(
            agent_id: str,
            key: str,
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.DELETE, Resource.FILES)
            try:
                await self.service.delete_agent_config_file(user, agent_id, key)
                return {"ok": True, "key": key, "agent_id": agent_id}
            except FileNotFoundError:
                raise HTTPException(404, "File not found")
            except ValueError as e:
                raise HTTPException(400, str(e))
            except Exception:
                logger.exception("Agent config delete failed")
                raise HTTPException(500, "Internal server error")

        # ------------------------------------------------------------------ #
        # 3) AGENT PER-USER NOTES: /user-storage/agent-user/{agent_id}/{target_user_id}/...
        # ------------------------------------------------------------------ #
        @router.post(
            "/storage/agent-user/{agent_id}/{target_user_id}/upload",
            tags=["User Storage"],
            summary="Upload or replace an agent's per-user note/memo",
        )
        async def upload_agent_user_file(
            request: Request,
            agent_id: str,
            target_user_id: str,
            file: UploadFile = File(..., description="Binary payload"),
            key: Optional[str] = Form(None, description="Logical path inside the agent-user space"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.CREATE, Resource.FILES)
            try:
                logical_key = key or (file.filename or "file")
                meta = await self.service.put_agent_user_file(user, agent_id, target_user_id, logical_key, file)
                download_url = self._build_download_url(request, f"storage/agent-user/{agent_id}/{target_user_id}/{logical_key}")
                meta_dict = self._meta_to_dict(meta)
                return {**meta_dict, "download_url": download_url}
            except ValueError as e:
                raise HTTPException(400, str(e))
            except Exception:
                logger.exception("Agent-user upload failed")
                raise HTTPException(500, "Internal server error")

        @router.get(
            "/storage/agent-user/{agent_id}/{target_user_id}",
            tags=["User Storage"],
            summary="List files in an agent's per-user storage",
        )
        async def list_agent_user_files(
            agent_id: str,
            target_user_id: str,
            prefix: str = "",
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.FILES)
            try:
                return await self.service.list_agent_user_files(user, agent_id, target_user_id, prefix)
            except Exception:
                logger.exception("Agent-user list failed")
                raise HTTPException(500, "Internal server error")

        @router.get(
            "/storage/agent-user/{agent_id}/{target_user_id}/{key:path}",
            tags=["User Storage"],
            summary="Download a file from an agent's per-user storage",
        )
        async def download_agent_user_file(
            agent_id: str,
            target_user_id: str,
            key: str,
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.FILES)
            try:
                data = await self.service.read_agent_user_file(user, agent_id, target_user_id, key)
                return Response(content=data, media_type=self.service.guess_content_type(key))
            except FileNotFoundError:
                raise HTTPException(404, "File not found")
            except ValueError as e:
                raise HTTPException(400, str(e))
            except Exception:
                logger.exception("Agent-user download failed")
                raise HTTPException(500, "Internal server error")

        @router.delete(
            "/storage/agent-user/{agent_id}/{target_user_id}/{key:path}",
            tags=["User Storage"],
            summary="Delete a file from an agent's per-user storage",
        )
        async def delete_agent_user_file(
            agent_id: str,
            target_user_id: str,
            key: str,
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.DELETE, Resource.FILES)
            try:
                await self.service.delete_agent_user_file(user, agent_id, target_user_id, key)
                return {
                    "ok": True,
                    "key": key,
                    "agent_id": agent_id,
                    "user_id": target_user_id,
                }
            except FileNotFoundError:
                raise HTTPException(404, "File not found")
            except ValueError as e:
                raise HTTPException(400, str(e))
            except Exception:
                logger.exception("Agent-user delete failed")
                raise HTTPException(500, "Internal server error")
