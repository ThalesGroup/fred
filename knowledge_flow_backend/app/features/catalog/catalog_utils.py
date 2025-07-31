import hashlib
from pathlib import Path
from typing import List

from app.application_context import ApplicationContext
from app.common.structures import (
    DocumentSourceConfig,
)
from app.core.stores.metadata.base_catalog_store import PullFileEntry
import base64
from datetime import time
import hmac
from fastapi import requests


def _scan_local_path(base_path: Path, source_tag: str) -> List[PullFileEntry]:
    entries = []
    base = base_path.expanduser().resolve()
    for path in base.rglob("*"):
        if path.is_file():
            relative = str(path.relative_to(base))
            stat = path.stat()
            entries.append(PullFileEntry(path=relative, size=stat.st_size, modified_time=stat.st_mtime, hash=hashlib.sha256(str(path).encode()).hexdigest()))
    return entries

def _scan_sphere_api(source: DocumentSourceConfig, 
                    source_tag: str) -> List[PullFileEntry]:

    base_url = source.extra["base_url"]
    username = source.extra["username"]
    password = source.extra["password"]
    api_key = source.extra["apikey"]
    parent_node_id = source.extra["parent_node_id"]

    def generate_signature(method, url, timestamp):
        to_sign = f"{method.upper()}{url}{timestamp}{api_key}"
        signature = hmac.new(password.encode(), to_sign.encode(), hashlib.sha256).digest()
        return base64.b64encode(signature).decode()

    def get_headers(method, url):
        ts = str(int(time.time()))
        return {
            "apikey": api_key,
            "username": username,
            "content-type": "application/json",
            "X-Apim-Hash-Algorithm": "HMAC-SH512",
            "X-Timestamp": ts,
            "X-Signature": generate_signature(method, url, ts),
            "User-Agent": "FredSphereScanner",
        }

    session = requests.Session()
    session.auth = (username, password)
    session.verify = False  # configurable

    children_url = f"{base_url}/nodes/{parent_node_id}/nodes"
    response = session.get(children_url, headers=get_headers("GET", children_url))
    response.raise_for_status()

    entries = []
    for item in response.json():
        if "data" not in item or "properties" not in item["data"]:
            continue
        props = item["data"]["properties"]
        node_id = str(props.get("id"))
        name = props.get("name", "unknown")
        size = props.get("size", 0)
        modified = props.get("modified") or time.time()  # fallback if not available

        hash_id = hashlib.sha256((node_id + name).encode()).hexdigest()
        entries.append(PullFileEntry(
            path=name,
            size=size,
            modified_time=modified,
            hash=hash_id,
        ))

    return entries

def scan_pull_source(source_tag: str) -> List[PullFileEntry]:
    config = ApplicationContext.get_instance().get_config()
    source: DocumentSourceConfig = config.document_sources.get(source_tag)

    if not source or source.type != "pull":
        raise ValueError(f"Invalid or unknown pull source: {source_tag}")

    if source.provider == "local_path":
        return _scan_local_path(Path(source.base_path), source_tag)
    elif source.provider == "sphere":
        return _scan_sphere_api(source, source_tag)

    raise NotImplementedError(f"No scanner implemented for provider: {source.provider}")

