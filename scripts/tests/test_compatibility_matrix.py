"""Check the compatibility matrix derivation from client lockfiles, offline."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import compatibility_matrix as cm  # noqa: E402

COMMIT = "0" * 40

TABLE = """\
apiVersion: fred.dev/v1alpha1
kind: ClientCompatibility
services:
  postgres:
    - client: pypi/psycopg
      versions: ">=3.3.0 <4"
      server: ">=10 <20"
      source: https://example.org/psycopg
    - client: pypi/asyncpg
      versions: ">=0.31.0 <0.32"
      server: ">=9.5 <19"
      source: https://example.org/asyncpg
  s3:
    - client: pypi/minio
      versions: ">=7.0.0 <8"
      server: "*"
      source: https://example.org/minio
  temporal:
    - client: pypi/temporalio
      versions: ">=1.0.0 <2"
      server: unknown
      source: https://example.org/temporal
      note: nothing published
"""


def lock(*packages: tuple[str, str]) -> str:
    return "version = 1\n" + "".join(
        f'\n[[package]]\nname = "{name}"\nversion = "{version}"\n'
        for name, version in packages
    )


class FakeRepository:
    def __init__(self, directory: Path) -> None:
        self.root = directory
        _ = shutil.copytree(
            ROOT / cm.TABLE_DIR / "schemas", directory / cm.TABLE_DIR / "schemas"
        )
        self.table(TABLE)

    def write(self, relative: str | Path, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(text, encoding="utf-8")

    def table(self, text: str) -> None:
        self.write(cm.TABLE_DIR / "clients.yaml", text)

    def component(self, name: str, *packages: tuple[str, str]) -> None:
        self.write(f"apps/{name}/uv.lock", lock(*packages))


BASELINE = (
    ("psycopg", "3.3.6"),
    ("asyncpg", "0.31.0"),
    ("minio", "7.2.20"),
    ("temporalio", "1.35.0"),
)


class CompatibilityMatrixTest(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.repo = FakeRepository(Path(self._directory.name))

    def tearDown(self) -> None:
        self._directory.cleanup()

    def assertFails(self, fragment: str) -> None:
        with self.assertRaises(cm.CompatibilityError) as raised:
            _ = cm.derive(self.repo.root)
        self.assertIn(fragment, str(raised.exception))

    def test_repository_table_covers_every_locked_client(self) -> None:
        services = cm.derive(ROOT)
        self.assertIn("postgres", services)
        self.assertTrue(all(service["clients"] for service in services.values()))

    def test_service_range_intersects_every_client(self) -> None:
        self.repo.component("api", *BASELINE)
        services = cm.derive(self.repo.root)
        postgres = {
            key: value
            for key, value in services["postgres"].items()
            if key != "clients"
        }
        self.assertEqual(
            postgres,
            {
                "support": "range",
                "min": "10.0.0",
                "below": "19.0.0",
                "range": ">=10.0.0 <19.0.0",
            },
        )
        self.assertEqual(services["s3"]["support"], "any")
        self.assertEqual(services["temporal"]["support"], "unknown")
        self.assertEqual(
            services["temporal"]["clients"][0]["note"], "nothing published"
        )

    def test_each_locked_version_is_listed_with_its_components(self) -> None:
        self.repo.component("api", *BASELINE)
        self.repo.component("worker", ("psycopg", "3.3.4"), *BASELINE[1:])
        clients = cm.derive(self.repo.root)["postgres"]["clients"]
        psycopg = [entry for entry in clients if entry["client"] == "pypi/psycopg"]
        self.assertEqual(
            [(entry["version"], entry["usedBy"]) for entry in psycopg],
            [("3.3.4", ["worker"]), ("3.3.6", ["api"])],
        )
        asyncpg = next(entry for entry in clients if entry["client"] == "pypi/asyncpg")
        self.assertEqual(asyncpg["usedBy"], ["api", "worker"])

    def test_bumped_client_outside_the_table_fails(self) -> None:
        self.repo.component("api", ("psycopg", "4.0.0"), *BASELINE[1:])
        self.assertFails("pypi/psycopg 4.0.0 is outside every rule")

    def test_rules_no_locked_version_matches_must_leave_the_table(self) -> None:
        self.repo.component("api", *BASELINE[:3])
        self.assertFails("no locked version matches pypi/temporalio >=1.0.0 <2.0.0")
        self.repo.table(
            TABLE.replace(
                "  s3:\n",
                """\
    - client: pypi/psycopg
      versions: ">=4.0.0 <5"
      server: ">=12"
      source: https://example.org/psycopg4
  s3:
