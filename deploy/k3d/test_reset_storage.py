"""Opt-in storage contract test on disposable Docker services, never k3d.

Run RESET_STORAGE_TESTS=1 python3 -m unittest discover -s deploy/k3d -p test_reset_storage.py.
"""

import os
import subprocess
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

from test_reset_data import reset


@unittest.skipUnless(
    os.environ.get("RESET_STORAGE_TESTS") == "1",
    "opt-in disposable Docker storage test",
)
class StorageTest(unittest.TestCase):
    def test_real_cleanup_is_repeatable_and_preserves_other_databases_and_infra_index(
        self,
    ):
        prefix = "fred-reset-test-" + uuid.uuid4().hex[:10]
        network = prefix
        subprocess.run(["docker", "network", "create", network], check=True, capture_output=True)
        self.addCleanup(subprocess.run, ["docker", "network", "rm", network], capture_output=True)
        containers = {}
        images = {
            "postgres": (
                "pgvector/pgvector:pg17",
                ["-e", "POSTGRES_PASSWORD=test", "-e", "POSTGRES_USER=postgres"],
                [],
            ),
            "openfga": (
                "openfga/openfga:v1.11.0",
                ["-e", "OPENFGA_HTTP_ADDR=0.0.0.0:9080"],
                ["run", "--datastore-engine", "memory"],
            ),
            "seaweedfs": (
                "chrislusf/seaweedfs:4.29",
                [],
                ["server", "-dir=/data", "-filer", "-s3"],
            ),
            "opensearch": (
                "mirror.gcr.io/opensearchproject/opensearch:2.19.3",
                [
                    "-e",
                    "discovery.type=single-node",
                    "-e",
                    "DISABLE_SECURITY_PLUGIN=true",
                    "-e",
                    "DISABLE_INSTALL_DEMO_CONFIG=true",
                    "-e",
                    "OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m",
                ],
                [],
            ),
        }
        for name, (image, options, args) in images.items():
            container = prefix + "-" + name
            subprocess.run(
                [
                    "docker",
                    "run",
                    "--pull=never",
                    "-d",
                    "--name",
                    container,
                    "--network",
                    network,
                    "--network-alias",
                    name,
                    *options,
                    image,
                    *args,
                ],
                check=True,
                capture_output=True,
            )
            containers[name] = container
            self.addCleanup(
                subprocess.run,
                ["docker", "rm", "-f", "-v", container],
                capture_output=True,
            )
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(
                os.environ,
                KUBE_CONTEXT="k3d-test",
                K3D_CLUSTER="test",
                K3D_RESET_STATE_DIR=tmp,
            ),
        ):
            r = reset.Reset()

            def docker_exec(*args, data=None, timeout=180):
                # Reuse the production SQL and HTTP code, replacing only its transport.
                component = args[args.index("-c") + 1]
                command = list(args[args.index("--") + 1 :])
                command = [a.replace("https://opensearch:9200", "http://opensearch:9200") for a in command]
                return reset.run(
                    ["docker", "exec", "-i", containers[component], *command],
                    data,
                    timeout,
                )

            r.kubectl = docker_exec
            deadline = time.monotonic() + 100
            while True:
                try:
                    r.sql("SELECT 1;")
                    r.http("search", "/_cluster/health")
                    r.http("fga", "/stores")
                    r.http("files", "/?limit=1")
                    break
                except reset.Refused:
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(1)
            for owner in ("fred", "tabular", "temporal"):
                r.sql(f"CREATE ROLE {owner};")
            for db, owner in reset.DATABASES.items():
                r.sql(f"CREATE DATABASE {db} OWNER {owner};")
                r.sql(
                    "CREATE TABLE marker (value text); INSERT INTO marker VALUES ('old');",
                    db,
                )
            for db in ("keycloak", "evaluation"):
                r.sql(f"CREATE DATABASE {db};")
                r.sql(
                    "CREATE TABLE marker (value text); INSERT INTO marker VALUES ('retained');",
                    db,
                )
            for name in (
                "fred",
                "fred-manager",
                "fred-manager-8bd7b5ba-d75f-462f-b7e6-e85df773065b",
            ):
                r.http("fga", "/stores", "POST", body={"name": name})
            for index in (*reset.INDEXES, "infra-logs"):
                r.http("search", "/" + index, "PUT", body={})
                r.http(
                    "search",
                    "/" + index + "/_doc/1?refresh=true",
                    "PUT",
                    body={"text": "old"},
                )
            # Use the real filer upload interface, including a nested object.
            payload = '--test\r\nContent-Disposition: form-data; name="file"; filename="old.txt"\r\nContent-Type: text/plain\r\n\r\nold\r\n--test--\r\n'
            docker_exec(
                "exec",
                "-i",
                "deployment/opensearch",
                "-c",
                "opensearch",
                "--",
                "curl",
                "--fail",
                "--silent",
                "-H",
                "Content-Type: multipart/form-data; boundary=test",
                "--data-binary",
                "@-",
                "http://seaweedfs:8888/buckets/filesystem/nested/",
                data=payload,
            )
            self.assertEqual(r.buckets(), ["filesystem"])
            r.clear()
            self.assertEqual(r.stores(), [])
            self.assertEqual(r.buckets(), [])
            for db in reset.DATABASES:
                self.assertEqual(
                    r.sql("SELECT count(*) FROM pg_tables WHERE schemaname='public';", db).strip(),
                    "0",
                )
            self.assertEqual(
                r.sql("SELECT extname FROM pg_extension WHERE extname='vector';", "fred").strip(),
                "vector",
            )
            for db in ("keycloak", "evaluation"):
                self.assertEqual(r.sql("SELECT value FROM marker;", db).strip(), "retained")
            for index in reset.INDEXES:
                self.assertIsNone(r.http("search", "/" + index, missing=True))
            self.assertEqual(r.http("search", "/infra-logs/_count")["count"], 1)
            r.clear()
            self.assertEqual(r.stores(), [])
            self.assertEqual(r.sql("SELECT value FROM marker;", "keycloak").strip(), "retained")


if __name__ == "__main__":
    unittest.main()
