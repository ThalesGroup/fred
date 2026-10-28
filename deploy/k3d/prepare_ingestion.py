#!/usr/bin/env python3
"""Prepare the explicitly selected manager profile from its rendered worker image/config."""

import base64
import hashlib
import json
import os
import re
import secrets
from pathlib import Path
import ssl
import subprocess
import tempfile
from urllib.request import Request, urlopen
from urllib.parse import quote, urlencode

import yaml


def run(command: list[str], *, body: str | None = None, step: str | None = None) -> str:
    result = subprocess.run(command, input=body, text=True, capture_output=True)
    if result.returncode:
        # Subcommands may process Secrets; never echo their arguments or payloads.
        raise RuntimeError(f"{step or command[0]} failed while preparing ingestion (exit {result.returncode})")
    return result.stdout


def prepare() -> None:
    if os.environ.get("ENV") != "secondary":
        raise RuntimeError("Manager ingestion preparation requires ENV=secondary")
    here = Path(__file__).resolve().parent
    output = Path(os.environ["K3D_APP_OUT"])
    namespace = os.environ.get("K3D_NAMESPACE", "fred")
    kube = ["kubectl", "--context", os.environ["KUBE_CONTEXT"], "-n", namespace]
    # Use the same templates and precedence as the deployment (including the factory environment).
    command = ["helmfile", "--file", str(here / "helmfile.yaml.gotmpl"),
               "--kube-context", os.environ["KUBE_CONTEXT"], "--namespace", namespace,
               "template", "--skip-deps"]
    for values in os.environ.get("K3D_APP_VALUES", "").splitlines():
        command += ["--values", values]
    manifests = [item for item in yaml.safe_load_all(run(command)) if item]
    configs = {item["metadata"]["name"]: item for item in manifests if item["kind"] == "ConfigMap"}
    worker_yaml = configs["knowledge-flow-worker-back"]["data"]["configuration.yaml"]
    worker_config = yaml.safe_load(worker_yaml)
    api_config = yaml.safe_load(
        configs["knowledge-flow-backend-back"]["data"]["configuration.yaml"]
    )
    generated = output / "manager-ingestion.generated.yaml"
    if not worker_config.get("manager_processing", {}).get("enabled"):
        raise RuntimeError("This profile requires manager_processing.enabled for the KF worker")
    corpus_index, api_indexes = corpus_settings(worker_config, api_config)
    indexes = [corpus_index]
    kpi = worker_config["observability"]["kpi"]["opensearch"]
    if kpi["enabled"]:
        indexes.append(concrete_index(kpi.get("index")))
    deploys = {item["metadata"]["name"]: item for item in manifests if item["kind"] == "Deployment"}
    expected_deployments = {"control-plane-backend", "knowledge-flow-backend", "knowledge-flow-worker", "frontend", "fred-agents"}
    if set(deploys) != expected_deployments:
        raise RuntimeError("Expected only control-plane-backend, knowledge-flow-backend, knowledge-flow-worker, frontend and fred-agents deployments")
    image = deploys["knowledge-flow-worker"]["spec"]["template"]["spec"]["containers"][0]["image"]
    image_id = run(["docker", "image", "inspect", "--format", "{{.Id}}", image]).strip()
    with tempfile.TemporaryDirectory(prefix="fred-contract-") as directory:
        path = Path(directory) / "configuration.yaml"
        path.write_text(worker_yaml)
        # Rendered configuration contains references, never service credentials.
        # The image runs as a non-root user and must traverse this bind mount.
        Path(directory).chmod(0o755)
        path.chmod(0o644)
        exported = run(["docker", "run", "--rm", "--network", "none", "--entrypoint", "python", "-v", f"{directory}:/export:ro", image,
                        "-m", "knowledge_flow_backend.features.scheduler.export_contract", "--configuration", "/export/configuration.yaml"])
    contract = json.loads(exported)
    if contract.get("workflow") != "ProcessPush" or set(contract.get("profiles", {})) != {"fast", "medium", "rich"}:
        raise RuntimeError("Worker image exported an invalid ingestion contract")
    pipeline = json.loads(run([
        "docker", "run", "--rm", "--network", "none", "--entrypoint", "python", image, "-c",
        "import json; from knowledge_flow_backend.core.stores.vector.opensearch_vector_store import HYBRID_SEARCH_PIPELINE_NAME, HYBRID_SEARCH_PIPELINE_CONFIG; print(json.dumps({'name': HYBRID_SEARCH_PIPELINE_NAME, 'body': HYBRID_SEARCH_PIPELINE_CONFIG}))",
    ]))
    digest = hashlib.sha256((image_id + "\n" + worker_yaml + "\n" + exported).encode()).hexdigest()
    resource = {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {
        "name": "manager-processing-contract", "namespace": namespace,
        "annotations": {"fred/worker-image": image, "fred/worker-image-id": image_id, "fred/contract-sha256": digest}},
        "data": {"worker-contract.json": json.dumps(contract, indent=2)}}
    foundation = json.loads(run([*kube, "get", "secret", "fred-secrets", "-o", "json"]))["data"]
    application = provision_storage(kube, foundation, here, image)
    provision_worker_identity(foundation)
    user = base64.b64decode(foundation["OPENSEARCH_ADMIN"]).decode()
    password = base64.b64decode(foundation["OPENSEARCH_ADMIN_PASSWORD"]).decode()
    authorization = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
    endpoint = f"https://127.0.0.1:{int(os.environ.get('K3D_HOST_PORT_OPENSEARCH', '9200'))}/_plugins/_security/api"
    provision_search(
        endpoint,
        authorization,
        application["opensearch-password"],
        pipeline,
        indexes,
        application["kf-api-opensearch-password"],
        api_indexes,
    )
    run([*kube, "apply", "-f", "-"], body=json.dumps(resource))
    generated.write_text(
        yaml.safe_dump(
            {
                "applications": {
                    "control-plane-backend": {
                        "podAnnotations": {"fred/processing-contract": digest}
                    },
                }
            }
        )
    )
    print(
        "Manager ingestion and Knowledge Flow API corpus access: scoped OpenSearch identities and image-matched processing contract prepared"
    )


