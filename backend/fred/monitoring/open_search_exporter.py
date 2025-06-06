import requests
import time
import urllib3
import logging
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger("llm_monitoring.opensearch")

OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST", "https://localhost:9200")
OPENSEARCH_USER = os.getenv("OPENSEARCH_USER", "admin")
OPENSEARCH_PASS = os.getenv("OPENSEARCH_PASSWORD", "password")
DEFAULT_INDEX = "llm-logs-*"

logger = logging.getLogger("llm_monitoring.init")

def init_opensearch_index_if_needed(
    index_name="llm-logs-monitoring",
    host="https://fred-opensearch:9200",
    username="admin",
    password="password"
)->None:
    """
    Vérifie si l'index existe. Le crée avec mapping si nécessaire.
    """
    url = f"{host}/{index_name}"
    auth = (username, password)
    headers = {"Content-Type": "application/json"}

    # Vérifie si l'index existe déjà
    check = requests.head(url, auth=auth, verify=False)
    if check.status_code == 200:
        logger.debug(f"[Init] Index '{index_name}' déjà existant.")
        return

    logger.info(f"[Init] Création de l'index '{index_name}'...")

    mapping = {
            "index_patterns": ["llm-logs-*"],
            "template": {
                "mappings": {
                "properties": {
                    "timestamp": {
                    "type": "date",
                    "format": "epoch_second"
                    },
                    "user_id": { "type": "keyword" },
                    "session_id": { "type": "keyword" },
                    "latency": { "type": "float" },
                    "model_name": { "type": "keyword" },
                    "model_type": { "type": "keyword" },
                    "finish_reason": { "type": "keyword" },
                    "timestamp": { "type": "date" },
                    "token_usage": {
                    "properties": {
                        "prompt_tokens": { "type": "integer" },
                        "completion_tokens": { "type": "integer" },
                        "total_tokens": { "type": "integer" }
                            }
                        }
                    }
                }
            }
        }

    response = requests.put(url, auth=auth, headers=headers, json=mapping, verify=False)
    if response.ok:
        logger.info(f"[Init] ✅ Index '{index_name}' créé avec succès.")
    else:
        logger.error(f"[Init] ❌ Erreur lors de la création : {response.status_code} - {response.text}")

init_opensearch_index_if_needed(index_name="llm-monitoring",
    host=OPENSEARCH_HOST,
    username=OPENSEARCH_USER,
    password=OPENSEARCH_PASS)

def is_opensearch_available() -> bool:
    try:
        response = requests.head(
            f"{OPENSEARCH_HOST}/{DEFAULT_INDEX}",
            auth=(OPENSEARCH_USER, OPENSEARCH_PASS),
            verify=False,
            timeout=2
        )
        return response.status_code in [200, 404]  # 404 = index absent mais OS est joignable
    except Exception as e:
        logger.warning(f"[OpenSearch] ⚠️ OpenSearch non joignable : {e}")
        return False


def send_to_opensearch(document: dict, index: str = DEFAULT_INDEX) -> None:
    if not is_opensearch_available():
        logger.warning("[OpenSearch] ⛔ Connexion impossible — log ignoré.")
        return

    url = f"{OPENSEARCH_HOST}/{index}/_doc"
    auth = (OPENSEARCH_USER, OPENSEARCH_PASS)
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(url, auth=auth, headers=headers, json=document, verify=False)
        response.raise_for_status()
        logger.info(f"[OpenSearch] ✅ Document envoyé à l'index '{index}' (ID: {response.json().get('_id')})")
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"[OpenSearch] ❌ HTTP error: {http_err} | Response: {response.text}")
    except Exception as e:
        logger.error(f"[OpenSearch] ❌ Exception: {e}")

