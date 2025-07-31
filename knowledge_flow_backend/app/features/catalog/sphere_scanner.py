import base64
from datetime import time
import hashlib
import hmac
from typing import List
from app.common.structures import DocumentSourceConfig
from app.core.stores.metadata.base_catalog_store import PullFileEntry
from fastapi import requests


def scan_sphere_api(source: DocumentSourceConfig, 
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
