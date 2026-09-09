# Copyright Thales 2026
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

"""Nightly expiry of the cached Word/PowerPoint PDF renders.

One bulk activity: list every `{uid}/output/render.pdf`, delete those older than
`app.pdf_render_ttl_days`. The next viewer of an expired document simply triggers
a fresh render. Rationale and lifetime rules: docs/swift/ux/COMPONENT-UX.md.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from temporalio import activity

from knowledge_flow_backend.features.scheduler.activity_utils import _heartbeat_if_in_activity, to_thread_with_heartbeat

logger = logging.getLogger(__name__)

PDF_RENDER_EXPIRED_TOTAL = "content.pdf_render_expired_total"
_HEARTBEAT_EVERY = 100


def _as_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


@activity.defn
async def expire_pdf_renders() -> dict:
    """Delete every cached render written more than `ttl_days` ago.

    A listing failure raises so Temporal retries; a single failed deletion is
    counted and skipped so one bad object never stalls the whole pass.
    """
    from knowledge_flow_backend.application_context import ApplicationContext
    from knowledge_flow_backend.features.content.content_service import PDF_RENDER_ARTIFACT_NAME
    from knowledge_flow_backend.features.scheduler.kpi_utils import build_temporal_activity_kpi_actor

    context = ApplicationContext.get_instance()
    ttl_days = int(context.get_config().app.pdf_render_ttl_days)
    result = {"ttl_days": ttl_days, "scanned": 0, "expired": 0, "failed": 0}
    if ttl_days <= 0:
        activity.logger.info("[SCHEDULER][ACTIVITY][PDF_RENDER_EXPIRY] disabled (ttl_days=%d), nothing to do", ttl_days)
        return result

    store = context.get_content_store()
    cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
    # A full-bucket walk on S3-style stores can outlast the heartbeat timeout.
    renders = await to_thread_with_heartbeat(store.list_output_artifacts, PDF_RENDER_ARTIFACT_NAME, heartbeat_details={"stage": "list"})
    result["scanned"] = len(renders)

    for index, render in enumerate(renders, start=1):
        if render.modified is None or _as_utc(render.modified) >= cutoff:
            continue
        try:
            await asyncio.to_thread(store.delete_output_artifact, render.key)
            result["expired"] += 1
        except Exception as exc:  # noqa: BLE001
            result["failed"] += 1
            logger.warning("[SCHEDULER][ACTIVITY][PDF_RENDER_EXPIRY] could not delete %s: %s", render.key, exc)
        if index % _HEARTBEAT_EVERY == 0:
            _heartbeat_if_in_activity({"scanned": index, "expired": result["expired"]})

    activity.logger.info(
        "[SCHEDULER][ACTIVITY][PDF_RENDER_EXPIRY] ttl_days=%d scanned=%d expired=%d failed=%d",
        ttl_days,
        result["scanned"],
        result["expired"],
        result["failed"],
    )
    try:
        kpi = context.get_kpi_writer()
        actor = build_temporal_activity_kpi_actor()
        kpi.count(PDF_RENDER_EXPIRED_TOTAL, result["expired"], dims={"status": "ok"}, actor=actor)
        if result["failed"]:
            kpi.count(PDF_RENDER_EXPIRED_TOTAL, result["failed"], dims={"status": "error"}, actor=actor)
    except Exception as metric_exc:  # noqa: BLE001
        logger.warning("[SCHEDULER][ACTIVITY][PDF_RENDER_EXPIRY] failed to emit KPI: %s", metric_exc)
    return result
