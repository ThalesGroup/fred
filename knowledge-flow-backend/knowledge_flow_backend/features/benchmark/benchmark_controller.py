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
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fred_core import KeycloakUser, get_current_user

from knowledge_flow_backend.features.benchmark.procbench.models import (
    BenchmarkResponse,
    ProcessorDescriptor,
    ProcessorRunResult,
    SavedRun,
    SavedRunSummary,
)
from knowledge_flow_backend.features.benchmark.procbench.registry import default_registry
from knowledge_flow_backend.features.benchmark.procbench.runner import LiteAdapter, StandardProcessorAdapter
from knowledge_flow_backend.application_context import ApplicationContext
import json as _json
import io
import datetime as dt

logger = logging.getLogger(__name__)


class BenchmarkController:
    """
    Stateless developer endpoints to benchmark multiple ingestion processors.

    - Returns fully typed Pydantic models with in-memory markdown and metrics.
    - No persistent files, no HTML report generation.
    """

    def __init__(self, router: APIRouter) -> None:
        bench = APIRouter(prefix="/dev/bench", tags=["Benchmark"])
        bench.add_api_route(
            "/processors",
            self.list_processors,
            methods=["GET"],
            summary="List available processors",
            response_model=list[ProcessorDescriptor],
        )
        bench.add_api_route(
            "/run",
            self.run,
            methods=["POST"],
            summary="Run processors on an uploaded file (stateless)",
            response_model=BenchmarkResponse,
        )
        bench.add_api_route(
            "/runs",
            self.list_runs,
            methods=["GET"],
            summary="List saved benchmark runs for current user",
            response_model=list[SavedRunSummary],
        )
        bench.add_api_route(
            "/runs/{run_id}",
            self.get_run,
            methods=["GET"],
            summary="Get a saved benchmark run by id",
            response_model=BenchmarkResponse,
        )
        bench.add_api_route(
            "/runs/{run_id}",
            self.delete_run,
            methods=["DELETE"],
            summary="Delete a saved benchmark run by id",
        )
        router.include_router(bench)

    async def list_processors(self, user: KeycloakUser = Depends(get_current_user)) -> list[ProcessorDescriptor]:
        reg = default_registry()
        return [ProcessorDescriptor(id=s.id, name=s.display_name, kind=s.kind, file_types=s.file_types) for s in reg.values()]

    async def run(
        self,
        user: KeycloakUser = Depends(get_current_user),
        file: UploadFile = File(..., description="Input document (pdf, docx, …)"),
        processors: Optional[str] = Form(None, description="Comma-separated processor ids; default by file type"),
        persist: Optional[bool] = Form(False, description="Persist the run under the user's benchmark folder"),
    ) -> BenchmarkResponse:
        # Materialize upload into a temporary file path (processors need a filesystem path)
        import shutil
        import tempfile

        original_name = Path(file.filename or "upload").name
        # Preserve the original file extension so downstream tools (e.g., pandoc)
        # can infer the type from the path.
        ext = Path(original_name).suffix.lower()

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        try:
            with tmp as f:
                shutil.copyfileobj(file.file, f)
            input_path = Path(tmp.name)
        finally:
            await file.close()

        reg = default_registry()
        names: Optional[List[str]] = [p.strip() for p in processors.split(",")] if processors else None

        # Select specs by explicit ids or by extension (from original name)
        if names:
            specs = []
            for n in names:
                if n not in reg:
                    raise HTTPException(status_code=400, detail=f"Unknown processor id: {n}")
                specs.append(reg[n])
        else:
            specs = [s for s in reg.values() if ext in s.file_types]

        if not specs:
            # Cleanup and exit
            try:
                input_path.unlink(missing_ok=True)
            except Exception:
                logger.warning(f"Failed to delete temp file {input_path}")
                pass
            ext_display = ext or "(unknown)"
            supported = ", ".join(sorted({ft for s in reg.values() for ft in s.file_types}))
            raise HTTPException(status_code=400, detail=f"No processors registered for '{ext_display}'. Supported: {supported}")

        # Run all selected processors (stateless: no persistent working dir)
        results: List[ProcessorRunResult] = []
        for spec in specs:
            adapter = StandardProcessorAdapter() if spec.kind == "standard" else LiteAdapter()
            results.append(adapter.run(spec, input_path))

        try:
            resp = BenchmarkResponse(
                input_filename=original_name,
                file_type=ext,
                results=results,
            )
            if persist:
                self._save_run(user, resp)
            return resp
        finally:
            # Best-effort cleanup of the temp file
            try:
                input_path.unlink(missing_ok=True)
            except Exception:
                logger.warning(f"Failed to delete temp file {input_path}")
                pass

    # ---- Storage helpers and routes -------------------------------------------------

    def _runs_prefix(self, user: KeycloakUser) -> str:
        return f"benchmark/{user.uid}/"

    def _save_run(self, user: KeycloakUser, resp: BenchmarkResponse) -> str:
        store = ApplicationContext.get_instance().get_content_store()
        # Use two representations: a stable, file-safe id timestamp and an ISO-8601 saved_at
        now_id = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        # Use timestamp + sanitized filename for readability
        safe_name = (resp.input_filename or "upload").replace("/", "_").replace("\\", "_")
        run_id = f"{now_id}-{safe_name}"
        payload = {
            "saved_at": now_iso,
            "user_id": user.uid,
            "input_filename": resp.input_filename,
            "file_type": resp.file_type,
            "results": [r.model_dump() if hasattr(r, "model_dump") else r for r in resp.results],
        }
        data = _json.dumps(payload, ensure_ascii=False).encode("utf-8")
        key = f"{self._runs_prefix(user)}{run_id}.json"
        store.put_object(key=key, stream=io.BytesIO(data), content_type="application/json")
        return run_id

    async def list_runs(self, user: KeycloakUser = Depends(get_current_user)) -> list[SavedRunSummary]:
        store = ApplicationContext.get_instance().get_content_store()
        objs = store.list_objects(self._runs_prefix(user))
        runs: list[SavedRunSummary] = []
        for o in objs:
            key = o.key
            if not key.endswith(".json"):
                continue
            run_id = key.rsplit("/", 1)[-1][:-5]
            try:
                stream = store.get_object_stream(key)
                raw = stream.read()
                saved = SavedRun.model_validate_json(raw.decode("utf-8"))
                runs.append(
                    SavedRunSummary(
                        id=run_id,
                        input_filename=saved.input_filename,
                        file_type=saved.file_type,
                        processors_count=len(saved.results),
                        size=o.size,
                        modified=o.modified,
                    )
                )
            except Exception:
                # Skip corrupted entries to avoid breaking the UI
                logger.exception("Failed to read saved bench run: %s", key)
                continue
        # Sort desc by modified if present
        runs.sort(key=lambda r: r.modified or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True)
        return runs

    async def get_run(self, run_id: str, user: KeycloakUser = Depends(get_current_user)) -> BenchmarkResponse:
        store = ApplicationContext.get_instance().get_content_store()
        key = f"{self._runs_prefix(user)}{run_id}.json"
        try:
            stream = store.get_object_stream(key)
            raw = stream.read()
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Run not found")
        try:
            saved = SavedRun.model_validate_json(raw.decode("utf-8"))
            return BenchmarkResponse(input_filename=saved.input_filename, file_type=saved.file_type, results=saved.results)
        except Exception as e:
            logger.exception("Failed to reconstruct BenchmarkResponse")
            raise HTTPException(status_code=500, detail=f"Invalid saved run: {e}")

    async def delete_run(self, run_id: str, user: KeycloakUser = Depends(get_current_user)) -> dict:
        store = ApplicationContext.get_instance().get_content_store()
        key = f"{self._runs_prefix(user)}{run_id}.json"
        try:
            store.delete_object(key)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Run not found")
        return {"status": "deleted"}
