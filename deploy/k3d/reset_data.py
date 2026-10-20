#!/usr/bin/env python3
"""Reset the dedicated factory k3d installation; preview unless explicitly confirmed."""

import base64
import fcntl
import json
import os
import re
from pathlib import Path
import subprocess
import sys
from urllib.parse import quote

MANAGER_APPS = {"fred-manager", "fred-manager-worker"}
APPS = {
    "control-plane-backend",
    "control-plane-worker",
    "knowledge-flow-backend",
    "knowledge-flow-worker",
    "fred-agents",
    "frontend",
} | MANAGER_APPS
INFRA = {
    "postgres",
    "keycloak",
    "openfga",
    "opensearch",
    "opensearch-dashboards",
    "seaweedfs",
    "temporal",
    "temporal-ui",
    "prometheus",
    "grafana",
}
DATABASES = {
    "fred": "fred",
    "data": "tabular",
    "temporal": "temporal",
    "temporal_visibility": "temporal",
}
BUCKETS = {
    "app-content",
    "app-content-documents",
    "app-content-objects",
    "filesystem",
    "control-plane-content",
    "fred-runtime",
    "app-chat-profile",
    "app-feedback",
}
INDEXES = {"vector-index-mistral", "app-logs-index"}
RELEASE = "meta.helm.sh/release-name"


def manager_configuration(name, config):
    return name in MANAGER_APPS or (
        name in {"control-plane-backend", "control-plane-worker"}
        and config.get("security", {}).get("rebac", {}).get("store_name") == "fred-manager"
    )


class Refused(RuntimeError):
    pass


def require(ok, message):
    if not ok:
        raise Refused(message)


def run(args, data=None, timeout=180):
    # Captured stderr can contain connection strings or request bodies. Do not echo it.
    result = subprocess.run(args, input=data, text=True, capture_output=True, timeout=timeout)
    require(
        result.returncode == 0,
        f"{args[0]} operation failed ({result.returncode}); no further phase was run",
    )
    return result.stdout