def concrete_index(value: object) -> str:
    # A permission pattern must identify exactly one configured index.
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,254}", value):
        raise RuntimeError("OpenSearch permissions require a concrete lowercase index name, without wildcards")
    return value


def corpus_settings(worker_config: dict, api_config: dict) -> tuple[str, list[str]]:
    """Return the corpus index both KF processes share, and the API's writable indexes."""
    vector = worker_config["manager_processing"]["vector_store"]
    if vector.get("type") != "opensearch":
        raise RuntimeError("Local ingestion requires an OpenSearch vector store")
    corpus_index = concrete_index(vector.get("index"))
    if api_config["storage"].get("vector_store", {}).get("index") != corpus_index:
        raise RuntimeError("Knowledge Flow API must search the index the worker writes")
    api_indexes = []
    log_store = api_config["storage"].get("log_store") or {}
    if log_store.get("type") == "opensearch":
        api_indexes.append(concrete_index(log_store.get("index")))
    # KpiOpenSearchSinkConfig enables this sink and index by default.
    api_kpi = api_config.get("observability", {}).get("kpi", {}).get("opensearch", {})
    if api_kpi.get("enabled", True):
        api_indexes.append(concrete_index(api_kpi.get("index", "kpi-index")))
    if corpus_index in api_indexes:
        raise RuntimeError("The corpus index must be separate from writable API observability indexes")
    return corpus_index, api_indexes


