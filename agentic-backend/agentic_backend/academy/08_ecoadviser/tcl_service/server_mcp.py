from __future__ import annotations

import csv
import logging
import os
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi_mcp import FastApiMCP
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


def _normalize_label(value: str) -> str:
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFD", value)
    without_accents = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    alnum_only = "".join(ch for ch in without_accents if ch.isalnum())
    return alnum_only.upper()


def _stop_tokens(value: str, limit: int = 2) -> List[str]:
    if not value:
        return []
    sanitized = value.replace("-", " ").replace("/", " ").replace("'", " ")
    tokens = [tok for tok in sanitized.split() if tok]
    filtered: List[str] = []
    for tok in tokens:
        if len(tok) >= 2:
            filtered.append(tok)
        if len(filtered) >= limit:
            break
    return filtered


def _load_stop_index() -> Dict[str, str]:
    csv_path = os.getenv(
        "TCL_STOPS_CSV",
        str(Path(__file__).resolve().parents[1] / "data" / "tcl_stops_demo.csv"),
    )
    index: Dict[str, str] = {}
    try:
        with open(csv_path, "r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                stop_id = (row.get("stop_id") or "").strip()
                stop_name = (row.get("stop_name") or "").strip()
                if stop_id and stop_name:
                    index[stop_id] = stop_name
    except FileNotFoundError:
        logger.debug("TCL stop index CSV not found at %s", csv_path)
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Unable to load TCL stop index from %s: %s", csv_path, exc)
    return index

DEFAULT_TCL_DATASET = "tcl_sytral.tclpassagearret"
DEFAULT_TCL_BASE_URL = "https://data.grandlyon.com/fr/datapusher/ws/rdata"


class TCLRealtimeRequest(BaseModel):
    stop_code: str = Field(..., description="Identifiant d'arrêt (identifiantarret).")
    line: Optional[str] = Field(default=None, description="Code ligne (optionnel).")
    rows: int = Field(default=10, ge=1, le=200)

    @field_validator("stop_code", mode="before")
    @classmethod
    def _coerce_stop_code(cls, value: Any) -> str:
        if value is None:
            raise ValueError("stop_code is required")
        return str(value)


class TCLPassage(BaseModel):
    stop_code: Optional[str]
    stop_name: Optional[str]
    line: Optional[str]
    destination: Optional[str]
    passage_time: Optional[str]
    realtime: Optional[bool]
    platform: Optional[str]
    additional_info: Dict[str, Any]

    @field_validator("stop_code", mode="before")
    @classmethod
    def _coerce_stop_code(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        return str(value)


class TCLRealtimeResponse(BaseModel):
    provider: str
    fetched_at: datetime
    results: List[TCLPassage]
    total_returned: int


class TCLDataClient:
    def __init__(self):
        self.base_url = os.getenv("TCL_RDATA_URL", DEFAULT_TCL_BASE_URL).rstrip("/")
        dataset = os.getenv("TCL_RDATA_DATASET", DEFAULT_TCL_DATASET).strip("/")
        endpoint_override = os.getenv("TCL_RDATA_ENDPOINT")
        if endpoint_override:
            filtered, bulk = self._derive_endpoints(endpoint_override)
            self.filtered_endpoint = filtered
            self.bulk_endpoint = bulk
            self.dataset_label = endpoint_override
        else:
            self.filtered_endpoint = f"{self.base_url}/{dataset}.json"
            self.bulk_endpoint = f"{self.base_url}/{dataset}/all.json"
            self.dataset_label = dataset
        self.username = os.getenv("TCL_RDATA_USERNAME") or os.getenv("GRANDLYON_WFS_USERNAME")
        self.password = os.getenv("TCL_RDATA_PASSWORD") or os.getenv("GRANDLYON_WFS_PASSWORD")
        self.timeout = float(os.getenv("TCL_RDATA_TIMEOUT", "10.0"))
        self.page_size = int(os.getenv("TCL_RDATA_PAGE_SIZE", "200"))
        self.max_pages = int(os.getenv("TCL_RDATA_MAX_PAGES", "20"))
        if not (self.username and self.password):
            logger.warning(
                "TCL credentials missing (TCL_RDATA_USERNAME/PASSWORD). Requests will likely fail with 401."
            )
        self.stop_index = _load_stop_index()

    def resolve_stop_name(self, stop_code: str) -> Optional[str]:
        return self.stop_index.get(stop_code.strip()) if self.stop_index else None

    @staticmethod
    def _derive_endpoints(endpoint_override: str) -> tuple[str, str]:
        """
        Users sometimes provide the /all.json endpoint directly (as documented in
        Grand Lyon examples). We still need two distinct URLs: one for filtered
        queries (dataset.json) and one for bulk scans (dataset/all.json).
        """
        trimmed = endpoint_override.strip()
        trimmed = trimmed.rstrip("/")
        if not trimmed:
            raise ValueError("TCL_RDATA_ENDPOINT cannot be empty.")

        suffix_all = "/all.json"
        suffix_json = ".json"

        if trimmed.endswith(suffix_all):
            base = trimmed[: -len(suffix_all)]
            filtered = f"{base}.json"
            bulk = trimmed
        elif trimmed.endswith(suffix_json):
            base = trimmed[: -len(suffix_json)]
            filtered = trimmed
            bulk = f"{base}{suffix_all}"
        else:
            base = trimmed
            filtered = f"{base}{suffix_json}"
            bulk = f"{base}{suffix_all}"
        return filtered, bulk

    def _build_where_clause(self, request: TCLRealtimeRequest) -> str:
        value = request.stop_code.strip()
        identifiers = ["identifiantarret", "idtarretdestination", "id"]
        value_is_digit = value.isdigit()
        eq_fragments: List[str] = []
        for ident in identifiers:
            eq_fragments.append(f"{ident}='{value}'")
            if value_is_digit:
                eq_fragments.append(f"{ident}={value}")

        stop_clause = "(" + " OR ".join(eq_fragments) + ")"

        stop_name = self.resolve_stop_name(value)
        if stop_name:
            token_clauses: List[str] = []
            for token in _stop_tokens(stop_name):
                safe_token = token.replace("'", "''")
                token_clauses.append(f"upper(nomarret) LIKE upper('%{safe_token}%')")
                token_clauses.append(f"upper(destination) LIKE upper('%{safe_token}%')")
            if token_clauses:
                name_clause = "(" + " OR ".join(token_clauses) + ")"
                stop_clause = f"({stop_clause} OR {name_clause})"

        clauses = [stop_clause]
        if request.line:
            clauses.append(f"ligne='{request.line}'")
        return " AND ".join(clauses)

    def _extract_records(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        record_entries: List[Dict[str, Any]] = []
        if "records" in payload:
            for record in payload.get("records", []):
                fields = record.get("fields") or {}
                if fields:
                    record_entries.append(fields)
        elif "values" in payload:
            vals = payload.get("values") or []
            if isinstance(vals, list):
                record_entries.extend(val for val in vals if isinstance(val, dict))
        else:
            raise HTTPException(
                status_code=502,
                detail=payload.get("message") or payload.get("detail") or "Unexpected TCL payload",
            )
        return record_entries

    def query(self, request: TCLRealtimeRequest) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        auth = None
        if self.username and self.password:
            auth = httpx.BasicAuth(self.username, self.password)

        with httpx.Client(timeout=self.timeout, auth=auth) as client:
            # Try filtered endpoint first
            try:
                filtered_records, filtered_payload = self._fetch_filtered(client, request)
                if filtered_records:
                    return filtered_records, filtered_payload
            except Exception:  # pylint: disable=broad-except
                logger.debug("Filtered TCL endpoint failed, falling back to bulk scan.", exc_info=True)

            return self._fetch_bulk(client, request)

    def _fetch_filtered(
        self, client: httpx.Client, request: TCLRealtimeRequest
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        if not self.filtered_endpoint:
            return [], {}
        params = {
            "where": self._build_where_clause(request),
            "maxfeatures": request.rows,
            "start": 1,
            "sort": "heurepassage",
            "order": "asc",
            "compact": "false",
        }
        response = client.get(self.filtered_endpoint, params=params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=502, detail="Invalid TCL response (not JSON).")
        return self._extract_records(payload), payload

    def _fetch_bulk(
        self, client: httpx.Client, request: TCLRealtimeRequest
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        collected: List[Dict[str, Any]] = []
        payload_meta: Dict[str, Any] = {}
        page_size = min(max(request.rows, self.page_size), 1000)
        start = 1

        if not self.bulk_endpoint:
            raise HTTPException(status_code=502, detail="TCL bulk endpoint not configured.")

        for page in range(self.max_pages):
            params = {
                "where": self._build_where_clause(request),
                "maxfeatures": page_size,
                "start": start,
                "sort": "heurepassage",
                "order": "asc",
                "compact": "false",
            }
            response = client.get(self.bulk_endpoint, params=params)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.exception("GrandLyon TCL bulk error: %s", exc)
                raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text) from exc
            payload = response.json()
            if not isinstance(payload, dict):
                raise HTTPException(status_code=502, detail="Invalid TCL bulk response.")
            batch = self._extract_records(payload)
            collected.extend(batch)
            payload_meta = payload

            if len(batch) < page_size:
                break
            if len(collected) >= page_size * self.max_pages:
                break
            start += page_size

        return collected, payload_meta


def _coerce_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in {"true", "1", "oui", "yes"}:
            return True
        if lowered in {"false", "0", "non", "no"}:
            return False
    if isinstance(value, (int, float)):
        return value != 0
    return None


def _parse_passages(records: List[Dict[str, Any]]) -> List[TCLPassage]:
    results: List[TCLPassage] = []
    for fields in records:
        passage_iso = fields.get("heurepassage")
        if isinstance(passage_iso, str) and len(passage_iso) == 8:
            # Format HH:MM:SS, convert to ISO by assuming current date
            today = datetime.now(timezone.utc).date()
            passage_iso = f"{today}T{passage_iso}Z"
        results.append(
            TCLPassage(
                stop_code=fields.get("identifiantarret")
                or fields.get("idtarretdestination")
                or fields.get("id"),
                stop_name=fields.get("stop_name") or fields.get("nomarret"),
                line=fields.get("ligne"),
                destination=fields.get("destination") or fields.get("direction"),
                passage_time=passage_iso,
                realtime=_coerce_bool(fields.get("rdv")),
                platform=fields.get("quai"),
                additional_info=fields,
            )
        )
    return results


def _filter_records(
    records: List[Dict[str, Any]],
    request: TCLRealtimeRequest,
    stop_name_hint: Optional[str] = None,
) -> List[Dict[str, Any]]:
    def _matches_stop(fields: Dict[str, Any]) -> bool:
        if not request.stop_code:
            return True
        candidate_keys = ["identifiantarret", "idtarretdestination", "id", "stop_id"]
        target = str(request.stop_code)
        for key in candidate_keys:
            value = fields.get(key)
            if value is not None and str(value) == target:
                return True
        return False

    def _matches_line(fields: Dict[str, Any]) -> bool:
        if not request.line:
            return True
        return str(fields.get("ligne", "")).lower() == request.line.lower()

    stop_name_hint_norm = _normalize_label(stop_name_hint or "")

    filtered: List[Dict[str, Any]] = []
    for entry in records:
        stop_ok = _matches_stop(entry)
        if not stop_ok and stop_name_hint_norm:
            candidate_name = str(entry.get("nomarret") or entry.get("stop_name") or "")
            candidate_norm = _normalize_label(candidate_name)
            stop_ok = bool(candidate_norm and stop_name_hint_norm in candidate_norm)

        if not stop_ok:
            continue

        if not _matches_line(entry):
            continue

        filtered.append(entry)
    return filtered


client = TCLDataClient()

app = FastAPI(
    title="EcoAdvisor TCL Real-time Service",
    version="0.1.0",
    description="Proxy MCP service fetching live TCL passages from the Grand Lyon RDATA API.",
)


@app.post(
    "/tcl/realtime",
    response_model=TCLRealtimeResponse,
    tags=["TCL"],
    operation_id="get_tcl_realtime_passages",
)
async def get_tcl_realtime_passages(request: TCLRealtimeRequest) -> TCLRealtimeResponse:
    logger.info(
        "TCL realtime query stop=%s line=%s rows=%s",
        request.stop_code,
        request.line or "*",
        request.rows,
    )
    records, payload = client.query(request)
    stop_name_hint = client.resolve_stop_name(request.stop_code)
    filtered_records = _filter_records(records, request, stop_name_hint)
    if not filtered_records:
        logger.warning(
            "No TCL passages matched stop=%s line=%s (raw_records=%s)",
            request.stop_code,
            request.line or "*",
            len(records),
        )
        raise HTTPException(
            status_code=404,
            detail="Aucun passage temps réel trouvé pour cet arrêt/lignes (pensez à vérifier l'identifiant d'arrêt).",
        )
    try:
        results = _parse_passages(filtered_records)
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Failed to parse TCL passages payload")
        raise HTTPException(status_code=502, detail=f"TCL parsing error: {exc}") from exc
    provider = payload.get("layer_name") or payload.get("dataset") or "Grand Lyon RDATA TCL"
    return TCLRealtimeResponse(
        provider=provider,
        fetched_at=datetime.now(timezone.utc),
        results=results,
        total_returned=len(results),
    )


@app.get("/tcl/health", tags=["TCL"])
async def health() -> Dict[str, str]:
    return {
        "status": "ok",
        "filtered_endpoint": client.filtered_endpoint,
        "bulk_endpoint": client.bulk_endpoint,
        "dataset": client.dataset_label,
        "auth_mode": "basic" if client.username else "none",
    }


mcp = FastApiMCP(
    app,
    name="EcoAdvisor TCL MCP",
    description="Expose real-time TCL passages via the Grand Lyon RDATA API.",
    include_tags=["TCL"],
    describe_all_responses=True,
    describe_full_response_schema=True,
)
mcp.mount_http(mount_path="/mcp")

__all__ = ["app"]
