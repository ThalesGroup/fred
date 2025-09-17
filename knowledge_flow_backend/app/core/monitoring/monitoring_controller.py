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

from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from fastapi import (
    APIRouter,
    Response,
)

class MonitoringController:
    def __init__(self, router: APIRouter, base_path: str = ""):
        """
        Attach monitoring routes to the given APIRouter.
        :param router: The APIRouter instance to register endpoints on.
        :param base_path: Optional prefix for monitoring endpoints.
        """
        self.router = router
        self.base_path = base_path
        self._register_routes()

    def _register_routes(self):
        @self.router.get(f"{self.base_path}/healthz", tags=["Monitoring"])
        async def healthz():
            return {"status": "ok"}

        @self.router.get(f"{self.base_path}/ready", tags=["Monitoring"])
        async def ready():
            return {"status": "ready"}

        @self.router.get(
            f"{self.base_path}/metrics/system",
            summary="Expose system metrics for Prometheus scraping",
            include_in_schema=False,
        )
        async def metrics():
            return Response(
                content=generate_latest(),
                media_type=CONTENT_TYPE_LATEST,
            )