class Reset:
    def __init__(self):
        self.context = os.environ["KUBE_CONTEXT"]
        self.namespace = os.environ.get("K3D_NAMESPACE", "fred")
        self.cluster = os.environ["K3D_CLUSTER"]
        self.state_file = Path(os.environ["K3D_RESET_STATE_DIR"]) / "reset-state.json"
        self.headers = {}
        self.needs_stop_on_failure = False
        mode = os.environ.get("K3D_RESET_FOR_UPGRADE", "")
        require(mode in ("", "1"), "K3D_RESET_FOR_UPGRADE must be empty or 1")
        self.for_upgrade = mode == "1"
        self.allowed_buckets = set(BUCKETS)
        self.indexes = set(INDEXES)

    def kubectl(self, *args, data=None, timeout=180):
        return run(
            [
                "kubectl",
                "--context",
                self.context,
                "--namespace",
                self.namespace,
                *args,
            ],
            data,
            timeout,
        )

    def helm(self, *args):
        return run(
            [
                "helm",
                "--kube-context",
                self.context,
                "--namespace",
                self.namespace,
                *args,
            ]
        )

    def get(self, kind, *args):
        return json.loads(self.kubectl("get", kind, *args, "-o", "json"))

    def http(self, service, path, method="GET", missing=False, body=None):
        urls = {
            "search": "https://opensearch:9200",
            "fga": "http://openfga:9080",
            "files": "http://seaweedfs:8888",
        }
        config = "".join(f"header = {json.dumps(h)}\n" for h in self.headers.get(service, []))
        if body is not None:
            config += 'header = "Content-Type: application/json"\n'
            config += "data = " + json.dumps(json.dumps(body)) + "\n"
        response = self.kubectl(
            "exec",
            "-i",
            "deployment/opensearch",
            "-c",
            "opensearch",
            "--",
            "curl",
            "--silent",
            "--show-error",
            "--insecure",
            "--connect-timeout",
            "10",
            "--max-time",
            "120",
            "--config",
            "-",
            "--request",
            method,
            "--header",
            "Accept: application/json",
            "--write-out",
            "\n%{http_code}",
            urls[service] + path,
            data=config,
        )
        body, code = response.rsplit("\n", 1)
        if missing and code == "404":
            return None
        require(code.startswith("2"), f"{service} {method} failed (HTTP {code})")
        value = json.loads(body) if body else {}
        require(
            not isinstance(value, dict) or not value.get("error"),
            f"{service} returned an error",
        )
        return value

    def sql(self, sql, database="postgres"):
        return self.kubectl(
            "exec",
            "-i",
            "deployment/postgres",
            "-c",
            "postgres",
            "--",
            "sh",
            "-ec",
            'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1" -At',
            "reset",
            database,
            data=sql,
        )

    def values(self, release):
        return json.loads(self.helm("get", "values", release, "--all", "-o", "json"))

    def check_config(self, values, names):
        for name in names:
            if name == "frontend":
                continue
            app = values["applications"][name]
            require(
                not app.get("autoscaling", {}).get("enabled"),
                "autoscaling is unsupported",
            )
            c = app["configuration"]
            manager = manager_configuration(name, c)
            if manager and name == "control-plane-worker":
                c = values["applications"]["control-plane-backend"]["configuration"]
            pg = c["storage"]["postgres"]
            require(
                pg.get("host") == "postgres"
                and pg.get("database") == "fred"
                and pg.get("port", 5432) == 5432
                and pg.get("username") == "fred",
                "custom PostgreSQL storage is unsupported",
            )
            fga = c["security"]["rebac"]
            require(
                (manager or fga.get("type") == "openfga")
                and fga.get("api_url") in ("http://openfga:9080", "http://openfga:9080/")
                and fga.get("store_name", "fred") == ("fred-manager" if manager else "fred")
                and not fga.get("store_id")
                and not fga.get("authorization_model_id")
                and fga.get("create_store_if_needed", True)
                and fga.get("sync_schema_on_init", True),
                "custom OpenFGA storage is unsupported",
            )
            if not manager:
                temporal = c.get("scheduler", {}).get("temporal", {})
                require(
                    temporal.get("host") == "temporal:7233" and temporal.get("namespace", "default") == "default",
                    "custom Temporal storage is unsupported",
                )
            if manager:
                connection = c.get("scheduler", {}).get("temporal", {})
                require(
                    connection.get("host", "temporal:7233") == "temporal:7233"
                    and connection.get("namespace", "default") == "default",
                    "custom lifecycle Temporal storage is unsupported",
                )
                lifecycle = c.get("scheduler", {}).get("lifecycle", {}).get("temporal", {})
                require(
                    lifecycle.get("host", "temporal:7233") == "temporal:7233"
                    and lifecycle.get("namespace", "default") == "default",
                    "custom lifecycle Temporal storage is unsupported",
                )
            storage = c["storage"]
            if manager:
                content = storage.get("content")
                if content:
                    self.local_bucket(content, "fred-manager-originals")
                processing = c.get("scheduler", {}).get("processing")
                if processing:
                    temporal = processing.get("temporal", {})
                    require(
                        temporal.get("host") == "temporal:7233"
                        and temporal.get("namespace", "default") == "default",
                        "custom processing Temporal storage is unsupported",
                    )
                    self.local_bucket(processing["derived"], "fred-manager-derived")
            if name.startswith("knowledge-flow"):
                processing = c.get("manager_processing")
                if processing:
                    self.local_bucket(processing, "fred-manager-derived")
                    require(
                        processing["vector_store"] == {"type": "opensearch", "index": "fred-manager-vectors"},
                        "custom manager vector store is unsupported",
                    )
                    self.indexes.add("fred-manager-vectors")
            if not manager:
                require(
                    storage["opensearch"]["host"] == "https://opensearch:9200",
                    "custom OpenSearch host is unsupported",
                )
                require(
                    storage["log_store"] == {"type": "opensearch", "index": "app-logs-index"},
                    "custom log store is unsupported",
                )
            if name.startswith("knowledge-flow"):
                for key in ("metadata_store", "tag_store", "resource_store"):
                    require(
                        storage[key]["type"] == "postgres",
                        f"custom {key} is unsupported",
                    )
                require(
                    storage["vector_store"]["type"] == "opensearch"
                    and storage["vector_store"]["index"] == "vector-index-mistral",
                    "custom vector store is unsupported",
                )
                for key, bucket in (
                    ("content_storage", "app-content"),
                    ("filesystem", "filesystem"),
                ):
                    s = c[key]
                    require(
                        s["type"] == "minio"
                        and s["endpoint"] == "http://seaweedfs:8333"
                        and s["bucket_name"] == bucket,
                        f"custom {key} is unsupported",
                    )
            elif name.startswith("control-plane") and not manager:
                s = storage["content_storage"]
                require(
                    s["type"] == "minio"
                    and s["endpoint"] == "http://seaweedfs:8333"
                    and s["bucket_name"] == "control-plane-content",
                    "custom content storage is unsupported",
                )
            elif name == "fred-agents":
                s = storage["object_store"]
                require(
                    s["type"] == "minio"
                    and s["endpoint"] == "http://seaweedfs:8333"
                    and s.get("bucket_name", "fred-runtime") == "fred-runtime",
                    "custom runtime storage is unsupported",
                )

    def local_bucket(self, config, expected):
        require(
            config.get("endpoint") == "http://seaweedfs:8333"
            and config.get("bucket") == expected,
            "custom manager content storage is unsupported",
        )
        self.allowed_buckets.add(expected)

    def stores(self):
        stores, token = [], ""
        while True:
            page = self.http(
                "fga",
                "/stores?page_size=100" + ("&continuation_token=" + quote(token, safe="") if token else ""),
            )
            stores.extend(page.get("stores", []))
            next_token = page.get("continuation_token", "")
            if not next_token:
                break
            require(next_token != token, "OpenFGA pagination did not advance")
            token = next_token
        require(
            all(
                s["name"] in ("fred", "fred-manager")
                or re.fullmatch(
                    r"fred-manager-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}",
                    s["name"],
                )
                for s in stores
            ),
            "other OpenFGA stores are present",
        )
        return stores

    def buckets(self):
        page = self.http("files", "/buckets/?limit=10000", missing=True)
        if page is None:
            return []
        require(
            not page.get("ShouldDisplayLoadMore"),
            "bucket inventory exceeds supported page size",
        )
        names = [x["FullPath"].removeprefix("/buckets/") for x in page.get("Entries", []) or []]
        require(set(names) <= self.allowed_buckets, "other content buckets are present")
        return names

    def preflight(self):
        require(
            self.context == f"k3d-{self.cluster}",
            "only an explicit k3d context is supported",
        )
        clusters = json.loads(run(["k3d", "cluster", "list", "-o", "json"]))
        require(
            any(x["name"] == self.cluster for x in clusters),
            "local k3d cluster is absent",
        )
        releases = json.loads(self.helm("list", "--all-namespaces", "--all", "-o", "json"))
        for r in releases:
            if r["namespace"] == "kube-system" and r["name"] in (
                "traefik",
                "traefik-crd",
            ):
                continue
            require(
                r["namespace"] == self.namespace
                and r["name"] in ("fred-stack", "fred-app", "fred-manager")
                and r["status"] == "deployed",
                "other applications or incomplete Helm operations are present",
            )
        deployments = self.get("deployments", "--all-namespaces")["items"]
        self.deployments = {}
        for d in deployments:
            meta = d["metadata"]
            if meta["namespace"] == "kube-system":
                require(
                    meta["name"]
                    in (
                        "coredns",
                        "local-path-provisioner",
                        "metrics-server",
                        "traefik",
                    ),
                    "unknown system workload",
                )
                continue
            name = meta["name"]
            expected = {"fred-app", "fred-manager"} if name in MANAGER_APPS else {"fred-app"} if name in APPS else {"fred-stack"}
            require(
                meta["namespace"] == self.namespace
                and name in APPS | INFRA
                and meta.get("annotations", {}).get(RELEASE) in expected,
                "other applications or unknown deployments are present",
            )
            self.deployments[name] = d
        integrated = any(
            self.deployments[n]["metadata"]["annotations"][RELEASE] == "fred-app"
            for n in MANAGER_APPS & self.deployments.keys()
        )
        rust_control_plane = manager_configuration(
            "control-plane-backend",
            self.values("fred-app").get("applications", {}).get("control-plane-backend", {}).get("configuration", {}),
        )
        required_apps = (
            MANAGER_APPS | {"frontend", "knowledge-flow-backend", "knowledge-flow-worker"}
            if integrated else APPS - MANAGER_APPS - ({"fred-agents"} if rust_control_plane else set())
        )
        require(
            required_apps | INFRA <= self.deployments.keys(),
            "required local services are missing",
        )
        for kind in ("statefulsets", "cronjobs", "horizontalpodautoscalers"):
            require(
                not self.get(kind, "--all-namespaces")["items"],
                f"{kind} are unsupported on the dedicated reset cluster",
            )
        jobs = self.get("jobs", "--all-namespaces")["items"]
        for job in jobs:
            m = job["metadata"]
            own = (
                m.get("labels", {}).get("fred.local/reset") == "migration"
                and m.get("namespace") == self.namespace
                and m.get("name") in {f"fred-data-reset-migration-{n}" for n in range(3)}
                and self.state_file.exists()
            )
            status = job.get("status", {})
            complete = any(
                c.get("type") == "Complete" and c.get("status") == "True" for c in status.get("conditions", [])
            )
            require(
                (complete and not status.get("active", 0)) or own,
                "unfinished Jobs must be resolved before reset",
            )
        deployment_uids = {d["metadata"]["uid"] for d in deployments}
        replicasets = self.get("replicasets", "--all-namespaces")["items"]
        for rs in replicasets:
            require(
                any(
                    o["kind"] == "Deployment" and o["uid"] in deployment_uids
                    for o in rs["metadata"].get("ownerReferences", [])
                ),
                "standalone ReplicaSets are unsupported",
            )
        require(
            not self.get("replicationcontrollers", "--all-namespaces")["items"],
            "ReplicationControllers are unsupported",
        )
        daemonsets = self.get("daemonsets", "--all-namespaces")["items"]
        owners = {r["metadata"]["uid"] for r in replicasets + jobs + daemonsets}
        for pod in self.get("pods", "--all-namespaces")["items"]:
            require(
                pod.get("status", {}).get("phase") in ("Succeeded", "Failed")
                or any(o["uid"] in owners for o in pod["metadata"].get("ownerReferences", [])),
                "standalone or unknown running Pods are present",
            )
        for ds in daemonsets:
            m = ds["metadata"]
            require(
                (m["namespace"] == self.namespace and m["name"] == "fluent-bit")
                or (m["namespace"] == "kube-system" and m["name"].startswith("svclb-traefik-")),
                "unknown daemonset",
            )
        for release in {self.deployments[n]["metadata"]["annotations"][RELEASE] for n in APPS & self.deployments.keys()}:
            names = {n for n in APPS & self.deployments.keys() if self.deployments[n]["metadata"]["annotations"][RELEASE] == release}
            self.check_config(self.values(release), names)
        secret = self.get("secret", "fred-secrets")["data"]

        def decode(key):
            return base64.b64decode(secret[key]).decode()

        auth = base64.b64encode(
            (decode("OPENSEARCH_ADMIN") + ":" + decode("OPENSEARCH_ADMIN_PASSWORD")).encode()
        ).decode()
        self.headers = {
            "search": ["Authorization: Basic " + auth],
            "fga": ["Authorization: Bearer " + decode("OPENFGA_API_TOKEN")],
        }
        self.stores()
        self.buckets()
        self.http("search", "/_cluster/health")
        databases = self.sql(
            "SELECT datname || ':' || pg_get_userbyid(datdba) FROM pg_database WHERE datname IN ('fred','data','temporal','temporal_visibility');"
        )
        expected = {f"{db}:{owner}" for db, owner in DATABASES.items()}
        actual = set(databases.splitlines())
        require(
            actual <= expected and (actual == expected or self.state_file.exists()),
            "unexpected database ownership or missing database",
        )
        hooks = self.helm("get", "hooks", "fred-app")
        rendered = self.kubectl(
            "create",
            "--dry-run=client",
            "--validate=false",
            "-f",
            "-",
            "-o",
            "json",
            data=hooks,
        )
        self.jobs = []
        while rendered.strip():
            obj, end = json.JSONDecoder().raw_decode(rendered.lstrip())
            self.jobs.extend(obj.get("items", [obj]))
            rendered = rendered.lstrip()[end:]
        self.jobs = [
            j
            for j in self.jobs
            if j["kind"] == "Job"
            and re.fullmatch(
                r"(?:control-plane-backend|knowledge-flow-backend|fred-agents)-migration-[0-9]+",
                j["metadata"]["name"],
            )
        ]
        expected_migrations = {n for n in ("control-plane-backend", "knowledge-flow-backend", "fred-agents") if n in self.deployments}
        require(
            len(self.jobs) == len(expected_migrations)
            and {j["metadata"]["name"].rsplit("-migration-", 1)[0] for j in self.jobs} == expected_migrations,
            "installed SQL migration Jobs do not match the deployed services",
        )
        self.jobs.sort(key=lambda j: int(j["metadata"].get("annotations", {}).get("helm.sh/hook-weight", "0")))
        names = sorted(APPS & self.deployments.keys()) + ["temporal"]
        identity = {
            n: {
                "uid": self.deployments[n]["metadata"]["uid"],
                "template": self.deployments[n]["spec"]["template"],
            }
            for n in names
        }
        # Hash templates instead of persisting environment values in the resume file.
        import hashlib

        signature = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        self.state = {
            "context": self.context,
            "namespace": self.namespace,
            "signature": signature,
            "for_upgrade": self.for_upgrade,
            "replicas": {n: self.deployments[n]["spec"].get("replicas", 1) for n in names},
        }
        if self.state_file.exists():
            saved = json.loads(self.state_file.read_text())
            require(
                all(saved[k] == self.state[k] for k in ("context", "namespace", "signature")),
                "deployments changed since failed reset; saved state cannot be reused",
            )
            require(saved.get("for_upgrade", False) == self.for_upgrade, "reset mode changed since failed reset")
            self.state = saved
        require(self.state["replicas"]["temporal"] > 0, "Temporal must be enabled")

    def scale(self, name, count):
        self.kubectl("scale", "deployment/" + name, "--replicas=" + str(count))

    def wait_ready(self, name):
        self.kubectl("rollout", "status", "deployment/" + name, "--timeout=300s", timeout=320)

    def stop(self):
        for name in self.state["replicas"]:
            self.scale(name, 0)
        for name in self.state["replicas"]:
            self.wait_ready(name)
        # Migration Jobs reuse app labels; only Deployment-owned Pods must disappear.
        deployment_uids = {self.deployments[n]["metadata"]["uid"] for n in self.state["replicas"]}
        replica_uids = {
            rs["metadata"]["uid"]
            for rs in self.get("replicasets")["items"]
            if any(o["uid"] in deployment_uids for o in rs["metadata"].get("ownerReferences", []))
        }
        for pod in self.get("pods")["items"]:
            if any(o["uid"] in replica_uids for o in pod["metadata"].get("ownerReferences", [])):
                self.kubectl(
                    "wait",
                    "--for=delete",
                    "pod/" + pod["metadata"]["name"],
                    "--timeout=180s",
                    timeout=200,
                )

    def clear(self):
        for store in self.stores():
            self.http("fga", "/stores/" + quote(store["id"], safe=""), "DELETE")
        for index in sorted(self.indexes):
            self.http("search", "/" + index, "DELETE", missing=True)
        for bucket in self.buckets():
            self.http(
                "files",
                "/buckets/" + quote(bucket, safe="") + "?recursive=true",
                "DELETE",
                missing=True,
            )
        require(not self.buckets(), "content cleanup is incomplete")
        for db, owner in DATABASES.items():
            # No FORCE: an unexpected remaining connection must stop the reset.
            self.sql(
                f'DROP DATABASE IF EXISTS "{db}";\nCREATE DATABASE "{db}" OWNER "{owner}";\n'
                f'REVOKE ALL ON DATABASE "{db}" FROM PUBLIC;\nGRANT CONNECT ON DATABASE "{db}" TO "{owner}";\n'
            )
            if db in ("fred", "data"):
                self.sql("CREATE EXTENSION vector;", db)

    def initialize_buckets(self):
        # Manager validates pre-provisioned buckets before accepting any traffic.
        for bucket in sorted(self.allowed_buckets - BUCKETS):
            self.http("files", "/buckets/" + quote(bucket, safe="") + "/", "POST")

    def initialize(self):
        self.initialize_buckets()
        self.http("fga", "/stores", "POST", body={"name": "fred"})
        self.scale("temporal", self.state["replicas"]["temporal"])
        self.wait_ready("temporal")
        self.kubectl(
            "exec",
            "deployment/temporal",
            "-c",
            "temporal",
            "--",
            "temporal",
            "operator",
            "namespace",
            "create",
            "--namespace",
            "default",
            "--retention",
            "72h",
            "--command-timeout",
            "30s",
        )
        if self.for_upgrade:
            return
        for number, installed in enumerate(self.jobs):
            name = f"fred-data-reset-migration-{number}"
            self.kubectl(
                "delete",
                "job",
                name,
                "--ignore-not-found=true",
                "--cascade=foreground",
                "--wait=true",
            )
            spec = installed["spec"].copy()
            spec.pop("selector", None)
            job = {
                "apiVersion": "batch/v1",
                "kind": "Job",
                "metadata": {"name": name, "labels": {"fred.local/reset": "migration"}},
                "spec": spec,
            }
            self.kubectl("create", "-f", "-", data=json.dumps(job))
            self.kubectl(
                "wait",
                "--for=condition=complete",
                "job/" + name,
                "--timeout=300s",
                timeout=320,
            )
            self.kubectl("delete", "job", name, "--cascade=foreground", "--wait=true")

    def execute(self):
        temporary = self.state_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state))
        temporary.replace(self.state_file)
        self.needs_stop_on_failure = True
        print("Stopping Fred and Temporal...", flush=True)
        self.stop()
        for number in range(len(self.jobs)):
            self.kubectl(
                "delete",
                "job",
                f"fred-data-reset-migration-{number}",
                "--ignore-not-found=true",
                "--cascade=foreground",
                "--wait=true",
            )
        print("Clearing local business data...", flush=True)
        self.clear()
        print("Initializing Temporal..." if self.for_upgrade else "Initializing schemas with installed images...", flush=True)
        self.initialize()
        if self.for_upgrade:
            self.needs_stop_on_failure = False
            self.state_file.unlink()
            print("Reset complete for upgrade. Fred remains stopped; deploy the target release to initialize its SQL baseline and OpenFGA model.")
            return
        for name, count in self.state["replicas"].items():
            if name != "temporal":
                self.scale(name, count)
        for name, count in self.state["replicas"].items():
            if count:
                self.wait_ready(name)
        self.needs_stop_on_failure = False
        self.state_file.unlink()
        print("Reset complete. Keycloak accounts remain. Log in, accept terms and bootstrap again.")