def provision_search(
    endpoint: str,
    authorization: str,
    password: str,
    pipeline: dict,
    indexes: list[str],
    api_password: str,
    api_indexes: list[str],
) -> None:
    # The existing adapter checks a cluster-wide hybrid pipeline at startup.
    # Provision it as operator; the application only needs to read it.
    role = {"cluster_permissions": ["cluster_monitor", "cluster_composite_ops", "cluster:admin/search/pipeline/get"], "index_permissions": [
        {"index_patterns": indexes, "allowed_actions": ["crud", "create_index", "manage"]}]}
    account = {"password": password, "backend_roles": ["fred-kf-ingestion"]}
    resources = [(endpoint.removesuffix("/_plugins/_security/api") + "/_search/pipeline/" + quote(pipeline["name"], safe=""), pipeline["body"])]
    resources += [(endpoint + "/" + suffix, payload) for suffix, payload in [
        ("roles/fred-kf-ingestion", role), ("internalusers/fred-kf-ingestion", account),
        ("rolesmapping/fred-kf-ingestion", {"backend_roles": ["fred-kf-ingestion"], "users": []})]]
    # One connection serves search and observability; only the latter may write.
    api_role = {
        "cluster_permissions": [
            "cluster_monitor",
            "cluster_composite_ops",
            "cluster:admin/search/pipeline/get",
        ],
        "index_permissions": [
            {
                "index_patterns": [indexes[0]],
                # The adapter checks the index and its mapping at startup.
                "allowed_actions": [
                    "read",
                    "indices:admin/get",
                    "indices:admin/mappings/get",
                    "indices:monitor/settings/get",
                ],
            }
        ],
    }
    if api_indexes:
        api_role["index_permissions"].append(
            {
                "index_patterns": sorted(set(api_indexes)),
                "allowed_actions": ["crud", "create_index", "manage"],
            }
        )
    resources += [
        (endpoint + "/" + suffix, payload)
        for suffix, payload in [
            ("roles/fred-kf-api", api_role),
            (
                "internalusers/fred-kf-api",
                {"password": api_password, "backend_roles": ["fred-kf-api"]},
            ),
            (
                "rolesmapping/fred-kf-api",
                {"backend_roles": ["fred-kf-api"], "users": []},
            ),
        ]
    ]
    for url, payload in resources:
        request = Request(url, data=json.dumps(payload).encode(), headers={"Authorization": authorization, "Content-Type": "application/json"}, method="PUT")
        # This instance's self-signed OpenSearch certificate is a documented local deviation.
        with urlopen(request, context=ssl._create_unverified_context(), timeout=30) as response:
            response.read()


def apply(kube: list[str], resource: dict) -> None:
    run([*kube, "apply", "-f", "-"], body=json.dumps(resource))


def provision_storage(kube: list[str], foundation: dict, here: Path, image: str) -> dict:
    # Application credentials belong to this profile, never to shared factory values.
    existing = run([*kube, "get", "secret", "fred-ingestion", "--ignore-not-found", "-o", "json"])
    data = json.loads(existing).get("data", {}) if existing.strip() else {}
    credentials = {}
    for key in (
        "manager-s3-secret",
        "processor-s3-secret",
        "opensearch-password",
        "kf-api-opensearch-password",
    ):
        credentials[key] = base64.b64decode(data[key]).decode() if key in data else "F1!" + secrets.token_hex(24)
    apply(kube, {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "fred-ingestion"},
                 "type": "Opaque", "stringData": credentials})

    # Preserve the factory's identities. Add the profile's two scoped S3 identities.
    base = json.loads(run([*kube, "get", "configmap", "fred-seaweedfs-config", "-o", "json"]))
    config = json.loads(base["data"]["s3.json"])
    names = {"fred-document-manager", "fred-document-processor"}
    config["identities"] = [item for item in config["identities"] if item["name"] not in names]
    for name, key, policy in [("fred-document-manager", "manager-s3-secret", "manager"),
                              ("fred-document-processor", "processor-s3-secret", "kf")]:
        config["identities"].append({"name": name,
            "credentials": [{"accessKey": name, "secretKey": credentials[key]}],
            "actions": [], "policyNames": [policy]})
    policies = yaml.safe_load((here / "ingestion-policies.yaml").read_text())
    config["policies"] = [item for item in config.get("policies", []) if item["name"] not in {"manager", "kf"}]
    config["policies"] += [{"name": item["name"], "content": json.dumps(item["content"])} for item in policies]
    encoded = json.dumps(config, sort_keys=True)
    apply(kube, {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "control-plane-s3-config"},
                 "type": "Opaque", "stringData": {"s3.json": encoded}})
    # Explicit local infrastructure adaptation, restored by each app deployment after k3d-up.
    patch = {"spec": {"template": {
        "metadata": {"annotations": {"fred/manager-s3-config": hashlib.sha256(encoded.encode()).hexdigest()}},
        "spec": {"volumes": [{"name": "seaweedfs-config", "configMap": None,
                               "secret": {"secretName": "control-plane-s3-config"}}]}}}}
    run([*kube, "patch", "deployment", "seaweedfs", "--type", "strategic", "--patch-file", "/dev/stdin"], body=json.dumps(patch))
    run([*kube, "rollout", "status", "deployment/seaweedfs", "--timeout=180s"])
    # Use the worker's existing MinIO client, with credentials only on stdin.
    bucket_script = '''import json, sys
from urllib.parse import urlsplit
from minio import Minio
settings = json.load(sys.stdin)
endpoint = urlsplit(settings["endpoint"])
s3 = Minio(endpoint.netloc, access_key=settings["access"],
    secret_key=settings["secret"], secure=endpoint.scheme == "https", region="us-east-1")
if not s3.bucket_exists("app-content-documents"):
    s3.make_bucket("app-content-documents")
'''
    run(["docker", "run", "--rm", "-i", "--network", "host", "--entrypoint", "python", image, "-c", bucket_script],
        step="Create documents bucket with the worker MinIO client",
        body=json.dumps({"endpoint": f"http://127.0.0.1:{int(os.environ['K3D_HOST_PORT_SEAWEEDFS_S3'])}",
            "access": base64.b64decode(foundation["SEAWEEDFS_ADMIN_USER"]).decode(),
            "secret": base64.b64decode(foundation["SEAWEEDFS_ADMIN_PASSWORD"]).decode()}))
    return credentials


