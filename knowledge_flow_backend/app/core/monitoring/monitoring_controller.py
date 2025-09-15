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
from app.core.monitoring.monitoring_service import AppMonitoringMetricsService

from fastapi import (
    APIRouter,
    Response,
)

# Create a module-level APIRouter
router = APIRouter(tags=["Monitoring"])

@router.get("/healthz")
async def healthz():
  return {"status": "ok"}

@router.get("/ready")
def ready():
  return {"status": "ready"}

@router.get(
    "/metrics/system",
    summary="Expose system metrics for Prometheus scraping",
    include_in_schema=False,
)
def metrics():
    """
    Expose Prometheus system metrics
    """
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