def main():
    os.umask(0o077)
    reset = Reset()
    reset.state_file.parent.mkdir(parents=True, exist_ok=True)
    with (reset.state_file.parent / "reset.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        reset.preflight()
        print(f"Dedicated local reset: {reset.context}, namespace {reset.namespace}")
        print("Erase: fred/data SQL, Fred OpenFGA stores, Temporal work, Fred indexes and content buckets.")
        print("Preserve: Keycloak accounts/clients, credentials, infrastructure, images, observability.")
        print("Stop local Fred processes connected through host ports before execution.")
        if reset.for_upgrade:
            print("Upgrade mode: leave SQL/FGA empty and Fred stopped for the target release; do not restart installed images.")
        confirm = os.environ.get("K3D_RESET_CONFIRM", "")
        require(confirm in ("", "reset"), "confirmation must be CONFIRM=reset")
        if not confirm:
            prefix = "K3D_RESET_FOR_UPGRADE=1 " if reset.for_upgrade else ""
            print(f"Preview only. Execute with: {prefix}make k3d-app-reset DIR=<this checkout> CONFIRM=reset")
            return
        try:
            reset.execute()
        except BaseException:
            if not reset.needs_stop_on_failure:
                raise
            # Never let restarted workers resume after a partial initialization/readiness failure.
            for name in reset.state["replicas"]:
                if name != "temporal":
                    try:
                        reset.scale(name, 0)
                    except Exception:
                        pass
            print(
                "Reset failed. Fred is kept stopped where reachable. Fix the failure, then repeat the same command; original replica counts are saved.",
                file=sys.stderr,
            )
            raise


if __name__ == "__main__":
    try:
        main()
    except (Refused, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        print(
            f"Reset refused or failed: {exc if isinstance(exc, Refused) else type(exc).__name__}",
            file=sys.stderr,
        )
        sys.exit(1)