""",
            )
        )
        self.repo.component("api", *BASELINE)
        self.assertFails("no locked version matches pypi/psycopg >=4.0.0 <5.0.0")

    def test_one_unknown_client_leaves_the_service_unknown(self) -> None:
        self.repo.table(TABLE.replace('server: ">=9.5 <19"', "server: unknown"))
        self.repo.component("api", *BASELINE)
        self.assertEqual(cm.derive(self.repo.root)["postgres"]["support"], "unknown")

    def test_locked_versions_are_listed_in_numeric_order(self) -> None:
        self.repo.component("api", ("psycopg", "3.3.10"), *BASELINE[1:])
        self.repo.component("worker", ("psycopg", "3.3.9"), *BASELINE[1:])
        clients = cm.derive(self.repo.root)["postgres"]["clients"]
        versions = [
            entry["version"] for entry in clients if entry["client"] == "pypi/psycopg"
        ]
        self.assertEqual(versions, ["3.3.9", "3.3.10"])

    def test_clients_without_a_common_server_version_fail(self) -> None:
        self.repo.table(TABLE.replace('server: ">=9.5 <19"', 'server: ">=20"'))
        self.repo.component("api", *BASELINE)
        self.assertFails(
            "postgres: the locked clients support no common server version"
        )

    def test_overlapping_rules_are_rejected(self) -> None:
        self.repo.table(
            TABLE
            + """\
  pgvector:
    - client: pypi/psycopg
      versions: ">=3.0.0 <3.4"
      server: ">=10"
      source: https://example.org/again
"""
        )
        self.repo.component("api", *BASELINE)
        self.assertFails("already a client of postgres")
        self.repo.table(
            TABLE.replace(
                "  s3:\n",
                """\
    - client: pypi/psycopg
      versions: ">=3.0.0 <3.4"
      server: ">=10"
      source: https://example.org/again
  s3:
""",
            )
        )
        self.assertFails("overlap >=3.3.0 <4.0.0")

    def test_a_range_without_cap_has_no_below(self) -> None:
        self.repo.table(
            TABLE.replace('server: ">=10 <20"', 'server: ">=10"').replace(
                'server: ">=9.5 <19"', 'server: ">=9.5"'
            )
        )
        self.repo.component("api", *BASELINE)
        postgres = cm.derive(self.repo.root)["postgres"]
        self.assertEqual((postgres["min"], postgres["range"]), ("10.0.0", ">=10.0.0"))
        self.assertNotIn("below", postgres)

    def test_service_names_are_a_closed_vocabulary(self) -> None:
        self.repo.table(TABLE.replace("  s3:\n", "  object-store:\n"))
        self.repo.component("api", *BASELINE)
        self.assertFails("'object-store' is not one of")

    def test_package_names_are_normalized(self) -> None:
        self.repo.table(TABLE.replace("pypi/minio", "pypi/MinIO"))
        self.repo.component("api", *BASELINE)
        self.assertEqual(
            cm.derive(self.repo.root)["s3"]["clients"][0]["client"], "pypi/minio"
        )

    def test_table_requires_a_source_and_a_valid_range(self) -> None:
        self.repo.component("api", *BASELINE)
        self.repo.table(TABLE.replace("      source: https://example.org/minio\n", ""))
        self.assertFails("'source' is a required property")
        self.repo.table(TABLE.replace('server: ">=10 <20"', 'server: "^10"'))
        self.assertFails("services.postgres.0.server")

    def test_ranges(self) -> None:
        self.assertTrue(cm.parse_range(">=3.3.0 <4").contains((3, 3, 6)))
        self.assertFalse(cm.parse_range(">=3.3.0 <4").contains((4, 0, 0)))
        self.assertTrue(cm.parse_range(">=4.59").contains((9, 0, 0)))
        for invalid in ("^15", "<16", ">=16 <15", ">=16 <16.0", ">= 15", ">=15,<16"):
            with (
                self.subTest(invalid=invalid),
                self.assertRaises(cm.CompatibilityError),
            ):
                _ = cm.parse_range(invalid)

    def test_prerelease_client_versions_use_their_numeric_prefix(self) -> None:
        self.repo.component("api", ("psycopg", "3.3.0rc1"), *BASELINE[1:])
        clients = cm.derive(self.repo.root)["postgres"]["clients"]
        psycopg = next(entry for entry in clients if entry["client"] == "pypi/psycopg")
        self.assertEqual(psycopg["version"], "3.3.0rc1")

    def test_build_writes_a_reloadable_matrix(self) -> None:
        self.repo.component("api", *BASELINE)
        matrix = cm.build(self.repo.root, "3.18.0-rc.1", COMMIT, "ThalesGroup/fred")
        self.assertEqual(matrix["release"], "3.18.0-rc.1")
        path = self.repo.root / "compatibility-matrix.yaml"
        cm.dump(matrix, path)
        self.assertEqual(cm.load_yaml(path), matrix)
        with self.assertRaises(cm.CompatibilityError):
            _ = cm.build(self.repo.root, "v3.18.0", COMMIT, "ThalesGroup/fred")


if __name__ == "__main__":
    _ = unittest.main()