def provision_worker_identity(foundation: dict) -> None:
    # The generic factory identities hook creates the client and retains its secret.
    base = f"http://127.0.0.1:{int(os.environ['K3D_HOST_PORT_KEYCLOAK'])}"
    form = urlencode({"grant_type": "password", "client_id": "admin-cli",
        "username": base64.b64decode(foundation["KC_BOOTSTRAP_ADMIN_USERNAME"]).decode(),
        "password": base64.b64decode(foundation["KC_BOOTSTRAP_ADMIN_PASSWORD"]).decode()}).encode()
    request = Request(base + "/realms/master/protocol/openid-connect/token", data=form,
                      headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urlopen(request, timeout=30) as response:
        token = json.load(response)["access_token"]

    def api(path: str, method: str = "GET", payload: dict | None = None):
        request = Request(base + "/admin/realms/app" + path, method=method,
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
            data=json.dumps(payload).encode() if payload is not None else None)
        with urlopen(request, timeout=30) as response:
            body = response.read()
            return json.loads(body) if body else None

    clients = api("/clients?clientId=knowledge-flow-worker")
    if len(clients) != 1:
        raise RuntimeError("Expected the knowledge-flow-worker client from identities.yaml")
    client = clients[0]
    client.update(standardFlowEnabled=False, implicitFlowEnabled=False,
                  directAccessGrantsEnabled=False, fullScopeAllowed=False)
    path = "/clients/" + client["id"]
    api(path, "PUT", client)
    mappers = [
        {"name": "workload-audience", "protocolMapper": "oidc-audience-mapper",
         "config": {"included.custom.audience": "control-plane"}},
        {"name": "workload-client-id", "protocolMapper": "oidc-hardcoded-claim-mapper",
         "config": {"claim.name": "client_id", "claim.value": "knowledge-flow-worker", "jsonType.label": "String"}},
        {"name": "workload-username", "protocolMapper": "oidc-usermodel-property-mapper",
         "config": {"user.attribute": "username", "claim.name": "preferred_username", "jsonType.label": "String"}},
    ]
    current = {m["name"]: m["id"] for m in api(path + "/protocol-mappers/models")}
    for mapper in mappers:
        mapper["protocol"] = "openid-connect"
        mapper["config"].update({"access.token.claim": "true", "id.token.claim": "false"})
        target = path + "/protocol-mappers/models"
        if mapper["name"] in current:
            mapper["id"] = current[mapper["name"]]
            api(target + "/" + mapper["id"], "PUT", mapper)
        else:
            api(target, "POST", mapper)


if __name__ == "__main__":
    try:
        prepare()
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
    except Exception as error:
        # Exceptions from network libraries can carry sensitive request details.
        raise SystemExit(f"Manager ingestion preparation failed ({type(error).__name__}); check infrastructure prerequisites, image and rendered configuration") from None
